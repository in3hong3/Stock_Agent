"""
매일 카카오 데일리 브리핑 (cron 1회).
매크로 + 내 자산 + 매매 시그널(오늘 할 일) + 보유종목 뉴스 헤드라인을
하나의 카카오톡 메시지로 묶어 '나에게 보내기'로 발송한다.

- LLM 호출 없음 (전부 규칙 기반·무료 데이터) → 비용 0
- 카카오 텍스트 메모 1000자 제한에 맞춰 압축
- 대상 사용자: STOCK_AGENT_USER 환경변수 (기본 admin)

[실행]
    STOCK_AGENT_USER=admin python scripts/daily_kakao_briefing.py
[cron 예]
    0 7 * * 1-5  cd ~/stock-agent && STOCK_AGENT_USER=admin ./.venv/bin/python scripts/daily_kakao_briefing.py >> logs/kakao_briefing.log 2>&1
"""
import os
import sys
from datetime import datetime

# 프로젝트 루트를 path에 + .env 로드
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except ImportError:
    pass

# 대상 사용자 고정 (세션 없으므로)
os.environ.setdefault("STOCK_AGENT_USER", "admin")

LINK = "http://161.33.6.231/"
LIMIT = 3500  # 카카오 텍스트 메모 길이 (2000자+ 발송 확인됨)


def _strip_md(text: str) -> str:
    """마크다운을 카카오톡 평문으로 정리."""
    import re
    lines = []
    for ln in text.splitlines():
        s = ln.rstrip()
        if s.strip() in ("---", "***", "___"):
            continue
        # 헤더(##) → 굵게 표시 대신 그냥 텍스트 (앞에 ▸)
        s = re.sub(r"^\s*#{1,6}\s*", "▸ ", s)
        # 볼드/이탤릭 마크 제거
        s = s.replace("**", "").replace("__", "")
        s = re.sub(r"\*(.+?)\*", r"\1", s)
        # 링크 [텍스트](url) → 텍스트
        s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
        # 표 구분선 제거
        if re.match(r"^\s*\|?\s*:?-{2,}", s):
            continue
        lines.append(s)
    out = "\n".join(lines)
    # 연속 빈 줄 압축
    import re as _re
    return _re.sub(r"\n{3,}", "\n\n", out).strip()


def build_briefing() -> str:
    from modules.issue_tracker import get_portfolio_holdings
    from modules.event_calendar import get_all_events, get_upcoming_events
    from modules.daily_paper import get_saved_paper

    today = datetime.now().strftime("%m/%d (%a)")
    parts = [f"📊 Stock Agent 데일리 · {today}"]

    holdings = get_portfolio_holdings()
    tickers = [h["ticker"] for h in holdings]

    # ── 📅 오늘/이번주 일정 (오늘 무슨 일이 있을까) ──
    try:
        events = get_all_events(tickers)
        upcoming = get_upcoming_events(events, days=14)
        if upcoming:
            lines = []
            for ev in upcoming[:6]:
                d_day = "오늘" if ev["d_day"] == 0 else f"D-{ev['d_day']}"
                lines.append(f"• {d_day} ({ev['date'].strftime('%m/%d')}) {ev['title']}")
            parts.append("\n📅 다가오는 일정\n" + "\n".join(lines))
        else:
            parts.append("\n📅 다가오는 일정\n• 2주 내 예정된 주요 일정 없음")
    except Exception as e:
        print(f"일정 실패: {e}")

    # ── 🗞️ 시황 브리핑 (어제~오늘 무슨 일이 있었나 — 데일리 신문 그대로) ──
    try:
        paper = get_saved_paper()
        front = paper.get("front", "")
        if front:
            # 검색 출처(URL 목록) 섹션 이후는 잘라냄 — 카카오엔 불필요
            import re as _re
            front = _re.split(r"\n#{0,6}\s*📎?\s*검색 출처", front)[0]
            front = _re.split(r"\n-{3,}\s*\n\s*\*?\*?📎", front)[0]
            clean = _strip_md(front)
            # 본문 내 인용 표시 [1][2] 제거 (출처 뺐으므로 의미 없음)
            clean = _re.sub(r"\[\d+\](\[\d+\])*", "", clean)
            parts.append("\n🗞️ 시황 브리핑\n" + clean)
        else:
            parts.append("\n🗞️ 시황 브리핑\n• 오늘 신문이 아직 발행 전입니다. 앱에서 발행하세요.")
    except Exception as e:
        print(f"시황 실패: {e}")

    parts.append(f"\n📲 전체 보기 → {LINK}")

    text = "\n".join(parts)
    if len(text) > LIMIT:
        text = text[:LIMIT - 25].rstrip() + f"\n…\n📲 전체 → {LINK}"
    return text


def main():
    from modules.kakao_notify import is_configured, send_kakao_memo
    from ui.pages._meta import load_meta

    # 이 계정이 '브리핑 받기'를 켰는지 확인 (가격 알림 탭의 토글)
    if not load_meta().get("kakao_briefing_enabled", False):
        user = os.getenv("STOCK_AGENT_USER", "admin")
        print(f"ℹ️ {user} 계정이 브리핑 받기 OFF — 발송 생략")
        sys.exit(0)

    if not is_configured():
        print("⚠️ 카카오 미설정 (.env에 KAKAO_* 키 필요)")
        sys.exit(1)

    text = build_briefing()
    print("─" * 50)
    print(text)
    print("─" * 50)
    ok = send_kakao_memo(text)
    print("발송:", "✅ 성공" if ok else "❌ 실패")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
