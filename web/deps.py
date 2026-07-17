"""요청별 사용자 컨텍스트 — FastAPI Depends용.

로그인 안 됐으면 /login 으로 리다이렉트(HTML 요청) 또는 401(그 외).
전환 기간엔 utils.user_data.current_user()도 이 값을 쓰도록 contextvar를 세팅한다.
"""
from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from web.auth import AUTH_COOKIE, user_from_cookie


def get_current_user(request: Request) -> str:
    uid = user_from_cookie(request.cookies.get(AUTH_COOKIE))
    if not uid:
        # 브라우저 요청이면 로그인 페이지로, API면 401
        raise StarletteHTTPException(status_code=401, detail="login required")
    # 사용자별 데이터 경로가 이 요청 사용자를 쓰도록 바인딩 (Phase 2 CRUD에서 활용)
    try:
        from utils import user_data
        if hasattr(user_data, "set_current_user"):
            user_data.set_current_user(uid)
    except Exception:
        pass
    return uid


def optional_user(request: Request) -> str | None:
    return user_from_cookie(request.cookies.get(AUTH_COOKIE))
