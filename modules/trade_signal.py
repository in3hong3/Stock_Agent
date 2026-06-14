"""
매매 시그널 엔진 (Pro)
10년차 트레이더의 판단 프로세스를 규칙화한다:
  1) 시장 국면 (VIX / Fear&Greed / S&P500) → 리스크 환경
  2) 멀티 타임프레임 (주봉 추세 + 일봉 타이밍)
  3) 추세 강도(ADX) → 추세장/횡보장 구분 후 전략 분기
  4) 셋업 패턴 인식 (눌림목/과매도반등/돌파/추세이탈/과열)
  5) ATR 기반 진입가·손절가·목표가 + 리스크:리워드 산정
LLM 호출 없음 — 순수 규칙 기반이라 즉시·무료.
"""
from typing import Dict, List, Any

import numpy as np
import pandas as pd
import yfinance as yf


# ──────────────────────────────────────────────
# 0. 보조 지표 계산
# ──────────────────────────────────────────────
def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    return 100 - 100 / (1 + gain / loss)


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    """평균 진폭 — 변동성 기반 손절폭 산정에 사용"""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def _adx(df: pd.DataFrame, period: int = 14) -> float:
    """추세 강도. 25↑ 강한 추세, 20↓ 횡보."""
    high, low, close = df["High"], df["Low"], df["Close"]
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.rolling(period).mean()
    return float(adx.iloc[-1]) if not np.isnan(adx.iloc[-1]) else 0.0


def _support_resistance(df: pd.DataFrame, lookback: int = 20):
    """최근 N일 스윙 고/저 → 단기 지지·저항"""
    recent = df.tail(lookback)
    return float(recent["Low"].min()), float(recent["High"].max())


def get_valuation(ticker: str, price: float) -> Dict[str, Any]:
    """
    밸류에이션 판정 (PER/PEG/목표가 괴리율 기반).
    Returns: {verdict: "저평가"|"적정"|"고평가"|"평가불가", score, note, ...}
    score: 양수=저평가(매수우위), 음수=고평가(매수신중)
    """
    try:
        info = yf.Ticker(ticker).info
    except Exception:
        return {"verdict": "평가불가", "score": 0, "note": "데이터 조회 실패"}

    trailing_pe = info.get("trailingPE")
    forward_pe = info.get("forwardPE")
    peg = info.get("pegRatio") or info.get("trailingPegRatio")
    target = info.get("targetMeanPrice")
    sector = info.get("sector", "")

    pts = 0
    notes = []

    # 1) PEG (성장 대비 밸류 — 가장 중요): 1 미만 저평가, 2 초과 고평가
    if isinstance(peg, (int, float)) and peg > 0:
        if peg < 1.0:
            pts += 12; notes.append(f"PEG {peg:.2f} (<1, 성장 대비 저평가)")
        elif peg <= 1.5:
            pts += 4; notes.append(f"PEG {peg:.2f} (적정)")
        elif peg <= 2.0:
            notes.append(f"PEG {peg:.2f} (다소 부담)")
        else:
            pts -= 10; notes.append(f"PEG {peg:.2f} (>2, 성장 대비 고평가)")

    # 2) Forward PE (절대 수준): 섹터마다 다르지만 대략 기준
    if isinstance(forward_pe, (int, float)) and forward_pe > 0:
        if forward_pe < 15:
            pts += 8; notes.append(f"선행 PER {forward_pe:.1f} (낮음)")
        elif forward_pe < 25:
            pts += 2; notes.append(f"선행 PER {forward_pe:.1f} (보통)")
        elif forward_pe < 40:
            pts -= 4; notes.append(f"선행 PER {forward_pe:.1f} (높음)")
        else:
            pts -= 10; notes.append(f"선행 PER {forward_pe:.1f} (매우 높음)")
        # 후행→선행 PER 개선 여부 (이익 성장 기대)
        if isinstance(trailing_pe, (int, float)) and trailing_pe > forward_pe * 1.1:
            pts += 4; notes.append("선행<후행 PER (이익 성장 기대)")

    # 3) 애널리스트 목표가 괴리율
    upside = None
    if isinstance(target, (int, float)) and target > 0 and price > 0:
        upside = (target / price - 1) * 100
        if upside >= 20:
            pts += 10; notes.append(f"목표가 +{upside:.0f}% 상승여력")
        elif upside >= 8:
            pts += 4; notes.append(f"목표가 +{upside:.0f}% 여력")
        elif upside >= -5:
            notes.append(f"목표가 {upside:+.0f}% (현재가 ≈ 목표가)")
        else:
            pts -= 8; notes.append(f"목표가 {upside:+.0f}% (현재가가 목표가 상회)")

    # 종합 판정
    if not notes:
        verdict = "평가불가"
    elif pts >= 12:
        verdict = "저평가"
    elif pts <= -10:
        verdict = "고평가"
    else:
        verdict = "적정"

    return {
        "verdict": verdict, "score": pts, "note": " · ".join(notes),
        "trailing_pe": round(trailing_pe, 1) if isinstance(trailing_pe, (int, float)) else None,
        "forward_pe": round(forward_pe, 1) if isinstance(forward_pe, (int, float)) else None,
        "peg": round(peg, 2) if isinstance(peg, (int, float)) else None,
        "target": round(target, 2) if isinstance(target, (int, float)) else None,
        "upside": round(upside, 1) if upside is not None else None,
    }


def _bull_divergence(close: pd.Series, rsi: pd.Series, lookback: int = 20) -> bool:
    """강세 다이버전스: 가격은 신저점인데 RSI는 더 높음 (반등 선행 신호)"""
    seg_c, seg_r = close.tail(lookback), rsi.tail(lookback)
    if len(seg_c) < lookback:
        return False
    half = lookback // 2
    price_lower = seg_c.iloc[-1] <= seg_c.iloc[:half].min()  # 현재가 전반부 최저 이하
    rsi_higher = seg_r.iloc[-1] > seg_r.iloc[:half].min() + 3  # RSI는 더 높음
    return bool(price_lower and rsi_higher)


# ──────────────────────────────────────────────
# 1. 시장 국면 판단
# ──────────────────────────────────────────────
def get_market_regime() -> Dict[str, Any]:
    detail = []
    points = 0

    vix = None
    try:
        h = yf.Ticker("^VIX").history(period="5d")
        if not h.empty:
            vix = float(h["Close"].iloc[-1])
            if vix < 15:
                points += 1; detail.append(f"VIX {vix:.1f} (안정 — 추세 추종 유리)")
            elif vix > 25:
                points -= 2; detail.append(f"VIX {vix:.1f} (공포 — 변동성 확대, 포지션 축소)")
            else:
                detail.append(f"VIX {vix:.1f} (보통)")
    except Exception:
        pass

    fng = None
    try:
        import requests
        r = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://edition.cnn.com/"},
            timeout=5,
        )
        if r.status_code == 200:
            fng = float(r.json()["fear_and_greed"]["score"])
            if fng <= 25:
                points += 1; detail.append(f"공포탐욕 {fng:.0f} (극공포 — 역발상 매수 우호)")
            elif fng >= 75:
                points -= 1; detail.append(f"공포탐욕 {fng:.0f} (극탐욕 — 신규 진입 신중)")
            else:
                detail.append(f"공포탐욕 {fng:.0f}")
    except Exception:
        pass

    try:
        h = yf.Ticker("^GSPC").history(period="3mo")
        if len(h) >= 50:
            spx = float(h["Close"].iloc[-1])
            ma50 = float(h["Close"].rolling(50).mean().iloc[-1])
            if spx > ma50:
                points += 1; detail.append("S&P500 > MA50 (시장 상승 추세 — 롱 우위)")
            else:
                points -= 1; detail.append("S&P500 < MA50 (시장 하락 추세 — 방어적)")
    except Exception:
        pass

    if points >= 2:
        regime, label, mod = "risk_on", "🟢 위험선호 (Risk-On)", +10
    elif points <= -2:
        regime, label, mod = "risk_off", "🔴 위험회피 (Risk-Off)", -15
    else:
        regime, label, mod = "neutral", "🟡 중립", 0

    return {"regime": regime, "label": label, "score_modifier": mod,
            "detail": detail, "vix": vix, "fng": fng}


# ──────────────────────────────────────────────
# 2. 종목 분석 — 멀티 타임프레임 + 셋업 인식
# ──────────────────────────────────────────────
def analyze_stock(ticker: str, quantity: float = 0, avg_price: float = 0) -> Dict[str, Any]:
    df = yf.Ticker(ticker).history(period="1y")
    if df.empty or len(df) < 60:
        return {"ticker": ticker, "error": "데이터 부족"}

    close = df["Close"]
    price = float(close.iloc[-1])

    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma50 = float(close.rolling(50).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else ma50

    rsi_series = _rsi(close)
    rsi = float(rsi_series.iloc[-1])

    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal_line
    macd_hist = float(hist.iloc[-1])
    macd_cross_up = float(hist.iloc[-1]) > 0 and float(hist.iloc[-2]) <= 0   # 골든크로스 직후
    macd_cross_dn = float(hist.iloc[-1]) < 0 and float(hist.iloc[-2]) >= 0   # 데드크로스 직후
    macd_rising = float(hist.iloc[-1]) > float(hist.iloc[-3])

    bb_mid = float(close.rolling(20).mean().iloc[-1])
    bb_std = float(close.rolling(20).std().iloc[-1])
    bb_upper, bb_lower = bb_mid + 2 * bb_std, bb_mid - 2 * bb_std
    bb_pos = (price - bb_lower) / (bb_upper - bb_lower) * 100 if bb_upper > bb_lower else 50

    vol_avg = float(df["Volume"].rolling(20).mean().iloc[-1])
    vol_ratio = float(df["Volume"].iloc[-1]) / vol_avg * 100 if vol_avg > 0 else 100

    atr = _atr(df)
    atr_pct = atr / price * 100 if price else 0
    adx = _adx(df)
    support, resistance = _support_resistance(df, 20)
    bull_div = _bull_divergence(close, rsi_series, 20)

    chg_1d = (price / float(close.iloc[-2]) - 1) * 100
    chg_5d = (price / float(close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
    high_52w = float(close.tail(252).max())
    profit_rate = (price / avg_price - 1) * 100 if avg_price > 0 else None

    # ── 주봉 추세 (멀티 타임프레임) ──
    wk = close.resample("W").last().dropna()
    wk_trend = "중립"
    if len(wk) >= 30:
        wk_ma10 = float(wk.rolling(10).mean().iloc[-1])
        wk_ma30 = float(wk.rolling(30).mean().iloc[-1])
        wk_price = float(wk.iloc[-1])
        if wk_price > wk_ma10 > wk_ma30:
            wk_trend = "상승"
        elif wk_price < wk_ma10 < wk_ma30:
            wk_trend = "하락"

    trend_regime = "추세장" if adx >= 25 else ("약추세" if adx >= 20 else "횡보장")

    # ── 밸류에이션 판정 (1차 필터) ──
    valuation = get_valuation(ticker, price)

    # ── 셋업 인식: 트레이더의 진입/청산 패턴 ──
    setup, score, reasons = _identify_setup(
        price=price, ma20=ma20, ma50=ma50, ma200=ma200,
        rsi=rsi, macd_hist=macd_hist, macd_cross_up=macd_cross_up,
        macd_cross_dn=macd_cross_dn, macd_rising=macd_rising,
        bb_pos=bb_pos, bb_lower=bb_lower, vol_ratio=vol_ratio,
        adx=adx, trend_regime=trend_regime, wk_trend=wk_trend,
        bull_div=bull_div, support=support, resistance=resistance,
        chg_5d=chg_5d, high_52w=high_52w,
    )

    return {
        "ticker": ticker, "price": price, "quantity": quantity, "avg_price": avg_price,
        "profit_rate": round(profit_rate, 1) if profit_rate is not None else None,
        "setup": setup, "score": score, "reasons": reasons, "valuation": valuation,
        "rsi": round(rsi, 1), "ma20": round(ma20, 2), "ma50": round(ma50, 2), "ma200": round(ma200, 2),
        "bb_lower": round(bb_lower, 2), "bb_upper": round(bb_upper, 2),
        "support": round(support, 2), "resistance": round(resistance, 2),
        "atr": round(atr, 2), "atr_pct": round(atr_pct, 1), "adx": round(adx, 1),
        "trend_regime": trend_regime, "wk_trend": wk_trend, "bull_div": bull_div,
        "high_52w": round(high_52w, 2), "chg_1d": round(chg_1d, 2), "chg_5d": round(chg_5d, 2),
        "vol_ratio": round(vol_ratio, 0),
    }


def _identify_setup(**k) -> tuple:
    """
    셋업 패턴을 인식하고 (셋업명, 점수, 근거리스트) 반환.
    점수: 양수=매수 우위, 음수=매도 우위.
    """
    price, ma20, ma50, ma200 = k["price"], k["ma20"], k["ma50"], k["ma200"]
    rsi, bb_pos, adx = k["rsi"], k["bb_pos"], k["adx"]
    wk_trend, trend_regime = k["wk_trend"], k["trend_regime"]
    vol_ratio, bull_div = k["vol_ratio"], k["bull_div"]
    resistance, support, high_52w = k["resistance"], k["support"], k["high_52w"]
    chg_5d = k["chg_5d"]

    score = 0
    reasons = []
    setup = "관망"

    long_trend_up = price > ma200  # 200일선 위 = 장기 상승 국면

    # ───── 매수 셋업 ─────
    # A. 눌림목 매수 (best): 주봉 상승 + 일봉 MA20~50 조정 + RSI 회복
    if wk_trend == "상승" and ma50 < price <= ma20 * 1.03 and 40 <= rsi <= 58:
        setup = "🎯 눌림목 매수 (추세 속 조정)"
        score = 45
        reasons.append(("✅", f"주봉 상승추세 유지 + 일봉이 MA20({ma20:,.1f}) 부근까지 조정 — 추세 재개 자리"))
        reasons.append(("✅", f"RSI {rsi:.0f} (과열 식고 반등 초입), ADX {adx:.0f} {trend_regime}"))
        if k["macd_cross_up"]:
            score += 10; reasons.append(("✅", "MACD 골든크로스 발생 — 모멘텀 전환 확인"))

    # B. 과매도 반등: RSI<32 + 볼린저 하단 + (다이버전스/장기추세 위면 가산)
    elif rsi <= 32 and bb_pos <= 15:
        setup = "🔄 과매도 반등 (역추세)"
        score = 30
        reasons.append(("✅", f"RSI {rsi:.0f} 과매도 + 볼린저 하단({bb_pos:.0f}%) — 통계적 저점권"))
        if bull_div:
            score += 15; reasons.append(("✅", "강세 다이버전스 (가격 신저점, RSI 고점 높임) — 반등 선행 신호"))
        if long_trend_up:
            score += 10; reasons.append(("✅", "200일선 위 장기 상승국면 — 눌림 매수 우위"))
        else:
            score -= 8; reasons.append(("⚠️", "200일선 아래 — 떨어지는 칼날 주의, 반등은 단기 트레이딩 관점"))

    # C. 돌파 매수: 저항 돌파 + 거래량 동반 + 추세장
    elif price >= resistance * 0.995 and vol_ratio >= 130 and adx >= 22:
        setup = "🚀 저항 돌파 (모멘텀)"
        score = 38
        reasons.append(("✅", f"단기 저항 {resistance:,.1f} 돌파 시도 + 거래량 {vol_ratio:.0f}% 동반"))
        reasons.append(("✅", f"ADX {adx:.0f} 추세 강함 — 돌파 신뢰도 양호"))
        if price >= high_52w * 0.98:
            score += 8; reasons.append(("✅", "52주 신고가 근접 — 매물벽 적음(저항 희박)"))

    # ───── 매도/청산 셋업 ─────
    # D. 과열 청산: RSI>72 + 볼린저 상단
    elif rsi >= 72 and bb_pos >= 88:
        setup = "🔴 과열 — 분할 익절"
        score = -32
        reasons.append(("⛔", f"RSI {rsi:.0f} 과매수 + 볼린저 상단({bb_pos:.0f}%) — 단기 과열, 되돌림 리스크"))
        if k["macd_cross_dn"]:
            score -= 10; reasons.append(("⛔", "MACD 데드크로스 — 모멘텀 둔화 확인"))

    # E. 추세 이탈: MA50 하향 이탈 + 데드크로스
    elif price < ma50 and (k["macd_cross_dn"] or k["macd_hist"] < 0) and wk_trend != "상승":
        setup = "📉 추세 이탈 — 비중 축소"
        score = -30
        reasons.append(("⛔", f"MA50({ma50:,.1f}) 하향 이탈 + MACD 음전 — 중기 추세 훼손"))
        if price < ma200:
            score -= 10; reasons.append(("⛔", "200일선마저 하회 — 장기 하락국면 진입"))

    # ───── 중립 ─────
    else:
        setup = "⚪ 관망 (셋업 미형성)"
        score = 0
        if price > ma50:
            score += 5; reasons.append(("•", f"MA50 위 추세 유지 중이나 뚜렷한 진입 트리거 없음 (RSI {rsi:.0f})"))
        else:
            score -= 5; reasons.append(("•", f"MA50 아래, 방향성 불명확 (RSI {rsi:.0f}, ADX {adx:.0f})"))
        if trend_regime == "횡보장":
            reasons.append(("•", f"ADX {adx:.0f} 횡보장 — 박스권 매매 외 신규 진입 자제"))

    return setup, score, reasons


# ──────────────────────────────────────────────
# 3. 성향별 의사결정 + 실행 가격(진입/손절/목표) + R:R
# ──────────────────────────────────────────────
# 성향별: (매수 임계, 강력매수 임계, 매도 임계, ATR 손절 배수, 목표 R:R, 익절 수익률%, 최대 손절폭%)
_PROFILE = {
    "aggressive":   (12, 35, -25, 2.5, 2.5, 60, 15),
    "neutral":      (18, 40, -22, 2.0, 2.0, 40, 12),
    "conservative": (25, 45, -18, 1.5, 1.8, 28, 9),
}


def decide_action(analysis: Dict, stance: str, regime_mod: int) -> Dict[str, Any]:
    buy_th, strong_th, sell_th, atr_mult, target_rr, take_pct, max_stop_pct = _PROFILE.get(stance, _PROFILE["neutral"])
    val = analysis.get("valuation", {})
    val_score = val.get("score", 0)
    # 밸류에이션을 기술 점수에 합산 (가치가 우선 — 기술 셋업보다 가중치 큼)
    score = analysis["score"] + regime_mod + val_score
    price = analysis["price"]
    atr = analysis["atr"]
    avg = analysis.get("avg_price", 0)
    profit = analysis.get("profit_rate")
    extra = []

    # ── 밸류에이션 게이트: 고평가면 신규 매수에 제동 ──
    verdict = val.get("verdict", "평가불가")
    if verdict == "고평가":
        extra.append(f"🏷️ 밸류에이션 고평가 — 기술적 셋업이 좋아도 신규 매수는 신중 ({val.get('note','')})")
    elif verdict == "저평가":
        extra.append(f"🏷️ 밸류에이션 저평가 — 가격 매력 구간 ({val.get('note','')})")

    is_buy_side = score > 0

    # ── 진입/손절/목표 가격 산정 (ATR 기반, 손절폭 상한 적용) ──
    entry = stop = target = rr = None
    if is_buy_side and score >= buy_th:
        # 진입: 현재가 (돌파형) 또는 지지 부근 (눌림형)
        if "돌파" in analysis["setup"]:
            entry = price
        else:
            entry = round(max(analysis["support"], price - 0.5 * atr), 2)  # 지지/소폭 눌림
        # 손절: ATR 배수 vs 최대 손절폭% 중 더 가까운(얕은) 쪽 채택 → 변동성 큰 종목 보호
        atr_stop = entry - atr_mult * atr
        cap_stop = entry * (1 - max_stop_pct / 100)
        stop = round(max(atr_stop, cap_stop), 2)
        risk = entry - stop
        target = round(entry + target_rr * risk, 2)                        # R:R 기반 목표
        rr = round((target - entry) / risk, 2) if risk > 0 else None

    # ── 수익률 오버레이 (보유 종목) ──
    if profit is not None and avg > 0:
        if profit >= take_pct:
            extra.append(f"💰 평단 +{profit:.1f}% (익절 기준 +{take_pct}% 초과) — 50% 분할 익절 후 나머지 추세 추종 권장")
        # 트레일링 스톱: 의미 있게 수익 난 종목(+10%↑)에만, 손절폭 상한 적용
        if profit >= 10:
            trail = round(max(price - atr_mult * atr, price * (1 - max_stop_pct / 100)), 2)
            extra.append(f"🔒 트레일링 스톱 {trail:,.2f}(현재가 {(trail/price-1)*100:+.1f}%) 이탈 시 청산 — 수익 보전")

    # ── 액션 라벨 ──
    if score >= strong_th:
        action, icon = "적극 매수", "🟢🟢"
    elif score >= buy_th:
        action, icon = "분할 매수", "🟢"
    elif score <= sell_th and profit is not None:
        action, icon = "비중 축소", "🔴🔴"
    elif score <= sell_th:
        action, icon = "신규 진입 회피", "🔴"
    elif score < 0 and "익절" in analysis["setup"]:
        action, icon = "분할 익절", "🟠"
    else:
        action, icon = "관망", "⚪"

    # ── 실행 플랜 문구 ──
    if entry is not None:
        plan = (f"진입 {entry:,.2f} → 손절 {stop:,.2f}(-{atr_mult}×ATR) → 목표 {target:,.2f} "
                f"| 손익비 1:{rr}")
        if rr is not None and rr < 1.5:
            extra.append(f"⚠️ 손익비 1:{rr} — 1.5 미만이라 진입 매력도 낮음. 더 좋은 자리 대기 권장")
    elif "익절" in action or "축소" in action:
        plan = f"반등 시 {analysis['resistance']:,.2f}(저항) 부근 분할 매도, MA20({analysis['ma20']:,.2f}) 이탈 시 속도 조절"
    else:
        plan = f"지지 {analysis['support']:,.2f} / 저항 {analysis['resistance']:,.2f} 돌파·이탈 확인 후 대응"

    # 보유 종목 손절가 (평단 기준 ATR)
    stop_price = round(avg - atr_mult * atr, 2) if avg > 0 else None

    return {
        "action": action, "icon": icon, "adj_score": score,
        "plan": plan, "entry": entry, "stop": stop, "target": target, "rr": rr,
        "stop_price": stop_price, "extra": extra,
    }


# ──────────────────────────────────────────────
# 4. 메인
# ──────────────────────────────────────────────
def generate_signals(holdings: List[Dict], stance: str = "aggressive") -> Dict[str, Any]:
    regime = get_market_regime()
    signals = []
    for h in holdings:
        analysis = analyze_stock(h["ticker"], h.get("quantity", 0), h.get("avg_price", 0))
        if "error" in analysis:
            continue
        decision = decide_action(analysis, stance, regime["score_modifier"])
        signals.append({**analysis, **decision})
    signals.sort(key=lambda s: -abs(s["adj_score"]))
    return {"regime": regime, "signals": signals}
