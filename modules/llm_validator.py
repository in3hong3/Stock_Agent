"""
LLM 출력 검증 하네스 (로드맵 #3)

데일리신문·AI평가 등 LLM이 쓴 글이 환각(특히 '옛 가격'·'틀린 현재가')을
담고 있는지 사후 검사한다.

핵심 아이디어:
  발행 시 우리는 holdings[].current_price 에 yfinance 실시간가를 '그라운드 트루스'로
  주입하고, 프롬프트에서 "현재가는 이 값을 써라"고 강제한다. 그런데도 LLM이 검색한
  옛 기사의 가격(분할 전 가격 등)을 본문에 적을 수 있다.
  → 생성문에서 '현재가 단언' 가격을 뽑아 우리가 준 실제가와 비교, 5% 넘게 빗나가면 경고.

설계 원칙(거짓경보 최소화):
  - '현재가/주가는/종가/시가/거래되고' 같은 **현재가 단언 키워드**가 있는 문장만 검사
  - '목표가/저항/지지/평단/52주/신고가' 등 합법적으로 다를 수 있는 수치가 섞인 문장은 건너뜀
  - 한 문장에 보유종목이 정확히 1개 언급될 때만 그 가격을 그 종목에 귀속(오귀속 방지)
  - 자릿수가 동떨어진 숫자(퍼센트·시총 등)는 비교 제외 (0.2 < 인용/실제 < 5 만 비교)
  검증은 비차단(non-blocking) — 경고만 내고 발행/표시는 그대로 진행.
"""
import re
from typing import Dict, List, Any, Optional

# 현재가를 단언하는 신호 (이 중 하나라도 문장에 있어야 검사)
_PRICE_ASSERT = ("현재가", "현재 주가", "주가는", "주가가", "종가", "시가",
                 "거래되", "거래 중", "trading at", "trades at")
# 합법적으로 현재가와 다를 수 있는 수치 → 이 단어가 같은 문장에 있으면 통째로 건너뜀
_PRICE_EXEMPT = ("목표가", "목표주가", "목표 주가", "저항", "지지", "평단", "평균단가",
                 "52주", "신고가", "신저가", "전고점", "전저점", "고점", "저점", "target")

_NUM = r"[0-9][0-9,]*\.?[0-9]*"
# $123.45 / 123.45달러 / 현재가 123.45
_PRICE_PATTERNS = [
    re.compile(r"\$\s?(" + _NUM + r")"),
    re.compile(r"(" + _NUM + r")\s*달러"),
    re.compile(r"(?:현재가|주가는|주가가|종가|시가)\s*(?:는|은|이|가)?\s*\$?\s*(" + _NUM + r")"),
]


def _to_float(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _split_sentences(text: str) -> List[str]:
    # 마침표/느낌표/물음표/줄바꿈/중점(·) 기준 분할
    parts = re.split(r"[.!?\n·]+", text or "")
    return [p.strip() for p in parts if p.strip()]


def _true_price(h: Dict) -> Optional[float]:
    """그라운드 트루스 가격 = 발행 시 주입한 current_price, 없으면 캐시 종가."""
    cur = h.get("current_price")
    try:
        cur = float(cur or 0)
    except (TypeError, ValueError):
        cur = 0
    if cur > 0:
        return cur
    try:
        from core.services.market_cache import get_history
        df = get_history(h["ticker"], period="5d")
        if df is not None and not df.empty:
            return float(df["Close"].iloc[-1])
    except Exception:
        pass
    return None


def validate_price_claims(text: str, holdings: List[Dict],
                          threshold_pct: float = 5.0) -> List[Dict[str, Any]]:
    """생성문 속 '현재가 단언'을 실제가와 비교해 빗나간 항목을 반환.
    Returns: [{ticker, name, claimed, true, deviation_pct, sentence}]"""
    if not text or not holdings:
        return []

    # 종목별 그라운드 트루스 + 매칭 키(티커·종목명)
    truth = []
    for h in holdings:
        tp = _true_price(h)
        if tp and tp > 0:
            truth.append({"ticker": h["ticker"], "name": h.get("name", h["ticker"]),
                          "true": tp})
    if not truth:
        return []

    warnings = []
    for sent in _split_sentences(text):
        if not any(kw in sent for kw in _PRICE_ASSERT):
            continue
        if any(kw in sent for kw in _PRICE_EXEMPT):
            continue

        # 이 문장이 언급한 보유종목 (티커 단어경계 / 종목명 부분일치)
        mentioned = []
        for t in truth:
            tk = t["ticker"]
            if re.search(r"\b" + re.escape(tk) + r"\b", sent, re.IGNORECASE):
                mentioned.append(t)
            elif t["name"] and len(t["name"]) >= 2 and t["name"] in sent:
                mentioned.append(t)
        if len(mentioned) != 1:   # 0개 or 2개 이상 → 오귀속 위험, 건너뜀
            continue
        target = mentioned[0]

        # 가격 후보 추출
        nums = set()
        for pat in _PRICE_PATTERNS:
            for m in pat.findall(sent):
                v = _to_float(m)
                if v and v > 0:
                    nums.add(v)

        for claimed in nums:
            ratio = claimed / target["true"]
            if not (0.2 < ratio < 5):   # 자릿수 동떨어진 숫자(%·시총 등) 제외
                continue
            dev = abs(ratio - 1) * 100
            if dev > threshold_pct:
                warnings.append({
                    "ticker": target["ticker"], "name": target["name"],
                    "claimed": round(claimed, 2), "true": round(target["true"], 2),
                    "deviation_pct": round(dev, 1),
                    "sentence": sent[:120],
                })
    return warnings


def format_warnings(warnings: List[Dict[str, Any]]) -> str:
    """경고 리스트를 사람이 읽을 한 덩어리 텍스트로."""
    if not warnings:
        return "✅ 가격 검증 통과 (현재가 단언 이상 없음)"
    lines = [f"⚠️ 가격 검증 경고 {len(warnings)}건 (현재가 ±{warnings[0].get('deviation_pct','?')}%↑ 빗나감)"]
    for w in warnings:
        lines.append(f"  - {w['ticker']}: 본문 {w['claimed']:,} vs 실제 {w['true']:,} "
                     f"({w['deviation_pct']:+.0f}% 차) → \"{w['sentence']}\"")
    return "\n".join(lines)


def validate_paper(result: Dict[str, Any], holdings: List[Dict],
                   threshold_pct: float = 5.0) -> Dict[str, Any]:
    """publish_daily_paper 결과(front)를 검증. 결과에 검증 요약을 붙여 반환."""
    front = (result or {}).get("front", "")
    warnings = validate_price_claims(front, holdings, threshold_pct)
    return {
        "ok": not warnings,
        "warnings": warnings,
        "summary": format_warnings(warnings),
    }
