"""
보유 종목 AI 평가 (성향 선택형)
공격적/중립/보수적 3가지 투자 성향 페르소나로 같은 데이터를 다르게 해석한다.
뉴스(Claude 웹 검색) + 밸류에이션(yfinance) + 이벤트(캘린더)를 종합해
종목별 [현재 상황 → 이벤트 → 밸류에이션 → 액션 의견]을 생성한다.
"""
import os
import json
from datetime import datetime
from typing import Dict, List, Any

import yfinance as yf

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from utils.user_data import portfolio_eval_path


def _eval_file() -> str:
    return portfolio_eval_path()


# ──────────────────────────────────────────────
# 1. 투자 성향 페르소나
# ──────────────────────────────────────────────
PERSONAS = {
    "aggressive": {
        "label": "🔥 공격적",
        "description": "성장·모멘텀 중시, 높은 변동성 감내, 수익 극대화 추구",
        "system": (
            "너는 고위험-고수익을 추구하는 공격적 성향의 포트폴리오 전략가야. "
            "성장 모멘텀과 섹터 주도주를 중시하고, 단기 변동성은 기회로 본다. "
            "다만 무모하진 않다 — 공격적이라는 건 확신 있는 곳에 집중한다는 뜻이지 아무거나 사는 게 아니다. "
            "조정은 분할매수 기회로 제안하고, 모멘텀이 꺾인 종목은 과감한 교체를 권한다. "
            "목표 수익 구간과 손절 라인을 구체적 가격대로 제시해."
        ),
    },
    "neutral": {
        "label": "⚖️ 중립",
        "description": "성장과 안정의 균형, 분산 중시",
        "system": (
            "너는 균형 잡힌 시각의 포트폴리오 전략가야. "
            "성장성과 밸류에이션을 동등하게 보고, 섹터 집중 리스크를 항상 점검한다. "
            "과열 종목은 일부 차익실현, 저평가 우량주는 분할매수를 제안하되 "
            "한 번에 큰 비중 변화보다 점진적 리밸런싱을 선호한다. "
            "긍정 요인과 부정 요인을 반드시 같은 비중으로 다뤄."
        ),
    },
    "conservative": {
        "label": "🛡️ 보수적",
        "description": "자본 보전 우선, 밸류에이션 엄격, 리스크 회피",
        "system": (
            "너는 자본 보전을 최우선으로 하는 보수적 성향의 포트폴리오 전략가야. "
            "밸류에이션에 엄격하고(PER 과열이면 명확히 경고), 고평가 구간에서는 "
            "차익실현과 현금비중 확대를 적극 권한다. "
            "'잃지 않는 것'이 '더 버는 것'보다 중요하다는 관점으로, "
            "각 종목의 하방 리스크 시나리오를 반드시 짚고, 추격 매수는 강하게 말려."
        ),
    },
    "expert": {
        "label": "🎩 전문가",
        "description": "30년차 월스트리트 트레이더·애널리스트, 중장기·냉정한 시각",
        "system": (
            "너는 30년차 월스트리트 증권 트레이더이자 전문 애널리스트다. "
            "워렌 버핏이 너에게 조언을 구할 정도로 이 분야에 대한 식견이 깊다. "
            "최신 데이터(기사, 시장 참여자들의 반응, 정량적 수치)를 종합 분석하되, "
            "단기 노이즈에 휩쓸리지 않고 중장기적 관점에서 사업의 본질 가치와 실적 추세를 본다. "
            "냉정한 투자 전문가의 시각으로, 듣기 좋은 말보다 사실에 근거한 판단을 우선한다. "
            "핵심 원칙: "
            "(1) 실적(EPS·매출 성장)이라는 '엔진'을 먼저 보고 차트는 '계기판'으로만 참고한다. "
            "(2) 펀더멘털이 강하면 단기 과열(RSI 과매수)도 추세로 해석하고, "
            "엔진이 식으면 차트가 좋아도 경계한다. "
            "(3) 시장 컨센서스와 군중 심리를 짚되, 거기에 동조하기보다 괴리(기회/위험)를 찾는다. "
            "(4) 각 판단에 정량 근거(밸류에이션 수치, 성장률, 목표가 괴리)를 반드시 제시하고, "
            "확신의 강도와 그 이유, 틀렸을 때의 시나리오(반증 조건)까지 명확히 밝힌다. "
            "감정 없이, 데이터로 말하라."
        ),
    },
}

_EVAL_FORMAT = """## 📊 포트폴리오 총평
(전체 구성에 대한 평가 2-3문장: 섹터 집중도, 현재 시장 국면과의 궁합)

## 종목별 평가
각 종목마다 아래 형식 (모든 보유 종목을 다뤄):

### [티커] 종목명 — 한줄 결론
- **📰 현재 상황**: 최근 뉴스/이슈 요약 (검색 근거, 매체명 표기)
- **📅 다가오는 이벤트**: 실적발표일 등 주가에 영향 줄 일정
- **💰 밸류에이션**: 제공된 PER/목표주가 수치 근거로 고평가/적정/저평가 판단
- **🎯 의견**: 분할매수 / 홀드 / 분할매도 / 비중축소 중 선택 + 구체적 실행안 (가격대, 비중)

## ⚠️ 리스크 체크
(포트폴리오 전체 관점의 리스크 2-3개)

마지막 줄에: "본 평가는 투자 권유가 아닌 분석 참고자료이며, 최종 판단과 책임은 본인에게 있습니다." """


# ──────────────────────────────────────────────
# 2. 밸류에이션 데이터 수집 (yfinance)
# ──────────────────────────────────────────────
def get_valuation_data(holdings: List[Dict]) -> List[Dict[str, Any]]:
    """종목별 밸류에이션 지표 수집"""
    rows = []
    for h in holdings:
        ticker = h["ticker"]
        try:
            info = yf.Ticker(ticker).info
            rows.append({
                "ticker": ticker,
                "name": h.get("name", ticker),
                "quantity": h.get("quantity", 0),
                "avg_price": h.get("avg_price", 0),
                "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "trailing_pe": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "target_mean": info.get("targetMeanPrice"),
                "recommendation": info.get("recommendationKey"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
            })
        except Exception as e:
            print(f"밸류에이션 수집 실패 ({ticker}): {e}")
            rows.append({"ticker": ticker, "name": h.get("name", ticker),
                         "quantity": h.get("quantity", 0), "avg_price": h.get("avg_price", 0)})
    return rows


def _fmt(v, fmt="{:.2f}"):
    return fmt.format(v) if isinstance(v, (int, float)) else "N/A"


def _build_data_text(valuations: List[Dict], events_text: str) -> str:
    lines = []
    for v in valuations:
        price = v.get("price")
        avg = v.get("avg_price", 0)
        profit = f"{(price / avg - 1) * 100:+.1f}%" if price and avg else "N/A"
        lines.append(
            f"[{v['ticker']}] {v.get('name', '')}\n"
            f"  보유: {v.get('quantity', 0):.0f}주 | 평단: {_fmt(avg)} | 현재가: {_fmt(price)} | 수익률: {profit}\n"
            f"  PER(TTM): {_fmt(v.get('trailing_pe'))} | PER(Fwd): {_fmt(v.get('forward_pe'))} | "
            f"애널리스트 목표가: {_fmt(v.get('target_mean'))} ({v.get('recommendation', 'N/A')})\n"
            f"  52주: {_fmt(v.get('52w_low'))} ~ {_fmt(v.get('52w_high'))}"
        )
    return (
        "[보유 종목 데이터 (yfinance 실시간)]\n" + "\n".join(lines)
        + f"\n\n[다가오는 이벤트 (3주 이내)]\n{events_text or '없음'}"
    )


# ──────────────────────────────────────────────
# 3. 평가 생성 (Claude 웹 검색)
# ──────────────────────────────────────────────
def evaluate_portfolio(holdings: List[Dict], stance: str = "neutral",
                       max_searches: int = 12) -> str:
    """성향에 맞는 페르소나로 보유 종목 종합 평가 생성 (Gemini/Claude 자동 선택)"""
    from utils.web_llm import search_generate

    persona = PERSONAS.get(stance, PERSONAS["neutral"])

    # 이벤트 수집
    try:
        from modules.event_calendar import get_all_events, get_upcoming_events
        events = get_all_events([h["ticker"] for h in holdings])
        upcoming = get_upcoming_events(events, days=21)
        events_text = "\n".join(f"- D-{e['d_day']} {e['date']} {e['title']}" for e in upcoming[:12])
    except Exception as e:
        print(f"이벤트 수집 실패: {e}")
        events_text = ""

    valuations = get_valuation_data(holdings)
    data_text = _build_data_text(valuations, events_text)

    prompt = f"""오늘 날짜: {datetime.now().strftime('%Y년 %m월 %d일')}

{data_text}

위 데이터는 이미 확보된 실시간 수치야. 추가로 각 종목의 최근 뉴스와 이슈를 웹에서 검색해서
(특히 수익률이 크게 움직였거나 이벤트가 임박한 종목 위주로) 아래 형식으로 평가서를 작성해.

{_EVAL_FORMAT}"""

    return search_generate(
        system=persona["system"] + (
            " 출력은 반드시 요청된 형식을 따르고, 수치는 제공된 데이터를 인용해. "
            "뉴스는 검색으로 확인한 것만 쓰고 매체명을 표기해. 추측은 '~로 보인다'로 구분해."
        ),
        prompt=prompt,
        max_tokens=10000,
        max_searches=max_searches,
    )


# ──────────────────────────────────────────────
# 4. 캐시 (날짜+성향별 저장 → 재요청 시 API 호출 없음)
# ──────────────────────────────────────────────
def _load_evals() -> Dict:
    try:
        with open(_eval_file(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_or_create_eval(holdings: List[Dict], stance: str, force: bool = False) -> Dict[str, Any]:
    """
    당일+성향 캐시 확인 후 없으면 생성.
    Returns: {text, time, cached: bool}
    """
    today = datetime.now().strftime("%Y-%m-%d")
    store = _load_evals()
    key = f"{today}|{stance}"

    if not force and key in store:
        return {**store[key], "cached": True}

    text = evaluate_portfolio(holdings, stance)
    entry = {"text": text, "time": datetime.now().strftime("%H:%M")}

    # 오늘 것만 유지 (과거 날짜 정리)
    store = {k: v for k, v in store.items() if k.startswith(today)}
    store[key] = entry
    os.makedirs(os.path.dirname(_eval_file()), exist_ok=True)
    with open(_eval_file(), "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)

    return {**entry, "cached": False}
