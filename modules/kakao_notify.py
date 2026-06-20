"""
카카오톡 '나에게 보내기' (메모 API) 알림.

REST API 키 + refresh token 기반. access token이 6시간마다 만료되므로
refresh token으로 자동 갱신한다.

[.env 필요 항목]
  KAKAO_REST_API_KEY   = 카카오 디벨로퍼스 앱의 REST API 키
  KAKAO_REFRESH_TOKEN  = 최초 1회 OAuth 인증으로 발급받은 refresh token
  (access token은 자동 발급/갱신되어 data/kakao_token.json에 캐시됨)

[최초 토큰 발급은 scripts/kakao_get_token.py 참고]
"""
import os
import json
import time
from typing import List, Dict, Any, Optional

import requests

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOKEN_CACHE = os.path.join(_BASE_DIR, "data", "kakao_token.json")

_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
_MEMO_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


def _load_cached_token() -> Dict[str, Any]:
    try:
        with open(_TOKEN_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cached_token(data: Dict[str, Any]):
    os.makedirs(os.path.dirname(_TOKEN_CACHE), exist_ok=True)
    with open(_TOKEN_CACHE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _refresh_access_token() -> Optional[str]:
    """refresh token으로 새 access token 발급. 성공 시 토큰 문자열 반환."""
    rest_key = os.getenv("KAKAO_REST_API_KEY")
    refresh_token = os.getenv("KAKAO_REFRESH_TOKEN") or _load_cached_token().get("refresh_token")
    if not rest_key or not refresh_token:
        print("⚠️ 카카오 환경변수 미설정 (KAKAO_REST_API_KEY / KAKAO_REFRESH_TOKEN)")
        return None

    try:
        r = requests.post(_TOKEN_URL, data={
            "grant_type": "refresh_token",
            "client_id": rest_key,
            "refresh_token": refresh_token,
        }, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"카카오 토큰 갱신 실패: {e}")
        return None

    access_token = data.get("access_token")
    if not access_token:
        print(f"카카오 토큰 갱신 응답에 access_token 없음: {data}")
        return None

    cache = _load_cached_token()
    cache["access_token"] = access_token
    cache["expires_at"] = time.time() + int(data.get("expires_in", 21600)) - 300  # 5분 여유
    # 카카오가 refresh_token도 새로 줄 때만 갱신 (보통 1개월 이상 유지)
    if data.get("refresh_token"):
        cache["refresh_token"] = data["refresh_token"]
    _save_cached_token(cache)
    return access_token


def _get_access_token() -> Optional[str]:
    """유효한 access token 반환 (캐시 우선, 만료 시 자동 갱신)."""
    cache = _load_cached_token()
    if cache.get("access_token") and cache.get("expires_at", 0) > time.time():
        return cache["access_token"]
    return _refresh_access_token()


def send_kakao_memo(text: str, link_url: str = "http://161.33.6.231/") -> bool:
    """나에게 보내기 — 텍스트 메모 1건 발송. 성공 시 True."""
    token = _get_access_token()
    if not token:
        return False

    template = {
        "object_type": "text",
        "text": text[:1000],  # 카카오 텍스트 메모 길이 제한
        "link": {"web_url": link_url, "mobile_web_url": link_url},
        "button_title": "앱에서 보기",
    }
    try:
        r = requests.post(
            _MEMO_URL,
            headers={"Authorization": f"Bearer {token}"},
            data={"template_object": json.dumps(template, ensure_ascii=False)},
            timeout=10,
        )
        if r.status_code == 401:
            # 토큰 만료/무효 → 1회 강제 갱신 후 재시도
            token = _refresh_access_token()
            if not token:
                return False
            r = requests.post(
                _MEMO_URL,
                headers={"Authorization": f"Bearer {token}"},
                data={"template_object": json.dumps(template, ensure_ascii=False)},
                timeout=10,
            )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"카카오 메모 발송 실패: {e}")
        return False


def send_alert_kakao(triggered: List[Dict[str, Any]], condition_types: Dict[str, str]) -> bool:
    """가격 알림을 카카오톡 '나에게 보내기'로 전송."""
    if not triggered:
        return False
    lines = ["🔔 Stock Agent 가격 알림"]
    for t in triggered:
        cond = condition_types.get(t["condition"], t["condition"])
        lines.append(f"• {t['ticker']} — {cond} (기준 {t['value']} / 현재 {t['current_value']})")
    lines.append("\n앱에서 확인하세요.")
    return send_kakao_memo("\n".join(lines))


def is_configured() -> bool:
    """카카오 알림 설정 여부 (키 + refresh token 존재)."""
    has_key = bool(os.getenv("KAKAO_REST_API_KEY"))
    has_refresh = bool(os.getenv("KAKAO_REFRESH_TOKEN") or _load_cached_token().get("refresh_token"))
    return has_key and has_refresh
