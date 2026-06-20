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
LIMIT = 980  # 카카오 텍스트 메모 안전 길이


def _fmt_won(v):
    return f"₩{v:,.0f}"


def build_briefing() -> str:
    from modules.issue_tracker import get_portfolio_holdings, get_usdkrw_rate, fetch_ticker_news
    from modules.market_overview import get_macro_data
    from modules.trade_signal import generate_signals

    today = datetime.now().strftime("%m/%d (%a)")
    parts = [f"📊 Stock Agent 데일리 · {today}"]

    holdings = get_portfolio_holdings()
    fx = get_usdkrw_rate() or 1400.0

    # ── 시장(매크로) 한 줄 ──
    try:
        macro = get_macro_data()
        pick = {m["name"].split(" ")[-1].strip("()"): m for m in macro}
        wanted = ["S&P", "나스닥", "VIX", "원/달러"]
        seg = []
        for m in macro:
            nm = m["name"]
            if any(w in nm for w in ["S&P 500", "나스닥", "VIX", "원/달러"]) and m.get("change_pct") is not None:
                short = nm.split(" ", 1)[-1] if " " in nm else nm
                seg.append(f"{short} {m['change_pct']:+.1f}%")
            if len(seg) >= 4:
                break
        if seg:
            parts.append("\n🌍 시장\n" + " · ".join(seg))
    except Exception as e:
        print(f"매크로 실패: {e}")

    # ── 내 자산 ──
    try:
        stock_eval = stock_cost = 0.0
        for h in holdings:
            qty = float(h.get("quantity", 0) or 0)
            cur = float(h.get("current_price", 0) or 0)
            avg = float(h.get("avg_price", 0) or 0)
            is_kr = str(h["ticker"]).endswith((".KS", ".KQ"))
            factor = 1.0 if is_kr else fx
            stock_eval += qty * cur * factor
            stock_cost += qty * avg * factor
        pnl = stock_eval - stock_cost
        pnl_rate = (pnl / stock_cost * 100) if stock_cost > 0 else 0
        if stock_eval > 0:
            parts.append(f"\n💰 내 주식 {_fmt_won(stock_eval)} (평가손익 {pnl_rate:+.1f}%)")
    except Exception as e:
        print(f"자산 실패: {e}")

    # ── 오늘 할 일 (매매 시그널 — 액션 있는 것 우선) ──
    try:
        result = generate_signals(holdings, "expert", 0, 1.0)
        actionable = [s for s in result["signals"] if s.get("action") not in ("관망",)]
        actionable = actionable or result["signals"]
        lines = []
        for s in actionable[:5]:
            pr = s.get("profit_rate")
            pr_s = f" {pr:+.0f}%" if pr is not None else ""
            lines.append(f"{s['icon']} {s['ticker']} {s['action']}{pr_s}")
        if lines:
            parts.append("\n🎯 오늘 할 일\n" + "\n".join(lines))
    except Exception as e:
        print(f"시그널 실패: {e}")

    # ── 보유종목 주요 뉴스 헤드라인 ──
    try:
        news_lines = []
        for h in holdings[:4]:
            items = fetch_ticker_news(h["ticker"], max_news=1)
            if items:
                title = items[0]["title"][:42]
                news_lines.append(f"• [{h['ticker']}] {title}")
            if len(news_lines) >= 4:
                break
        if news_lines:
            parts.append("\n📰 주요 뉴스\n" + "\n".join(news_lines))
    except Exception as e:
        print(f"뉴스 실패: {e}")

    parts.append(f"\n전체 보기 → {LINK}")

    text = "\n".join(parts)
    if len(text) > LIMIT:
        text = text[:LIMIT - 20].rstrip() + f"\n…전체 → {LINK}"
    return text


def main():
    from modules.kakao_notify import is_configured, send_kakao_memo

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
