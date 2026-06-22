"""
AI 핫 섹터 스캐너
섹터/테마 ETF의 상대강도(모멘텀)를 yfinance로 정량 계산해 '지금 뜨는 섹터'를 랭킹하고,
상위 섹터에 대해 AI가 '왜 뜨는지'를 웹 검색 기반으로 해설한다.

- 정량 랭킹: 무료·즉시 (yfinance)
- AI 해설: 버튼 클릭 시에만 (web_llm — Perplexity/Gemini/Claude)
"""
from typing import Dict, List, Any
import pandas as pd
import yfinance as yf

# GICS 11개 섹터 ETF (S&P500 기준)
_GICS_SECTORS = [
    ("XLK", "기술 (Technology)"),
    ("XLC", "커뮤니케이션"),
    ("XLY", "임의소비재"),
    ("XLP", "필수소비재"),
    ("XLE", "에너지"),
    ("XLF", "금융"),
    ("XLV", "헬스케어"),
    ("XLI", "산업재"),
    ("XLB", "소재"),
    ("XLU", "유틸리티"),
    ("XLRE", "부동산"),
]

# 세부 테마 ETF
_THEME_SECTORS = [
    ("SMH", "반도체"),
    ("NLR", "원자력·원전"),
    ("ITA", "방산·항공우주"),
    ("TAN", "태양광"),
    ("LIT", "리튬·배터리"),
    ("IBB", "바이오테크"),
    ("BOTZ", "로봇·AI"),
    ("HACK", "사이버보안"),
    ("BLOK", "블록체인"),
    ("ARKK", "혁신성장"),
    ("XME", "광산·금속"),
    ("URA", "우라늄"),
]

_BENCHMARK = "SPY"  # 상대강도 비교 기준


def _period_return(close: pd.Series, days: int) -> float:
    """최근 N거래일 수익률 (%). 데이터 부족 시 None."""
    s = close.dropna()
    if len(s) <= days:
        return None
    return (float(s.iloc[-1]) / float(s.iloc[-1 - days]) - 1) * 100


def scan_sectors(include_themes: bool = True) -> Dict[str, Any]:
    """
    섹터/테마 ETF 모멘텀 스캔.
    Returns: {generated, benchmark_1m, rows: [{ticker, name, kind, r_1w, r_1m, r_3m, rs_1m, momentum_score, hot}]}
    momentum_score: 가중 모멘텀 (1주 0.2 + 1개월 0.5 + 3개월 0.3), 벤치마크 초과분 가산.
    """
    targets = list(_GICS_SECTORS)
    kinds = {t: "섹터" for t, _ in _GICS_SECTORS}
    if include_themes:
        targets += _THEME_SECTORS
        for t, _ in _THEME_SECTORS:
            kinds[t] = "테마"

    tickers = [t for t, _ in targets] + [_BENCHMARK]
    try:
        data = yf.download(tickers, period="6mo", interval="1d",
                           group_by="ticker", progress=False, auto_adjust=True)
    except Exception as e:
        return {"error": f"데이터 조회 실패: {e}", "rows": []}

    def _close(tk):
        try:
            if len(tickers) == 1:
                return data["Close"]
            return data[tk]["Close"]
        except Exception:
            return pd.Series(dtype=float)

    # 벤치마크 1개월 수익률
    bench_1m = _period_return(_close(_BENCHMARK), 21)

    rows = []
    name_map = {t: n for t, n in targets}
    for tk, name in targets:
        close = _close(tk)
        r_1w = _period_return(close, 5)
        r_1m = _period_return(close, 21)
        r_3m = _period_return(close, 63)
        if r_1m is None:
            continue
        # 상대강도 (1개월, 벤치마크 대비 초과)
        rs_1m = (r_1m - bench_1m) if (bench_1m is not None) else r_1m
        # 가중 모멘텀 점수
        score = (0.2 * (r_1w or 0)) + (0.5 * r_1m) + (0.3 * (r_3m or 0))
        score += rs_1m * 0.3  # 벤치마크 초과분 가산
        rows.append({
            "ticker": tk, "name": name, "kind": kinds[tk],
            "r_1w": round(r_1w, 2) if r_1w is not None else None,
            "r_1m": round(r_1m, 2),
            "r_3m": round(r_3m, 2) if r_3m is not None else None,
            "rs_1m": round(rs_1m, 2),
            "momentum_score": round(score, 2),
        })

    rows.sort(key=lambda x: -x["momentum_score"])
    # 상위 1/3을 'hot'으로 표시
    hot_n = max(3, len(rows) // 3)
    for i, r in enumerate(rows):
        r["hot"] = i < hot_n

    return {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "benchmark_1m": round(bench_1m, 2) if bench_1m is not None else None,
        "rows": rows,
    }


def explain_sector(scan: Dict[str, Any], ticker: str, holdings: List[Dict] = None) -> str:
    """선택한 단일 섹터/테마 ETF를 AI가 웹 검색 기반으로 심층 해설. web_llm 사용 (없으면 안내)."""
    from utils.web_llm import get_search_provider, search_generate

    if not get_search_provider():
        return "⚠️ 검색 LLM 키가 없습니다. .env에 PERPLEXITY_API_KEY / GEMINI_API_KEY 중 하나를 설정하세요."

    rows = scan.get("rows", [])
    row = next((r for r in rows if r["ticker"] == ticker), None)
    if not row:
        return "선택한 섹터 데이터를 찾을 수 없습니다."

    def _fmt(v):
        return f"{v:+.1f}" if v is not None else "N/A"

    bench = scan.get("benchmark_1m")
    metric = (f"{row['name']} ({row['ticker']}, {row['kind']}): "
              f"1주 {_fmt(row['r_1w'])}% · 1개월 {_fmt(row['r_1m'])}% (벤치 대비 {_fmt(row['rs_1m'])}%p) · "
              f"3개월 {_fmt(row['r_3m'])}% · 모멘텀점수 {row['momentum_score']:.1f}")

    hold_line = ""
    if holdings:
        tk = ", ".join(f"{h['name']}({h['ticker']})" for h in holdings[:12])
        hold_line = f"\n\n참고로 사용자의 보유 종목은: {tk}"

    system = (
        "당신은 30년 차 월스트리트 수석 트레이더이자 글로벌 탑티어 헤지펀드의 전문 애널리스트입니다. "
        "워런 버핏이 거시 경제 흐름과 기업의 해자를 파악하기 위해 당신에게 자문을 구할 정도로, "
        "당신은 시장의 노이즈를 걸러내고 본질적 가치를 꿰뚫어 보는 데 압도적인 식견을 가지고 있습니다. "
        "특히 전통적 재무 분석뿐 아니라 AI 인프라, 반도체, 양자 컴퓨팅, 우주 항공 등 미래 산업과 "
        "딥테크 기업의 기술적 해자(Moat)를 정량적 가치로 환산하는 데 독보적인 능력이 있습니다. "
        "냉정하고 날카로운 투자 전문가의 시각으로 분석하며, 근거가 된 매체명을 본문에 표기합니다."
    )
    prompt = f"""오늘 기준, 미국 섹터/테마 ETF 모멘텀 상위에 든 '{row['name']}' 섹터 하나를 심층 분석합니다.
(벤치마크 SPY 1개월 {_fmt(bench)}%)

[정량 측정값]
{metric}

위 정량 데이터를 출발점으로, 이 '{row['name']}' 섹터에 대해 아래 프레임워크를 엄격히 적용해
심층 분석 보고서를 작성하세요. 최신 기사·기관 리포트·자금 흐름을 검색해 근거로 삼으세요.

[분석 프레임워크]
1. **핵심 동력**: 이 섹터가 지금 돈이 몰리는 근본 구조 (수요/공급/정책/실적 사이클)
2. **정량 펀더멘털**: 섹터 대표 기업들의 매출 성장률·밸류에이션(P/E, PSR)·FCF 추세를
   기관 투자자 관점에서 평가. 모멘텀이 실적이 받쳐주는지 vs 멀티플 팽창인지 구분.
3. **시장 심리 & 컨센서스**: 최근 기사·기관 리포트의 컨센서스 변화, 기대감과 우려.
4. **기술적 해자 & 리스크**: 진입 장벽/경쟁 구도, 그리고 치명적 하방·매크로·규제 리스크를 가감 없이.
5. **중장기 뷰 (1~3년)**: 단기 노이즈를 배제한 구조적 추세 여부 + 대표 수혜 종목 3-5개(티커)와
   각각의 최종 스탠스(강력 매수 / 분할 매수 / 관망 / 매도).

[출력 구조]
### 🔥 {row['name']} — 한눈에 (2-3문장: 지금 강한 이유 + 자금 흐름 방향)

### 심층 분석
(위 5개 프레임워크를 표와 글머리 기호로)

### ⚠️ 과열·되돌림 경고
- 이미 멀티플이 과도하거나 단기 순환 정점 신호가 있으면 명확히 지적

### 💡 내 포트폴리오 관점
- 사용자 보유 종목이 이 섹터와 어떻게 연결되는지, 비어있는 기회는 무엇인지{hold_line}

[규칙]
- 흔한 면책 조항이나 AI로서의 변명은 생략. 단, 맨 마지막 한 줄에만
  "본 분석은 투자 참고자료이며 최종 판단과 책임은 본인에게 있습니다."를 적을 것.
- 문체는 단호하고 전문적이며 불필요한 미사여구를 뺄 것.
- 정량 수치(성장률·밸류에이션·목표가 괴리)를 근거로 제시하고, 확신 강도와 반증 조건을 밝힐 것."""

    return search_generate(system=system, prompt=prompt, max_tokens=5000, max_searches=10)


def score_stocks(query: str, holdings: List[Dict] = None) -> str:
    """월스트리트 스코어링 시스템(100점)으로 종목 발굴·랭킹.

    query가 섹터/테마면 그 안에서 8-10곳 발굴, 티커 나열이면 그 종목들만 스코어링.
    web_llm(Perplexity/Gemini/Claude) 웹 검색 기반.
    """
    from utils.web_llm import get_search_provider, search_generate

    if not get_search_provider():
        return "⚠️ 검색 LLM 키가 없습니다. .env에 PERPLEXITY_API_KEY / GEMINI_API_KEY 중 하나를 설정하세요."

    q = (query or "").strip()
    if not q:
        return "분석할 섹터명 또는 티커를 입력하세요."

    hold_line = ""
    if holdings:
        tk = ", ".join(f"{h['name']}({h['ticker']})" for h in holdings[:15])
        hold_line = f"\n\n참고: 사용자의 현재 보유 종목 — {tk}. 분석 대상에 이들이 포함되면 보유 관점도 한 줄 덧붙여라."

    system = (
        "당신은 30년 차 월스트리트 수석 트레이더이자 글로벌 탑티어 헤지펀드의 전문 애널리스트입니다. "
        "워런 버핏이 거시 경제 흐름과 기업의 해자를 파악하기 위해 당신에게 자문을 구할 정도로, "
        "당신은 시장의 노이즈를 걸러내고 기업의 본질적 가치와 미래 성장성을 꿰뚫어 보는 데 "
        "압도적인 식견을 가지고 있습니다. 철저히 데이터와 숫자에 기반해 냉정하게 평가하며, "
        "근거가 된 최신 기사·계약·수주 팩트와 매체명을 본문에 반드시 표기합니다."
    )
    prompt = f"""분석 요청: **{q}**

위 입력이 '섹터/테마'이면 해당 섹터 내에서 현재 가장 매력적인 투자처 8~10곳을 발굴하고,
'개별 종목(티커) 나열'이면 그 종목들만 대상으로, 아래 '월스트리트 스코어링 시스템(총 100점)'에
따라 랭킹을 매겨라. 각 항목은 최신 데이터를 검색해 근거로 삼아라.

[월스트리트 스코어링 프레임워크 — 100점]
1. **밸류에이션 및 고평가 검증 (30점)**
   - P/E, Forward P/E, PSR, EV/EBITDA, FCF 등 정량 지표로 현재 주가의 과열 여부를 엄격히 진단.
   - 거품이 낀 종목은 가차 없이 감점.
2. **미래 성장 모멘텀 및 가시성 (40점) ★가장 중요★**
   - 최근 체결 수주 계약, 백로그(수주 잔고), 대규모 CAPEX, 정부 정책 수혜, 대기업 파트너십 등
     미래 실적을 담보하는 최신 팩트를 반드시 포함해 평가.
3. **기술적/구조적 경제적 해자 (30점)**
   - 경쟁사가 쉽게 따라올 수 없는 독점 기술력, 시장 점유율, 진입 장벽.

[출력 양식 — 반드시 이 순서]
### 1. 섹터/대상 요약
(현재 매크로 환경 및 투자 매력도 — 짧고 강렬하게)

### 2. 랭킹보드
| 순위 | 기업명(티커) | 총점 | 밸류에이션 | 핵심 요약 |
|---|---|---|---|---|
(점수 높은 순. 밸류에이션은 저평가/적정/고평가)

### 3. 개별 종목 분석
(각 종목을 3대 항목 점수 분해로 상세히. **미래 수주·계약 관련 팩트 필수**)

### 4. 종합 투자 전략
(핵심 리스크 하나 + 중장기 대응 전략){hold_line}

[규칙]
- 면책 조항이나 AI로서의 변명은 절대 금지. (맨 끝 한 줄 "투자 참고자료" 고지만 허용)
- 문체는 30년 차 베테랑답게 단호하고, 철저히 데이터·숫자 기반의 냉정한 톤.
- 각 점수에 근거(수치·팩트)를 붙이고, 총점이 같으면 성장 모멘텀(2번) 우선."""

    return search_generate(system=system, prompt=prompt, max_tokens=6000, max_searches=12)
