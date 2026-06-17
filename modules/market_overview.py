"""
시장 종합 현황 (매크로 지표 + 시장 이슈)
달러 인덱스, 금리, VIX, 원자재 등 매크로 지표와 시장 전반 뉴스를 제공한다.
"""
import math
from typing import Dict, List, Any
import pandas as pd
import yfinance as yf

# 매크로 지표 정의: (yfinance 티커, 표시명, 단위 포맷)
MACRO_INDICATORS = [
    ("DX-Y.NYB", "💵 달러 인덱스 (DXY)", "{:.2f}"),
    ("^TNX", "🏦 미국채 10년물", "{:.2f}%"),
    ("^VIX", "😱 VIX (공포지수)", "{:.2f}"),
    ("CL=F", "🛢️ WTI 유가", "${:.2f}"),
    ("GC=F", "🥇 금 선물", "${:,.0f}"),
    ("BTC-USD", "₿ 비트코인", "${:,.0f}"),
    ("^GSPC", "🇺🇸 S&P 500", "{:,.0f}"),
    ("^IXIC", "🇺🇸 나스닥", "{:,.0f}"),
    ("^KS11", "🇰🇷 코스피", "{:,.2f}"),
    ("KRW=X", "💱 원/달러", "₩{:,.1f}"),
]

# 시장 전반 뉴스 수집용 ETF/지수
MARKET_NEWS_TICKERS = ["SPY", "QQQ", "DIA"]


def get_macro_data() -> List[Dict[str, Any]]:
    """
    매크로 지표별 현재값/등락/1개월 추세 데이터.
    Returns: [{name, value_str, change_pct, spark(list[float])}]
    """
    results = []
    for ticker, name, fmt in MACRO_INDICATORS:
        try:
            df = yf.Ticker(ticker).history(period="1mo")
            if df.empty or len(df) < 2:
                results.append({"name": name, "value_str": "N/A", "change_pct": None, "spark": []})
                continue
            # NaN 행 제거 후 마지막 두 값이 유효한지 확인
            close = df["Close"].dropna()
            if len(close) < 2:
                results.append({"name": name, "value_str": "N/A", "change_pct": None, "spark": []})
                continue
            value = float(close.iloc[-1])
            prev = float(close.iloc[-2])
            if math.isnan(value) or math.isnan(prev) or prev == 0:
                results.append({"name": name, "value_str": "N/A", "change_pct": None, "spark": []})
                continue
            change = (value / prev - 1) * 100
            spark = [round(float(v), 4) for v in close.tolist() if not math.isnan(float(v))]
            results.append({
                "name": name,
                "value_str": fmt.format(value),
                "change_pct": round(change, 2),
                "spark": spark,
            })
        except Exception as e:
            print(f"매크로 지표 실패 ({ticker}): {e}")
            results.append({"name": name, "value_str": "N/A", "change_pct": None, "spark": []})
    return results


def fetch_market_news(max_per_ticker: int = 5) -> List[Dict[str, Any]]:
    """시장 전반 뉴스 (SPY/QQQ/DIA 뉴스 합산, 중복 제목 제거)"""
    from modules.issue_tracker import fetch_ticker_news

    seen_titles = set()
    all_news = []
    for ticker in MARKET_NEWS_TICKERS:
        for n in fetch_ticker_news(ticker, max_per_ticker):
            title_key = n["title"][:60]
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                all_news.append(n)
    return all_news


def summarize_market(macro: List[Dict], news: List[Dict], model: str = "gpt-4o-mini") -> str:
    """매크로 지표 + 시장 뉴스를 종합해 오늘의 시장 브리핑 생성"""
    from openai import OpenAI
    client = OpenAI()

    macro_text = "\n".join(
        f"- {m['name']}: {m['value_str']} ({m['change_pct']:+.2f}%)"
        for m in macro if m["change_pct"] is not None
    )
    news_text = "\n".join(f"- [{n['published']}] {n['title']}" for n in news[:15])

    prompt = f"""[현재 매크로 지표]
{macro_text}

[시장 주요 뉴스 헤드라인]
{news_text}

위 데이터를 종합해 아래 형식으로 시장 브리핑을 작성해줘:

### 🌍 오늘의 시장 한 줄 요약
(핵심 분위기 1-2문장)

### 📊 매크로 체크포인트
- 달러/금리/VIX 등에서 주목할 변화와 그 의미 (2-3개)

### 📰 핵심 이슈
- 헤드라인에서 추출한 주요 이슈 2-3개와 시장 영향

### ⚠️ 리스크 요인
- 현재 지표상 주의할 점 1-2개"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "너는 매크로와 뉴스를 연결해서 해석하는 시장 전략가야. 간결하고, 숫자를 근거로 말하고, 사실과 추측을 구분해."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content
