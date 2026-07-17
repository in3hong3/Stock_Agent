"""FastAPI 인증 — 기존 Streamlit(ui/components.py)과 동일한 서명 토큰 스킴.

같은 salt('stockagent-v1')·같은 해시·같은 쿠키 이름(sa_auth)을 써서
두 앱이 로그인 쿠키를 공유한다 (전환 기간에 한쪽에서 로그인하면 다른 쪽도 유지).
"""
import hashlib
import os

AUTH_COOKIE = "sa_auth"
# 쿠키 Secure 플래그 — HTTPS 붙기 전까지는 0(로컬 개발). 도메인+certbot 후 서버 env로 1.
COOKIE_SECURE = os.getenv("WEB_COOKIE_SECURE", "0") == "1"
COOKIE_MAX_AGE = 30 * 24 * 3600  # 30일 (Streamlit과 동일)


def accounts() -> dict:
    """계정 목록 (환경변수 또는 기본값) — ui/components._get_accounts와 동일."""
    return {
        os.getenv("APP_USERNAME", "admin"): os.getenv("APP_PASSWORD", "admin"),
        "song": os.getenv("APP_PASSWORD_SONG", "song"),
    }


def auth_token(username: str) -> str:
    """비밀번호 기반 서명 토큰 (ui/components._auth_token과 완전 동일)."""
    pw = accounts().get(username, "")
    return hashlib.sha256(f"{username}:{pw}:stockagent-v1".encode()).hexdigest()[:20]


def verify_login(username: str, password: str) -> bool:
    accts = accounts()
    return username in accts and password == accts.get(username)


def make_cookie_value(username: str) -> str:
    """쿠키에 저장할 값 'username:token' (Streamlit set_login_cookie와 동일 포맷)."""
    return f"{username}:{auth_token(username)}"


def user_from_cookie(raw: str | None) -> str | None:
    """쿠키 값을 검증해 사용자 ID를 돌려준다. 위조/없음이면 None."""
    if raw and ":" in str(raw):
        u, t = str(raw).split(":", 1)
        if u in accounts() and t == auth_token(u):
            return u
    return None
