"""
daily_briefing.py
매일 22:30에 실행되는 미장 프리뷰 이메일 리포트 스크립트.

실행 방법:
  python daily_briefing.py

이메일 설정:
  .env 파일에 아래 항목을 추가하세요.
    BRIEFING_FROM_EMAIL=your_gmail@gmail.com
    BRIEFING_APP_PASSWORD=xxxx xxxx xxxx xxxx   # Gmail 앱 비밀번호 (일반 비밀번호 X)
    BRIEFING_TO_EMAIL=receive@example.com
"""

import os
import sys
import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()


# ──────────────────────────────
# 1. 데이터 수집 함수들
# ──────────────────────────────

def get_market_summary() -> dict:
    """Fear & Greed + 주요 지수 수집"""
    result = {
        "fg_index": "N/A", "fg_status": "N/A",
        "kospi": "N/A", "nasdaq": "N/A", "sp500": "N/A",
        "krw_usd": "N/A", "bitcoin": "N/A"
    }
    try:
        from main import CNNScraper, MarketDataCollector
        fg_val, fg_status = CNNScraper.get_fear_and_greed_index()
        if fg_val != -1:
            result["fg_index"] = fg_val
            result["fg_status"] = fg_status

        prices = MarketDataCollector.get_latest_prices()
        result.update({
            "kospi":   prices.get("kospi", "N/A"),
            "nasdaq":  prices.get("nasdaq", "N/A"),
            "sp500":   prices.get("sp500", "N/A"),
            "krw_usd": prices.get("krw_usd", "N/A"),
            "bitcoin": prices.get("bitcoin", "N/A"),
        })
    except Exception as e:
        print(f"  [시장 데이터 오류] {e}")
    return result


def get_recent_rag_insights(days: int = 3) -> str:
    """최근 N일 유튜브 영상을 RAG로 요약"""
    try:
        from agents.rag_agent import RAGAgent
        from config.settings import AGENT_REGISTRY

        rag_config = next(
            (v for v in AGENT_REGISTRY.values() if v.get("type") == "rag"),
            {}
        )
        agent = RAGAgent(
            agent_id=rag_config.get("id", "rag_default"),
            name=rag_config.get("name", "RAG"),
            description=rag_config.get("description", ""),
            channel_id=rag_config.get("channel_id"),
        )

        today = datetime.date.today()
        start = today - datetime.timedelta(days=days)
        query = (
            f"{start.strftime('%Y-%m-%d')} ~ {today.strftime('%Y-%m-%d')} 사이에 "
            "올라온 영상들을 기반으로, 현재 시장에서 가장 주목해야 할 이슈 3가지를 "
            "각각 종목명/이슈명, 핵심 내용, 투자 포인트 형식으로 간결하게 정리해줘."
        )
        result = agent.process(query=query)
        return result.get("answer", "인사이트를 생성하지 못했습니다.")

    except Exception as e:
        print(f"  [RAG 오류] {e}")
        return f"RAG 인사이트 수집 실패: {e}"


def get_portfolio_summary() -> str:
    """포트폴리오 현황 간단 요약"""
    try:
        import pandas as pd
        portfolio_file = os.path.join(os.path.dirname(__file__), "data", "portfolio.csv")
        if not os.path.exists(portfolio_file):
            return "포트폴리오 파일 없음"

        df = pd.read_csv(portfolio_file)
        if df.empty:
            return "포트폴리오 데이터 없음"

        df["eval"] = df["quantity"] * df["current_price"]
        df["cost"] = df["quantity"] * df["avg_price"]
        df["pnl"] = df["eval"] - df["cost"]
        df["rate"] = (df["pnl"] / df["cost"] * 100).round(2)

        total_eval = df["eval"].sum()
        total_cost = df["cost"].sum()
        total_pnl = df["pnl"].sum()
        total_rate = ((total_eval - total_cost) / total_cost * 100) if total_cost else 0

        lines = [f"  {'종목':<12} {'수익률':>8}  {'평가손익':>12}"]
        lines.append("  " + "-" * 38)
        for _, row in df.iterrows():
            arrow = "▲" if row["rate"] >= 0 else "▼"
            lines.append(f"  {row.get('name', row['ticker']):<12} {arrow}{abs(row['rate']):>6.1f}%  {row['pnl']:>+12,.0f}원")

        lines.append("  " + "-" * 38)
        total_arrow = "▲" if total_rate >= 0 else "▼"
        lines.append(f"  {'합계':<12} {total_arrow}{abs(total_rate):>6.1f}%  {total_pnl:>+12,.0f}원")
        return "\n".join(lines)

    except Exception as e:
        print(f"  [포트폴리오 오류] {e}")
        return f"포트폴리오 조회 실패: {e}"


# ──────────────────────────────
# 2. 이메일 전송
# ──────────────────────────────

def send_email(subject: str, body_html: str, body_text: str):
    """Gmail SMTP로 이메일 전송"""
    from_email = os.getenv("BRIEFING_FROM_EMAIL")
    app_password = os.getenv("BRIEFING_APP_PASSWORD")
    to_email = os.getenv("BRIEFING_TO_EMAIL")

    if not all([from_email, app_password, to_email]):
        print("  ❌ 이메일 환경변수 미설정. .env 파일을 확인하세요.")
        print("     필요한 항목: BRIEFING_FROM_EMAIL, BRIEFING_APP_PASSWORD, BRIEFING_TO_EMAIL")
        print("\n[이메일 내용 미리보기]\n")
        print(body_text)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        with smtplib.SMTP("smtp.naver.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(from_email, app_password)
            server.sendmail(from_email, to_email, msg.as_string())
        print(f"  ✅ 이메일 전송 완료 → {to_email}")
    except Exception as e:
        print(f"  ❌ 이메일 전송 실패: {e}")


# ──────────────────────────────
# 3. 리포트 조합 및 실행
# ──────────────────────────────

def build_report(market: dict, insights: str, portfolio: str, now: datetime.datetime) -> tuple:
    """텍스트 + HTML 리포트 생성"""

    fg = market["fg_index"]
    fg_status = market["fg_status"]

    # Fear & Greed 이모지
    if fg == "N/A":
        fg_emoji = "⚪"
    elif int(fg) <= 25:
        fg_emoji = "💚 극공포 (매수 기회?)"
    elif int(fg) <= 45:
        fg_emoji = "🟢 공포"
    elif int(fg) <= 55:
        fg_emoji = "⚪ 중립"
    elif int(fg) <= 75:
        fg_emoji = "🟠 탐욕"
    else:
        fg_emoji = "🔴 극탐욕 (과열 주의)"

    date_str = now.strftime("%Y-%m-%d %H:%M")

    # ── 텍스트 버전 ──
    text = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🌙 미장 프리뷰 리포트 [{date_str}]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 시장 심리 & 지수
  Fear & Greed : {fg} {fg_emoji}
  코스피        : {market['kospi']}
  나스닥        : {market['nasdaq']}
  S&P 500       : {market['sp500']}
  원달러 환율   : {market['krw_usd']}원
  비트코인      : ${market['bitcoin']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📺 최근 주요 이슈 (YouTube RAG 요약)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{insights}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💼 내 포트폴리오 현황
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{portfolio}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ⚠️ 이 리포트는 투자 권유가 아닙니다.
     최종 판단과 책임은 본인에게 있습니다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    # ── HTML 버전 ──
    insights_html = insights.replace("\n", "<br>")
    portfolio_html = portfolio.replace("\n", "<br>").replace(" ", "&nbsp;")

    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: 'Segoe UI', sans-serif; background: #0e1117; color: #e2e8f0; margin: 0; padding: 20px; }}
    .card {{ background: #1a1c24; border-radius: 12px; padding: 20px; margin-bottom: 16px; border-left: 4px solid #6366f1; }}
    h1 {{ color: #ffffff; font-size: 20px; }}
    h2 {{ color: #94a3b8; font-size: 14px; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1px; }}
    .metric {{ display: inline-block; background: #252836; border-radius: 8px; padding: 10px 16px; margin: 4px; }}
    .metric-label {{ font-size: 11px; color: #64748b; }}
    .metric-value {{ font-size: 18px; font-weight: bold; color: #ffffff; }}
    .insights {{ line-height: 1.8; color: #cbd5e1; }}
    .portfolio {{ font-family: monospace; color: #cbd5e1; font-size: 13px; }}
    .footer {{ text-align: center; color: #475569; font-size: 11px; margin-top: 20px; }}
  </style>
</head>
<body>
  <h1>🌙 미장 프리뷰 리포트 &nbsp;<small style="color:#64748b;font-size:14px;">{date_str}</small></h1>

  <div class="card">
    <h2>📊 시장 심리 & 지수</h2>
    <div class="metric"><div class="metric-label">Fear & Greed</div><div class="metric-value">{fg} {fg_emoji}</div></div>
    <div class="metric"><div class="metric-label">코스피</div><div class="metric-value">{market['kospi']}</div></div>
    <div class="metric"><div class="metric-label">나스닥</div><div class="metric-value">{market['nasdaq']}</div></div>
    <div class="metric"><div class="metric-label">S&P 500</div><div class="metric-value">{market['sp500']}</div></div>
    <div class="metric"><div class="metric-label">원달러</div><div class="metric-value">{market['krw_usd']}원</div></div>
    <div class="metric"><div class="metric-label">비트코인</div><div class="metric-value">${market['bitcoin']}</div></div>
  </div>

  <div class="card" style="border-left-color: #10b981;">
    <h2>📺 최근 주요 이슈 (YouTube RAG)</h2>
    <div class="insights">{insights_html}</div>
  </div>

  <div class="card" style="border-left-color: #f59e0b;">
    <h2>💼 내 포트폴리오</h2>
    <div class="portfolio">{portfolio_html}</div>
  </div>

  <div class="footer">⚠️ 이 리포트는 투자 권유가 아닙니다. 최종 판단과 책임은 본인에게 있습니다.</div>
</body>
</html>
"""
    return text, html


def main():
    now = datetime.datetime.now()
    print(f"\n🌙 미장 프리뷰 리포트 생성 시작 ({now.strftime('%Y-%m-%d %H:%M')})")
    print("=" * 50)

    print("  📊 시장 데이터 수집 중...")
    market = get_market_summary()

    print("  📺 RAG 인사이트 생성 중... (약 20~40초 소요)")
    insights = get_recent_rag_insights(days=3)

    print("  💼 포트폴리오 현황 조회 중...")
    portfolio = get_portfolio_summary()

    text, html = build_report(market, insights, portfolio, now)

    subject = f"🌙 [{now.strftime('%m/%d')}] 미장 프리뷰 | F&G {market['fg_index']} · 나스닥 {market['nasdaq']}"
    send_email(subject, html, text)
    print("=" * 50)
    print("✅ 완료!")


if __name__ == "__main__":
    main()
