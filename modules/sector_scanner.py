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


def explain_hot_sectors(scan: Dict[str, Any], top_n: int = 5, holdings: List[Dict] = None) -> str:
    """상위 섹터를 AI가 웹 검색 기반으로 해설. web_llm 사용 (없으면 안내)."""
    from utils.web_llm import get_search_provider, search_generate

    if not get_search_provider():
        return "⚠️ 검색 LLM 키가 없습니다. .env에 PERPLEXITY_API_KEY / GEMINI_API_KEY 중 하나를 설정하세요."

    rows = scan.get("rows", [])[:top_n]
    if not rows:
        return "스캔 데이터가 없습니다."

    bench = scan.get("benchmark_1m")
    lines = [f"- {r['name']} ({r['ticker']}, {r['kind']}): "
             f"1개월 {r['r_1m']:+.1f}% (벤치 대비 {r['rs_1m']:+.1f}%p), 3개월 {r['r_3m']:+.1f}%"
             for r in rows]
    rank_text = "\n".join(lines)

    hold_line = ""
    if holdings:
        tk = ", ".join(f"{h['name']}({h['ticker']})" for h in holdings[:12])
        hold_line = f"\n\n참고로 사용자의 보유 종목은: {tk}"

    system = (
        "너는 30년차 월스트리트 섹터 전략가다. 정량 모멘텀 데이터와 최신 뉴스를 결합해 "
        "'왜 이 섹터가 지금 강한가'를 냉정하게 분석한다. 단기 노이즈와 구조적 추세를 구분하고, "
        "근거가 된 매체명을 본문에 표기한다."
    )
    prompt = f"""오늘 기준 미국 섹터/테마 ETF 모멘텀 상위권 (벤치마크 SPY 1개월 {bench:+.1f}%):

{rank_text}

위 정량 순위를 바탕으로, 각 상위 섹터가 '지금' 강한 이유를 최신 뉴스/자금흐름/실적 관점에서 검색해 분석해줘.

형식:
### 🔥 지금 뜨는 섹터 종합 (1-2문장)

### 섹터별 분석 (상위 {top_n}개)
각 섹터마다:
- **[섹터명]** — 강세 이유 핵심 (검색 근거, 매체명 표기)
- 구조적 추세인지 / 단기 순환인지 구분
- 대표 수혜 종목 2-3개 (티커)

### ⚠️ 주의할 점
- 이미 과열이거나 되돌림 위험이 있는 섹터 1-2개

### 💡 내 포트폴리오 관점
- 사용자 보유 종목이 어느 핫 섹터에 속하는지, 비어있는 핫 섹터는 무엇인지 (있으면){hold_line}

투자 권유가 아닌 분석 참고자료임을 마지막에 한 줄로 밝혀."""

    return search_generate(system=system, prompt=prompt, max_tokens=4000, max_searches=8)
