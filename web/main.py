"""Stock Agent — FastAPI 엔트리포인트 (Streamlit 점진 이전용, Phase 0 셸).

전환 기간: nginx가 /v2/ 를 이 앱(8000)으로, / 는 기존 Streamlit(8501)으로 보낸다.
지금은 로그인 + 대시보드 셸(티커테이프·F&G·탭 내비)만. 탭 내용은 Phase 1부터 채운다.

실행: .venv/Scripts/python -m uvicorn web.main:app --reload --port 8000
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # .env의 실제 계정·API 키를 uvicorn 프로세스에도 로드 (Streamlit config.settings와 동일)

from fastapi import Depends, FastAPI, Request, Form
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from web.auth import (
    AUTH_COOKIE, COOKIE_MAX_AGE, COOKIE_SECURE,
    verify_login, make_cookie_value,
)
from web.deps import get_current_user, optional_user
from urllib.parse import quote

from web.services import (
    market, paper as paper_svc, hot as hot_svc, ml as ml_svc, weekly as weekly_svc,
    backtest as bt_svc, journal as journal_svc, alerts as alerts_svc, tracker as tracker_svc,
    portfolio as pf_svc, analysts as an_svc, admin as admin_svc,
    portfolio_analysis as pfa_svc,
)

import os as _os

ADMIN_USER = _os.getenv("APP_USERNAME", "admin")


async def require_admin(request: Request) -> str:
    uid = await get_current_user(request)
    if uid != ADMIN_USER:
        raise StarletteHTTPException(status_code=403, detail="관리자 전용")
    return uid

_BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_BASE / "templates"))


def _num(value, spec="{:,.0f}"):
    """Python str.format 기반 숫자 포맷 필터 — Jinja 기본 format(printf)은 천단위 콤마 미지원."""
    try:
        return spec.format(value)
    except (TypeError, ValueError):
        return "-"


templates.env.filters["num"] = _num

app = FastAPI(title="Stock Agent v2")
app.mount("/static", StaticFiles(directory=str(_BASE / "static")), name="static")

# 탭 정의 (라벨만 — 내용은 Phase 1~4에서 라우트로 채움)
TABS = [
    ("tracker", "📌 내 종목"), ("paper", "🗞️ 데일리"), ("weekly", "📅 주간 리포트"),
    ("hot", "🔥 핫 섹터"), ("analysts", "🤖 분석관"), ("portfolio", "💼 포트폴리오"),
    ("journal", "📒 매매일지"), ("alerts", "🔔 가격알림"), ("backtest", "🧪 백테스트"),
    ("ml", "🧠 AI 신호"),
]


@app.exception_handler(StarletteHTTPException)
async def _auth_redirect(request: Request, exc: StarletteHTTPException):
    """401(로그인 필요)은 /login 으로 리다이렉트. 그 외는 상태코드 그대로 응답
    (핸들러 안에서 raise 하면 500이 되므로 반드시 Response를 반환)."""
    if exc.status_code == 401:
        return RedirectResponse("/login", status_code=303)
    return PlainTextResponse(str(exc.detail or ""), status_code=exc.status_code)


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, error: str = ""):
    if optional_user(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": error})


# ── 로그인 무차별 대입 방어 (IP별 실패 rate limit, 인메모리) ──
import time as _time

_login_fails: dict[str, list] = {}
LOGIN_MAX_FAILS = 5      # 창 안에서 이만큼 실패하면 차단
LOGIN_WINDOW = 300.0     # 5분 롤링 창


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")  # nginx 프록시 뒤 실제 IP
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _login_blocked(ip: str) -> bool:
    now = _time.time()
    fails = [t for t in _login_fails.get(ip, []) if now - t < LOGIN_WINDOW]
    _login_fails[ip] = fails
    return len(fails) >= LOGIN_MAX_FAILS


@app.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    ip = _client_ip(request)
    if _login_blocked(ip):
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "로그인 시도가 너무 많습니다. 5분 후 다시 시도하세요."},
            status_code=429,
        )
    if not verify_login(username, password):
        _login_fails.setdefault(ip, []).append(_time.time())
        print(f"[login] 실패 ip={ip} user={username!r}")  # 감사 로그
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "계정 정보가 일치하지 않습니다."},
            status_code=401,
        )
    _login_fails.pop(ip, None)  # 성공 시 실패 카운트 초기화
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        AUTH_COOKIE, make_cookie_value(username),
        max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax", secure=COOKIE_SECURE,
    )
    return resp


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(AUTH_COOKIE)
    return resp


def _shell_ctx(uid: str, active: str | None = None) -> dict:
    """모든 탭 페이지 공통 셸 컨텍스트 (상단바·티커테이프·F&G·탭내비)."""
    tabs = TABS + [("admin", "🔧 관리자")] if uid == ADMIN_USER else TABS
    return {
        "user_id": uid,
        "tabs": tabs,
        "active_tab": active,
        "ticker_cards": market.get_ticker_tape(),
        "fg": market.get_fear_greed(),
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    uid = optional_user(request)
    if not uid:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "dashboard.html", _shell_ctx(uid))


# ── 데일리 신문 탭 (Phase 1 파일럿) ──
@app.get("/t/paper", response_class=HTMLResponse)
async def tab_paper(request: Request, uid: str = Depends(get_current_user)):
    ctx = _shell_ctx(uid, active="paper")
    ctx.update(paper_svc.get_context())
    return templates.TemplateResponse(request, "paper.html", ctx)


@app.post("/t/paper/publish", response_class=HTMLResponse)
async def tab_paper_publish(request: Request, uid: str = Depends(get_current_user)):
    """발행 버튼 — 1면 본문 fragment만 반환 (HTMX가 #paper-body에 스왑)."""
    result = paper_svc.publish()
    ctx = {
        "paper_front_html": result["front_html"],
        "paper_time": result["time"],
        "today_dot": result["today_dot"],
        "status_msg": result["status_msg"],
    }
    return templates.TemplateResponse(request, "_paper_body.html", ctx)


# ── 핫 섹터 탭 ──
@app.get("/t/hot", response_class=HTMLResponse)
async def tab_hot(request: Request, themes: int = 1, refresh: int = 0,
                  uid: str = Depends(get_current_user)):
    ctx = _shell_ctx(uid, active="hot")
    ctx.update(hot_svc.get_context(include_themes=bool(themes), refresh=bool(refresh)))
    return templates.TemplateResponse(request, "hot.html", ctx)


@app.post("/t/hot/explain", response_class=HTMLResponse)
async def tab_hot_explain(request: Request, ticker: str = Form(...), themes: int = Form(1),
                          uid: str = Depends(get_current_user)):
    ctx = hot_svc.explain(include_themes=bool(themes), ticker=ticker)
    return templates.TemplateResponse(request, "_hot_explain.html", ctx)


@app.post("/t/hot/score", response_class=HTMLResponse)
async def tab_hot_score(request: Request, query: str = Form(""),
                        uid: str = Depends(get_current_user)):
    ctx = hot_svc.score(query)
    return templates.TemplateResponse(request, "_hot_score.html", ctx)


# ── AI 신호 탭 (표시 전용) ──
@app.get("/t/ml", response_class=HTMLResponse)
async def tab_ml(request: Request, uid: str = Depends(get_current_user)):
    ctx = _shell_ctx(uid, active="ml")
    ctx.update(ml_svc.get_context())
    return templates.TemplateResponse(request, "ml.html", ctx)


# ── 주간 리포트 탭 ──
@app.get("/t/weekly", response_class=HTMLResponse)
async def tab_weekly(request: Request, week: str = "", uid: str = Depends(get_current_user)):
    ctx = _shell_ctx(uid, active="weekly")
    ctx.update(weekly_svc.get_context(chosen=week or None))
    return templates.TemplateResponse(request, "weekly.html", ctx)


@app.post("/t/weekly/regen", response_class=HTMLResponse)
async def tab_weekly_regen(request: Request, uid: str = Depends(get_current_user)):
    ctx = weekly_svc.publish()
    ctx["this_key"] = ctx["report"].get("week_key", "") if ctx["report"].get("available") else ""
    ctx["chosen"] = ctx["this_key"]
    return templates.TemplateResponse(request, "_weekly_report.html", ctx)


# ── 백테스트 탭 ──
@app.get("/t/backtest", response_class=HTMLResponse)
async def tab_backtest(request: Request, uid: str = Depends(get_current_user)):
    ctx = _shell_ctx(uid, active="backtest")
    ctx["strategies"] = bt_svc.strategies()
    return templates.TemplateResponse(request, "backtest.html", ctx)


@app.post("/t/backtest/signal", response_class=HTMLResponse)
async def tab_backtest_signal(request: Request, horizon: int = Form(10),
                              uid: str = Depends(get_current_user)):
    return templates.TemplateResponse(request, "_bt_signal.html", {"sig": bt_svc.run_signal(horizon)})


@app.post("/t/backtest/simple", response_class=HTMLResponse)
async def tab_backtest_simple(request: Request, ticker: str = Form("NVDA"),
                              strategy: str = Form("rsi"), period: str = Form("2y"),
                              capital: int = Form(10000), rsi_buy: int = Form(30),
                              rsi_sell: int = Form(70), uid: str = Depends(get_current_user)):
    bt = bt_svc.run_simple(ticker, strategy, period, capital, rsi_buy, rsi_sell)
    return templates.TemplateResponse(request, "_bt_simple.html", {"bt": bt})


# ── 매매일지 탭 (CRUD, PRG 패턴) ──
@app.get("/t/journal", response_class=HTMLResponse)
async def tab_journal(request: Request, flash: str = "", uid: str = Depends(get_current_user)):
    from datetime import date
    ctx = _shell_ctx(uid, active="journal")
    ctx.update(journal_svc.get_context(flash=flash))
    ctx["today"] = date.today().isoformat()
    return templates.TemplateResponse(request, "journal.html", ctx)


@app.post("/t/journal/add")
async def tab_journal_add(request: Request, date: str = Form(...), ticker: str = Form(...),
                          side: str = Form("매수"), qty: str = Form(...), price: str = Form(...),
                          memo: str = Form(""), apply: str = Form(""),
                          uid: str = Depends(get_current_user)):
    try:
        flash = journal_svc.add_entry(date, ticker, side, qty, price, memo, apply == "1")
    except ValueError as e:
        flash = f"⚠️ {e}"
    return RedirectResponse(f"/t/journal?flash={quote(flash)}", status_code=303)


@app.post("/t/journal/delete")
async def tab_journal_delete(request: Request, idx: int = Form(...),
                             uid: str = Depends(get_current_user)):
    flash = journal_svc.delete_entry(idx)
    return RedirectResponse(f"/t/journal?flash={quote(flash)}", status_code=303)


# ── 가격 알림 탭 (CRUD, PRG + HTMX) ──
def _redir_alerts(flash: str) -> RedirectResponse:
    return RedirectResponse(f"/t/alerts?flash={quote(flash)}", status_code=303)


@app.get("/t/alerts", response_class=HTMLResponse)
async def tab_alerts(request: Request, flash: str = "", uid: str = Depends(get_current_user)):
    ctx = _shell_ctx(uid, active="alerts")
    ctx.update(alerts_svc.get_context())
    ctx["flash"] = flash
    return templates.TemplateResponse(request, "alerts.html", ctx)


@app.post("/t/alerts/briefing-toggle")
async def alerts_briefing_toggle(request: Request, on: str = Form(""), uid: str = Depends(get_current_user)):
    return _redir_alerts(alerts_svc.toggle_briefing(on == "1"))


@app.post("/t/alerts/watchlist-toggle")
async def alerts_watchlist_toggle(request: Request, on: str = Form(""), uid: str = Depends(get_current_user)):
    return _redir_alerts(alerts_svc.toggle_watchlist_alert(on == "1"))


@app.post("/t/alerts/watchlist/add")
async def alerts_watch_add(request: Request, ticker: str = Form(""), uid: str = Depends(get_current_user)):
    return _redir_alerts(alerts_svc.add_watch(ticker))


@app.post("/t/alerts/watchlist/remove")
async def alerts_watch_remove(request: Request, ticker: str = Form(...), uid: str = Depends(get_current_user)):
    return _redir_alerts(alerts_svc.remove_watch(ticker))


@app.post("/t/alerts/add")
async def alerts_add(request: Request, ticker: str = Form(...), condition: str = Form(...),
                     value: float = Form(...), uid: str = Depends(get_current_user)):
    return _redir_alerts(alerts_svc.add_manual(ticker, condition, value))


@app.post("/t/alerts/reenable")
async def alerts_reenable(request: Request, id: int = Form(...), uid: str = Depends(get_current_user)):
    return _redir_alerts(alerts_svc.reenable(id))


@app.post("/t/alerts/remove")
async def alerts_remove(request: Request, id: int = Form(...), uid: str = Depends(get_current_user)):
    return _redir_alerts(alerts_svc.remove(id))


@app.post("/t/alerts/buy-timings", response_class=HTMLResponse)
async def alerts_buy_timings(request: Request, uid: str = Depends(get_current_user)):
    return templates.TemplateResponse(request, "_alert_buys.html", alerts_svc.buy_timings())


@app.post("/t/alerts/check", response_class=HTMLResponse)
async def alerts_check(request: Request, uid: str = Depends(get_current_user)):
    return templates.TemplateResponse(request, "_alert_check.html", alerts_svc.check_now())


# ── 내 종목 트래커 탭 ──
@app.get("/t/tracker", response_class=HTMLResponse)
async def tab_tracker(request: Request, uid: str = Depends(get_current_user)):
    ctx = _shell_ctx(uid, active="tracker")
    ctx.update(tracker_svc.get_context())
    return templates.TemplateResponse(request, "tracker.html", ctx)


@app.post("/t/tracker/briefing", response_class=HTMLResponse)
async def tab_tracker_briefing(request: Request, uid: str = Depends(get_current_user)):
    form = await request.form()
    tickers = form.getlist("tickers")
    return templates.TemplateResponse(request, "_tracker_briefing.html", tracker_svc.briefing(tickers))


@app.post("/t/tracker/eval", response_class=HTMLResponse)
async def tab_tracker_eval(request: Request, stance: str = Form("aggressive"),
                           force: str = Form("0"), uid: str = Depends(get_current_user)):
    return templates.TemplateResponse(request, "_tracker_eval.html",
                                      tracker_svc.ai_eval(stance, force == "1"))


# ── 포트폴리오 탭 (핵심 관리, PRG) ──
def _redir_pf(flash: str) -> RedirectResponse:
    return RedirectResponse(f"/t/portfolio?flash={quote(flash)}", status_code=303)


@app.get("/t/portfolio", response_class=HTMLResponse)
async def tab_portfolio(request: Request, flash: str = "", uid: str = Depends(get_current_user)):
    ctx = _shell_ctx(uid, active="portfolio")
    ctx.update(pf_svc.get_context())
    ctx["flash"] = flash
    ctx["pchat_history"] = pfa_svc.pchat_history(uid)
    return templates.TemplateResponse(request, "portfolio.html", ctx)


@app.post("/t/portfolio/sample")
async def pf_sample(request: Request, uid: str = Depends(get_current_user)):
    return _redir_pf(pf_svc.create_sample())


@app.post("/t/portfolio/add")
async def pf_add(request: Request, name: str = Form(""), qty: str = Form(""), avg: str = Form(""),
                 uid: str = Depends(get_current_user)):
    return _redir_pf(pf_svc.add_holding(name, qty, avg))


@app.post("/t/portfolio/save")
async def pf_save(request: Request, uid: str = Depends(get_current_user)):
    form = await request.form()
    flash = pf_svc.save_edits(form.getlist("ticker"), form.getlist("name"),
                              form.getlist("quantity"), form.getlist("avg_price"))
    return _redir_pf(flash)


@app.post("/t/portfolio/delete")
async def pf_delete(request: Request, uid: str = Depends(get_current_user)):
    form = await request.form()
    return _redir_pf(pf_svc.delete_holdings(form.getlist("tickers")))


@app.post("/t/portfolio/update-prices")
async def pf_update_prices(request: Request, uid: str = Depends(get_current_user)):
    return _redir_pf(pf_svc.update_prices())


@app.post("/t/portfolio/cash")
async def pf_cash(request: Request, krw: str = Form("0"), usd: str = Form("0"),
                  uid: str = Depends(get_current_user)):
    return _redir_pf(pf_svc.save_cash(krw, usd))


@app.post("/t/portfolio/seed")
async def pf_seed(request: Request, seed: str = Form("0"), risk: str = Form("1.0"),
                  uid: str = Depends(get_current_user)):
    return _redir_pf(pf_svc.save_seed(seed, risk))


@app.post("/t/portfolio/record-sells")
async def pf_record_sells(request: Request, action: str = Form("record"),
                          uid: str = Depends(get_current_user)):
    if action == "skip":
        return _redir_pf(pf_svc.skip_sells())
    form = await request.form()
    prices = {k[len("price_"):]: float(v) for k, v in form.items()
              if k.startswith("price_") and v}
    return _redir_pf(pf_svc.record_sells(prices))


# ── 포트폴리오 분석 서브탭 (온디맨드 HTMX) ──
@app.post("/t/portfolio/analyze", response_class=HTMLResponse)
async def pf_analyze(request: Request, uid: str = Depends(get_current_user)):
    return templates.TemplateResponse(request, "_pf_analyze.html", pfa_svc.analyze())


@app.post("/t/portfolio/viz", response_class=HTMLResponse)
async def pf_viz(request: Request, uid: str = Depends(get_current_user)):
    return templates.TemplateResponse(request, "_pf_viz.html", pfa_svc.viz())


@app.post("/t/portfolio/alerts", response_class=HTMLResponse)
async def pf_alerts_analysis(request: Request, uid: str = Depends(get_current_user)):
    return templates.TemplateResponse(request, "_pf_alerts.html", pfa_svc.alerts())


@app.post("/t/portfolio/rebalance", response_class=HTMLResponse)
async def pf_rebalance(request: Request, uid: str = Depends(get_current_user)):
    return templates.TemplateResponse(request, "_pf_rebalance.html", pfa_svc.rebalance())


@app.post("/t/portfolio/action-plan", response_class=HTMLResponse)
async def pf_action_plan(request: Request, deploy: float = Form(100),
                         uid: str = Depends(get_current_user)):
    return templates.TemplateResponse(request, "_pf_actionplan.html", pfa_svc.action_plan(deploy))


@app.post("/t/portfolio/chat", response_class=HTMLResponse)
async def pf_chat(request: Request, query: str = Form(...), uid: str = Depends(get_current_user)):
    msgs = pfa_svc.personalized_chat(uid, query)
    return templates.TemplateResponse(request, "_chat_history.html",
                                      {"messages": msgs, "post_url": "/t/portfolio/chat", "chat_id": "pf-chat"})


# ── 분석관 탭 (진입점검 규칙기반 + RAG/기술/뉴스/종합 LLM) ──
def _chat_ctx(kind: str, messages: list) -> dict:
    return {"messages": messages, "post_url": f"/t/analysts/{kind}", "chat_id": f"{kind}-chat"}


@app.get("/t/analysts", response_class=HTMLResponse)
async def tab_analysts(request: Request, uid: str = Depends(get_current_user)):
    from modules.portfolio_advisor import PERSONAS
    ctx = _shell_ctx(uid, active="analysts")
    ctx["personas"] = [{"key": k, "label": v["label"]} for k, v in PERSONAS.items()]
    ctx["default_stance"] = "expert" if "expert" in PERSONAS else next(iter(PERSONAS))
    ctx["rag_history"] = an_svc.history(uid, "rag")
    ctx["tech_history"] = an_svc.history(uid, "tech")
    ctx["comp_history"] = an_svc.history(uid, "comp")
    return templates.TemplateResponse(request, "analysts.html", ctx)


@app.post("/t/analysts/entry", response_class=HTMLResponse)
async def an_entry(request: Request, ticker: str = Form(""), stance: str = Form("expert"),
                   uid: str = Depends(get_current_user)):
    res = an_svc.entry_check(ticker, stance)
    return templates.TemplateResponse(request, "_entry_result.html",
                                      {"res": res, "error": res.get("error")})


@app.post("/t/analysts/rag", response_class=HTMLResponse)
async def an_rag(request: Request, query: str = Form(...), uid: str = Depends(get_current_user)):
    msgs = an_svc.rag_chat(uid, query)
    return templates.TemplateResponse(request, "_chat_history.html", _chat_ctx("rag", msgs))


@app.post("/t/analysts/tech", response_class=HTMLResponse)
async def an_tech(request: Request, query: str = Form(...), uid: str = Depends(get_current_user)):
    msgs = an_svc.tech_chat(uid, query)
    return templates.TemplateResponse(request, "_chat_history.html", _chat_ctx("tech", msgs))


@app.post("/t/analysts/comp", response_class=HTMLResponse)
async def an_comp(request: Request, query: str = Form(...), uid: str = Depends(get_current_user)):
    form = await request.form()
    agents = form.getlist("agents")
    msgs = an_svc.comprehensive_chat(uid, query, agents)
    return templates.TemplateResponse(request, "_chat_history.html", _chat_ctx("comp", msgs))


@app.post("/t/analysts/news", response_class=HTMLResponse)
async def an_news(request: Request, ticker: str = Form("NVDA"), max_news: int = Form(10),
                  uid: str = Depends(get_current_user)):
    return templates.TemplateResponse(request, "_news_result.html", an_svc.news_analyze(ticker, max_news))


# ── 관리자 탭 (admin 전용) ──
def _redir_admin(flash: str) -> RedirectResponse:
    return RedirectResponse(f"/t/admin?flash={quote(flash)}", status_code=303)


@app.get("/t/admin", response_class=HTMLResponse)
async def tab_admin(request: Request, flash: str = "", uid: str = Depends(require_admin)):
    ctx = _shell_ctx(uid, active="admin")
    ctx.update(admin_svc.get_context())
    ctx["flash"] = flash
    return templates.TemplateResponse(request, "admin.html", ctx)


@app.post("/t/admin/event/add")
async def admin_event_add(request: Request, date: str = Form(...), title: str = Form(""),
                          uid: str = Depends(require_admin)):
    return _redir_admin(admin_svc.add_event(date, title))


@app.post("/t/admin/event/remove")
async def admin_event_remove(request: Request, index: int = Form(...),
                             uid: str = Depends(require_admin)):
    return _redir_admin(admin_svc.remove_event(index))


@app.post("/t/admin/republish-paper")
async def admin_republish(request: Request, uid: str = Depends(require_admin)):
    return _redir_admin(admin_svc.force_republish_paper())


@app.post("/t/admin/clear-caches")
async def admin_clear_caches(request: Request, uid: str = Depends(require_admin)):
    return _redir_admin(admin_svc.clear_web_caches())


@app.post("/t/admin/refresh-alerts", response_class=HTMLResponse)
async def admin_refresh_alerts(request: Request, uid: str = Depends(require_admin)):
    r = admin_svc.force_refresh_alerts()
    return HTMLResponse(f"<div class='toast'>{r['msg']}</div>")


# ── 아직 이전 안 된 탭 — 셸만 표시 (플레이스홀더) ──
@app.get("/t/{tab_key}", response_class=HTMLResponse)
async def tab_placeholder(request: Request, tab_key: str, uid: str = Depends(get_current_user)):
    label = dict(TABS).get(tab_key)
    if not label:
        return PlainTextResponse("Not Found", status_code=404)
    ctx = _shell_ctx(uid, active=tab_key)
    ctx["tab_label"] = label
    return templates.TemplateResponse(request, "tab_todo.html", ctx)


@app.get("/healthz")
async def healthz():
    return {"ok": True}
