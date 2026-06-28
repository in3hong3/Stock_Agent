"""실제 매수 시그널 백테스트.
과거 각 거래일의 지표를 만들어 같은 엔진(trade_signal._identify_setup)으로 셋업을 판정하고,
이후 N일 실제 주가(ATR 기반 목표/손절)로 채점 → 셋업별 적중률·평균수익(트랙레코드).

한계: 과거 시점 펀더멘털(engine_strong/eps_growth)은 점추적이 어려워 중립 처리.
      지지/저항은 20일 롤링 고저로 근사. 즉 '실제 엔진 기반, 일부 근사' 백테스트.
"""
import collections
from typing import Dict, List, Any

import numpy as np
import pandas as pd
import yfinance as yf

from modules.trade_signal import _identify_setup, _rsi

_BUY_KEYS = ("눌림목", "과매도", "돌파", "저평가")  # setup 문자열에 있으면 매수성


def _atr_series(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _adx_series(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    up, dn = h.diff(), -l.diff()
    plus_dm = ((up > dn) & (up > 0)) * up
    minus_dm = ((dn > up) & (dn > 0)) * dn
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean()
    plus_di = 100 * (plus_dm.rolling(n).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(n).mean() / atr)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.rolling(n).mean()


def backtest_ticker(ticker: str, horizon: int = 10, period: str = "2y") -> List[Dict[str, Any]]:
    df = yf.Ticker(ticker).history(period=period)
    if df.empty or len(df) < 220:
        return []
    close, high, low, vol = df["Close"], df["High"], df["Low"], df["Volume"]
    ma20, ma50, ma200 = close.rolling(20).mean(), close.rolling(50).mean(), close.rolling(200).mean()
    rsi = _rsi(close)
    exp1, exp2 = close.ewm(span=12, adjust=False).mean(), close.ewm(span=26, adjust=False).mean()
    hist = (exp1 - exp2) - (exp1 - exp2).ewm(span=9, adjust=False).mean()
    bb_mid, bb_std = close.rolling(20).mean(), close.rolling(20).std()
    bb_up, bb_lo = bb_mid + 2 * bb_std, bb_mid - 2 * bb_std
    bb_pos = (close - bb_lo) / (bb_up - bb_lo) * 100
    vol_ratio = vol / vol.rolling(20).mean() * 100
    atr, adx = _atr_series(df), _adx_series(df)
    resistance, support = high.rolling(20).max().shift(1), low.rolling(20).min().shift(1)
    high_52w = close.rolling(252, min_periods=60).max()
    chg5 = close.pct_change(5) * 100
    ma50_rising = ma50 > ma50.shift(20)

    def _f(series, t, default):
        v = series.iloc[t]
        return float(v) if not pd.isna(v) else default

    out, idx, n = [], df.index, len(df)
    for t in range(205, n - horizon):
        if pd.isna(ma50.iloc[t]) or pd.isna(adx.iloc[t]) or pd.isna(rsi.iloc[t]):
            continue
        price = float(close.iloc[t])
        if price > ma50.iloc[t] and bool(ma50_rising.iloc[t]):
            wk = "상승"
        elif price < ma50.iloc[t] and not bool(ma50_rising.iloc[t]):
            wk = "하락"
        else:
            wk = "중립"
        adx_v = _f(adx, t, 15)
        regime = "추세장" if adx_v >= 25 else ("약추세" if adx_v >= 20 else "횡보장")
        setup, score, _ = _identify_setup(
            price=price, ma20=_f(ma20, t, price), ma50=_f(ma50, t, price), ma200=_f(ma200, t, _f(ma50, t, price)),
            rsi=_f(rsi, t, 50), macd_hist=_f(hist, t, 0),
            macd_cross_up=bool(hist.iloc[t] > 0 and hist.iloc[t - 1] <= 0),
            macd_cross_dn=bool(hist.iloc[t] < 0 and hist.iloc[t - 1] >= 0),
            macd_rising=bool(hist.iloc[t] > hist.iloc[t - 2]),
            macd_weakening=bool(hist.iloc[t] > 0 and hist.iloc[t] < hist.iloc[t - 1] < hist.iloc[t - 2]),
            bb_pos=_f(bb_pos, t, 50), bb_lower=_f(bb_lo, t, price * 0.95),
            vol_ratio=_f(vol_ratio, t, 100), adx=adx_v, trend_regime=regime, wk_trend=wk,
            bull_div=False, support=_f(support, t, price * 0.95), resistance=_f(resistance, t, price * 1.05),
            chg_5d=_f(chg5, t, 0), high_52w=_f(high_52w, t, price),
            engine_strong=False, eps_growth=None,
        )
        if not any(key in setup for key in _BUY_KEYS):
            continue
        a = _f(atr, t, price * 0.03)
        target, stop = price + 2.5 * a, price - 2.0 * a
        win = df.iloc[t + 1:t + 1 + horizon]
        if win.empty:
            continue
        hit_t = bool(win["High"].max() >= target)
        hit_s = bool(win["Low"].min() <= stop)
        fwd = (float(close.iloc[t + horizon]) / price - 1) * 100
        outcome = "적중" if (hit_t and not hit_s) else ("실패" if hit_s else "진행")
        out.append({"date": idx[t].strftime("%Y-%m-%d"), "ticker": ticker,
                    "setup": setup, "score": int(score), "fwd_ret": round(fwd, 2), "outcome": outcome})
    return out


def run_backtest(tickers: List[str], horizon: int = 10, period: str = "2y") -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for tk in tickers:
        try:
            rows.extend(backtest_ticker(tk, horizon, period))
        except Exception as e:
            print(f"백테스트 실패 ({tk}): {e}")
    if not rows:
        return {"n": 0, "rows": [], "setup_stats": {}, "overall_win": None, "avg_ret": None}

    by_setup = collections.defaultdict(list)
    for r in rows:
        by_setup[r["setup"]].append(r)
    setup_stats = {}
    for s, lst in by_setup.items():
        dec = [x for x in lst if x["outcome"] in ("적중", "실패")]
        wins = sum(1 for x in dec if x["outcome"] == "적중")
        setup_stats[s] = {
            "n": len(lst),
            "win_rate": round(wins / len(dec) * 100) if dec else None,
            "avg_ret": round(sum(x["fwd_ret"] for x in lst) / len(lst), 1),
        }
    dec_all = [x for x in rows if x["outcome"] in ("적중", "실패")]
    overall_win = round(sum(1 for x in dec_all if x["outcome"] == "적중") / len(dec_all) * 100, 1) if dec_all else None
    return {
        "n": len(rows), "overall_win": overall_win,
        "avg_ret": round(sum(x["fwd_ret"] for x in rows) / len(rows), 1),
        "setup_stats": setup_stats,
        "rows": sorted(rows, key=lambda x: x["date"], reverse=True),
    }
