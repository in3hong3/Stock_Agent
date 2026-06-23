"""
내 종목 이슈 트래커
보유/관심 종목을 등록하면 가격 스냅샷 + 관련 뉴스를 지속 추적한다.
종목 목록은 data/tracked_tickers.json에 저장 (포트폴리오 CSV와 독립).
"""
import os
import json
import math
import re
from typing import Dict, List, Any
from datetime import datetime

import pandas as pd
import yfinance as yf

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from utils.user_data import user_file, portfolio_path


def _tracked_file() -> str:
    return user_file("tracked_tickers.json")


def _portfolio_csv() -> str:
    return portfolio_path()

# 한글 종목명 → 티커 간편 매핑 (입력 편의)
NAME_TO_TICKER = {
    "삼성전자": "005930.KS", "삼전": "005930.KS",
    "하이닉스": "000660.KS", "sk하이닉스": "000660.KS", "하닉": "000660.KS",
    "엔비디아": "NVDA", "엔비": "NVDA",
    "테슬라": "TSLA", "테슬": "TSLA",
    "애플": "AAPL", "마이크로소프트": "MSFT", "마소": "MSFT",
    "구글": "GOOGL", "아마존": "AMZN", "메타": "META",
    "팔란티어": "PLTR", "아이온큐": "IONQ", "브로드컴": "AVGO",
    "amd": "AMD", "인텔": "INTC", "넷플릭스": "NFLX",
    "비트코인": "BTC-USD", "이더리움": "ETH-USD",
}


# ──────────────────────────────────────────────
# 종목 목록 관리
# ──────────────────────────────────────────────
def load_tracked() -> List[Dict[str, str]]:
    """[{ticker, name, added}] 리스트. 파일 없으면 portfolio.csv에서 시드."""
    if os.path.exists(_tracked_file()):
        try:
            with open(_tracked_file(), "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    # 최초 실행: 포트폴리오 CSV의 종목을 자동으로 가져옴
    seed = []
    if os.path.exists(_portfolio_csv()):
        try:
            df = pd.read_csv(_portfolio_csv())
            for _, row in df.iterrows():
                seed.append({
                    "ticker": str(row["ticker"]).strip().upper(),
                    "name": str(row.get("name", row["ticker"])),
                    "added": datetime.now().strftime("%Y-%m-%d"),
                })
        except Exception:
            pass
    save_tracked(seed)
    return seed


def save_tracked(items: List[Dict[str, str]]):
    os.makedirs(os.path.dirname(_tracked_file()), exist_ok=True)
    with open(_tracked_file(), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def resolve_ticker(user_input: str) -> str:
    """한글 종목명/티커 입력을 yfinance 티커로 변환"""
    text = user_input.strip()
    lower = text.lower()
    for name, ticker in NAME_TO_TICKER.items():
        if name.lower() == lower:
            return ticker
    # 한국 종목코드 6자리 숫자 → .KS 부착
    if re.fullmatch(r"\d{6}", text):
        return f"{text}.KS"
    return text.upper()


def add_ticker(user_input: str) -> Dict[str, Any]:
    """
    종목 추가. yfinance로 유효성 검증 후 종목명 자동 조회.
    Returns: {"success": bool, "ticker": str, "name": str, "error": str}
    """
    ticker = resolve_ticker(user_input)
    items = load_tracked()

    if any(it["ticker"] == ticker for it in items):
        return {"success": False, "error": f"{ticker}는 이미 등록되어 있습니다."}

    try:
        info = yf.Ticker(ticker)
        hist = info.history(period="5d")
        if hist.empty:
            return {"success": False, "error": f"'{user_input}' → '{ticker}' 데이터를 찾을 수 없습니다. 티커를 확인하세요."}
        name = info.info.get("shortName") or info.info.get("longName") or ticker
    except Exception:
        return {"success": False, "error": f"'{ticker}' 조회 실패. 티커를 확인하세요."}

    items.append({
        "ticker": ticker,
        "name": name,
        "added": datetime.now().strftime("%Y-%m-%d"),
    })
    save_tracked(items)
    return {"success": True, "ticker": ticker, "name": name}


def remove_ticker(ticker: str):
    items = [it for it in load_tracked() if it["ticker"] != ticker]
    save_tracked(items)


# ──────────────────────────────────────────────
# 포트폴리오 연동
# ──────────────────────────────────────────────
def get_portfolio_holdings() -> List[Dict[str, Any]]:
    """portfolio.csv에서 보유 종목 목록 로드:
    [{ticker, name, quantity, avg_price, current_price}]
    current_price가 비어있으면 0.0으로 반환.
    """
    if not os.path.exists(_portfolio_csv()):
        return []
    try:
        df = pd.read_csv(_portfolio_csv())
        out = []
        for _, row in df.iterrows():
            if not str(row.get("ticker", "")).strip():
                continue
            try:
                cur = float(row.get("current_price", 0) or 0)
            except (TypeError, ValueError):
                cur = 0.0
            out.append({
                "ticker": str(row["ticker"]).strip().upper(),
                "name": str(row.get("name", row["ticker"])),
                "quantity": float(row.get("quantity", 0) or 0),
                "avg_price": float(row.get("avg_price", 0) or 0),
                "current_price": cur,
            })
        return out
    except Exception as e:
        print(f"포트폴리오 로드 실패: {e}")
        return []


def get_usdkrw_rate() -> float:
    """원달러 환율 (실패 시 1400 폴백)"""
    try:
        hist = yf.Ticker("KRW=X").history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return 1400.0


# ──────────────────────────────────────────────
# 가격/지표 스냅샷
# ──────────────────────────────────────────────
def _fast_info_price(ticker: str) -> float:
    """yfinance fast_info에서 lastPrice 폴백. 실패 시 0."""
    try:
        fi = yf.Ticker(ticker).fast_info
        p = fi.get("lastPrice")
        if p and not (isinstance(p, float) and math.isnan(p)) and p > 0:
            return float(p)
    except Exception:
        pass
    return 0.0


def get_snapshot(holdings: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    보유 종목별 현재가/등락/수익률/평가액/RSI 테이블.
    holdings: [{ticker, name, quantity, avg_price, current_price}]

    **평가액/원가 계산은 사용자가 포트폴리오 탭에서 입력/저장한 current_price를
    그라운드 트루스로 사용**. csv가 비어 있으면 yfinance history → fast_info 순으로 폴백.
    """
    rows = []
    for h in holdings:
        ticker = h["ticker"]
        qty = h.get("quantity", 0)
        avg = h.get("avg_price", 0)
        user_price = float(h.get("current_price") or 0)
        is_kr = ticker.endswith((".KS", ".KQ"))

        def _emit(price, chg_1d, chg_5d, rsi_val):
            """공통 row 생성 + NaN 안전 처리."""
            if price is None or (isinstance(price, float) and math.isnan(price)) or price <= 0:
                rows.append({"티커": ticker, "현재가": "데이터 없음",
                             "1일": None, "5일": None, "수익률": None, "평가액": None, "RSI": None,
                             "_eval_native": 0.0, "_cost_native": avg * qty, "_is_kr": is_kr})
                return
            profit_rate = (price / avg - 1) * 100 if avg > 0 else None
            eval_amount = price * qty
            rows.append({
                "티커": ticker,
                "현재가": f"₩{price:,.0f}" if is_kr else f"${price:,.2f}",
                "1일": round(chg_1d, 2) if chg_1d is not None and not math.isnan(chg_1d) else None,
                "5일": round(chg_5d, 2) if chg_5d is not None and not math.isnan(chg_5d) else None,
                "수익률": round(profit_rate, 2) if profit_rate is not None else None,
                "평가액": f"₩{eval_amount:,.0f}" if is_kr else f"${eval_amount:,.2f}",
                "RSI": round(rsi_val, 1) if rsi_val is not None and not math.isnan(rsi_val) else None,
                "_eval_native": eval_amount,
                "_cost_native": avg * qty,
                "_is_kr": is_kr,
            })

        try:
            hist = yf.Ticker(ticker).history(period="3mo")
            # NaN 제거 후 유효 종가만 사용
            close = hist["Close"].dropna() if not hist.empty else hist
            yf_price = float(close.iloc[-1]) if len(close) > 0 else 0.0

            # csv current_price만 그라운드 트루스로 사용 (포트폴리오 탭과 합계 일치 보장).
            # csv가 비어있으면 합산에서 제외하고 "데이터 없음"으로 표시.
            display_price = user_price

            # 등락률·RSI는 유효 종가가 충분히 있을 때만
            chg_1d = chg_5d = rsi_val = None
            if len(close) >= 2:
                chg_1d = (yf_price / float(close.iloc[-2]) - 1) * 100
            if len(close) >= 6:
                chg_5d = (yf_price / float(close.iloc[-6]) - 1) * 100
            if len(close) >= 15:
                delta = close.diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rsi_series = 100 - 100 / (1 + gain / loss)
                rsi_val = float(rsi_series.dropna().iloc[-1]) if rsi_series.dropna().size else None

            _emit(display_price, chg_1d, chg_5d, rsi_val)

        except Exception as e:
            print(f"스냅샷 실패 ({ticker}): {e}")
            fallback_price = user_price if user_price > 0 else _fast_info_price(ticker)
            _emit(fallback_price, None, None, None)

    return pd.DataFrame(rows)


# ──────────────────────────────────────────────
# 이슈(뉴스) 수집 및 AI 요약
# ──────────────────────────────────────────────
def fetch_ticker_news(ticker: str, max_news: int = 6) -> List[Dict[str, Any]]:
    """NewsAgent 재사용 (yfinance 신/구 포맷 모두 대응)"""
    from agents.news_agent import NewsAgent
    agent = NewsAgent.__new__(NewsAgent)  # LLM 클라이언트 초기화 없이 fetch만 사용
    return NewsAgent.fetch_news(agent, ticker, max_news)


def summarize_all_issues(holdings_news: Dict[str, List[Dict]], model: str = "gpt-4o-mini") -> str:
    """
    보유 종목 전체의 뉴스를 한 번의 LLM 호출로 묶어서 브리핑 생성.
    holdings_news: {ticker: [news...]}
    """
    from openai import OpenAI
    client = OpenAI()

    sections = []
    for ticker, news_list in holdings_news.items():
        if not news_list:
            continue
        titles = "\n".join(f"  - [{n['published']}] {n['title']}" for n in news_list)
        sections.append(f"[{ticker}]\n{titles}")

    if not sections:
        return "수집된 뉴스가 없습니다."

    prompt = f"""다음은 내 보유 종목들의 최신 뉴스 헤드라인이야:

{chr(10).join(sections)}

각 종목마다 아래 형식으로 '깊이 있게' 브리핑해줘. 헤드라인만 주어졌으니
단순 나열·요약이 아니라 그 뒤의 배경·맥락·함의까지 풀어서 설명하되,
단정 대신 '~로 보인다 / ~가능성'으로 사실과 추측을 명확히 구분해.

### [티커] 종목명
- **핵심 이슈**: 지금 이 종목에 무슨 일이 벌어지고 있는지 2-4문장. 왜 이런 뉴스가
  나왔는지 배경까지 짚어줘.
- **배경/맥락**: 이 이슈가 속한 산업·매크로 흐름, 직전까지의 경위 (아는 범위에서)
- **영향 분석**: 🟢 긍정 / 🔴 부정 / ⚪ 중립 — 그렇게 본 근거를 2-3문장으로,
  단기 영향과 중기 영향을 구분해서.
- **주목할 점 / 리스크**: 앞으로 확인해야 할 트리거, 반대(약세) 시나리오, 변동성 요인
- **보유자 시사점**: 이 종목을 들고 있는 사람 관점에서 어떤 자세를 가질지 1-2문장

마지막에 "## 📌 오늘의 포트폴리오 총평"으로 종목들을 가로지르는 공통 테마
(섹터 쏠림·매크로 영향)와 종합 코멘트를 3-4문장으로 정리해줘."""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "너는 30년 경력의 증권사 리서치센터장이야. 헤드라인을 단순 나열하지 않고 그 뒤의 맥락과 함의까지 짚는 깊이 있는 브리핑을 쓴다. 풍부하게 설명하되, 헤드라인만으로 판단하는 한계를 인지해 단정 대신 '~로 보인다/가능성' 표현으로 사실과 추측을 구분한다."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        max_tokens=3500,
    )
    return response.choices[0].message.content
