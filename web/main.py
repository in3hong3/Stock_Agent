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
from web.services import market, paper as paper_svc

_BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_BASE / "templates"))

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
