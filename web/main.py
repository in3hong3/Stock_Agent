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
    backtest as bt_svc, journal as journal_svc,
)

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


@app.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if not verify_login(username, password):
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "계정 정보가 일치하지 않습니다."},
            status_code=401,
        )
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
    return {
        "user_id": uid,
        "tabs": TABS,
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
