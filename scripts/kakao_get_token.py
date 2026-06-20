"""
카카오톡 '나에게 보내기' 최초 토큰 발급 (1회만 실행).

[사전 준비 — 카카오 디벨로퍼스 https://developers.kakao.com]
1. 내 애플리케이션 → 앱 생성 (또는 기존 앱)
2. [앱 키] → REST API 키 복사
3. [카카오 로그인] → 활성화 ON
4. [카카오 로그인] → Redirect URI 등록:  http://localhost:8000/oauth
5. [카카오 로그인] → 동의항목 → "카카오톡 메시지 전송(talk_message)" 선택 동의 ON

[실행]
    python scripts/kakao_get_token.py

브라우저가 열리면 카카오 로그인 → 동의 → 자동으로 refresh token이 출력된다.
출력된 KAKAO_REST_API_KEY / KAKAO_REFRESH_TOKEN 을 .env에 붙여넣으면 끝.
"""
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import requests

# .env 로드 (KAKAO_REST_API_KEY / KAKAO_CLIENT_SECRET 읽기)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

REDIRECT_URI = "http://localhost:8000/oauth"
_auth_code = {}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        if "code" in q:
            _auth_code["code"] = q["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("✅ 인증 완료! 터미널로 돌아가세요. 이 창은 닫아도 됩니다.".encode("utf-8"))
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, *args):
        pass  # 콘솔 로그 억제


def main():
    rest_key = os.getenv("KAKAO_REST_API_KEY") or input("REST API 키를 입력하세요: ").strip()
    if not rest_key:
        print("REST API 키가 필요합니다.")
        sys.exit(1)

    # 1) 인가 코드 요청 (브라우저)
    auth_url = (
        "https://kauth.kakao.com/oauth/authorize"
        f"?client_id={rest_key}&redirect_uri={REDIRECT_URI}"
        "&response_type=code&scope=talk_message"
    )
    print("\n브라우저에서 카카오 로그인 + 동의를 진행하세요...")
    print(f"(자동으로 안 열리면 직접 접속: {auth_url})\n")
    webbrowser.open(auth_url)

    # 2) 로컬 서버로 redirect 받기
    server = HTTPServer(("localhost", 8000), _Handler)
    while "code" not in _auth_code:
        server.handle_request()
    code = _auth_code["code"]
    print(f"인가 코드 수신 완료.")

    # 3) 코드 → 토큰 교환 (Client Secret 활성화 시 함께 전송)
    token_data = {
        "grant_type": "authorization_code",
        "client_id": rest_key,
        "redirect_uri": REDIRECT_URI,
        "code": code,
    }
    client_secret = os.getenv("KAKAO_CLIENT_SECRET")
    if client_secret:
        token_data["client_secret"] = client_secret
    r = requests.post("https://kauth.kakao.com/oauth/token", data=token_data, timeout=10)
    data = r.json()
    if "refresh_token" not in data:
        print(f"❌ 토큰 발급 실패: {data}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✅ 발급 완료! 아래를 .env 파일에 추가하세요:")
    print("=" * 60)
    print(f"KAKAO_REST_API_KEY={rest_key}")
    print(f"KAKAO_REFRESH_TOKEN={data['refresh_token']}")
    if client_secret:
        print(f"KAKAO_CLIENT_SECRET={client_secret}")
    print("=" * 60)
    print(f"\n(access token은 앱이 자동 갱신합니다. refresh token은 보통 2개월 유지)")


if __name__ == "__main__":
    main()
