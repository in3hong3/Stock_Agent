"""
시그널 예측 기록 & 채점 (Signal Tracking)
매매 시그널을 생성할 때마다 예측을 스냅샷으로 저장하고,
시간이 지난 뒤 실제 가격으로 자동 채점한다.
→ 셋업별/성향별 적중률을 집계해 신뢰도를 측정하고,
   나중에 ML 학습용 데이터셋으로 활용한다.

저장: data/signal_predictions.csv
"""
import os
from datetime import datetime
from typing import Dict, List, Any

import pandas as pd
import yfinance as yf

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRED_FILE = os.path.join(_BASE_DIR, "data", "signal_predictions.csv")

COLUMNS = [
    "pred_date", "ticker", "stance", "action", "setup", "score",
    "valuation", "price_at_pred", "entry", "stop", "target", "rr",
    "rsi", "adx", "wk_trend",
    # 채점 결과 (나중에 채워짐)
    "graded", "grade_date", "price_after", "ret_pct", "outcome", "horizon_days",
]


def _load() -> pd.DataFrame:
    if not os.path.exists(PRED_FILE):
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(PRED_FILE)
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = None
    return df[COLUMNS]


def _save(df: pd.DataFrame):
    os.makedirs(os.path.dirname(PRED_FILE), exist_ok=True)
    df.to_csv(PRED_FILE, index=False)


def record_predictions(signals: List[Dict], stance: str) -> int:
    """
    오늘자 시그널을 예측으로 기록. 하루에 종목당 1건만 (중복 방지).
    관망도 기록 — 나중에 '안 산 게 옳았나'도 채점 가능.
    Returns: 새로 기록된 건수
    """
    today = datetime.now().strftime("%Y-%m-%d")
    df = _load()
    existing = set(zip(df["pred_date"].astype(str), df["ticker"].astype(str), df["stance"].astype(str)))

    rows = []
    for s in signals:
        if (today, s["ticker"], stance) in existing:
            continue
        val = s.get("valuation", {})
        rows.append({
            "pred_date": today, "ticker": s["ticker"], "stance": stance,
            "action": s["action"], "setup": s.get("setup", ""), "score": s["adj_score"],
            "valuation": val.get("verdict", ""), "price_at_pred": s["price"],
            "entry": s.get("entry"), "stop": s.get("stop"), "target": s.get("target"), "rr": s.get("rr"),
            "rsi": s.get("rsi"), "adx": s.get("adx"), "wk_trend": s.get("wk_trend"),
            "graded": False, "grade_date": None, "price_after": None,
            "ret_pct": None, "outcome": None, "horizon_days": None,
        })
    if rows:
        new_df = pd.DataFrame(rows)
        df = new_df if df.empty else pd.concat([df, new_df], ignore_index=True)
        _save(df)
    return len(rows)


def grade_predictions(horizon_days: int = 10) -> Dict[str, Any]:
    """
    horizon_days일 이상 지난 미채점 예측을 실제 가격으로 채점.
    매수 시그널: 목표 도달=적중, 손절 터치=실패, 그 외 수익률로 판정.
    """
    df = _load()
    if df.empty:
        return {"graded_count": 0}

    today = datetime.now().date()
    mask_ungraded = ~df["graded"].isin([True, "True"])
    graded_count = 0
    price_cache = {}

    for idx in df[mask_ungraded].index:
        row = df.loc[idx]
        try:
            pred_date = datetime.strptime(str(row["pred_date"]), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        age = (today - pred_date).days
        if age < horizon_days:
            continue

        ticker = row["ticker"]
        if ticker not in price_cache:
            try:
                price_cache[ticker] = yf.Ticker(ticker).history(period="3mo")
            except Exception:
                price_cache[ticker] = None
        hist = price_cache[ticker]
        if hist is None or hist.empty:
            continue

        try:
            window = hist[hist.index.date >= pred_date].head(horizon_days + 5)
        except Exception:
            window = hist.tail(horizon_days + 5)
        if window.empty:
            continue

        price_pred = float(row["price_at_pred"])
        price_after = float(window["Close"].iloc[-1])
        ret = (price_after / price_pred - 1) * 100

        action = str(row["action"])
        if "매수" in action:
            hit_target = pd.notna(row["target"]) and (window["High"].max() >= float(row["target"]))
            hit_stop = pd.notna(row["stop"]) and (window["Low"].min() <= float(row["stop"]))
            if hit_target and not hit_stop:
                outcome = "적중(목표달성)"
            elif hit_stop:
                outcome = "실패(손절터치)"
            else:
                outcome = "진행중(수익)" if ret > 0 else "진행중(손실)"
        elif "축소" in action or "익절" in action or "회피" in action:
            outcome = "적중(하락회피)" if ret < 0 else "실패(상승놓침)"
        else:
            outcome = f"관망({ret:+.1f}%)"

        df.at[idx, "graded"] = True
        df.at[idx, "grade_date"] = today.strftime("%Y-%m-%d")
        df.at[idx, "price_after"] = round(price_after, 2)
        df.at[idx, "ret_pct"] = round(ret, 2)
        df.at[idx, "outcome"] = outcome
        df.at[idx, "horizon_days"] = age
        graded_count += 1

    if graded_count:
        _save(df)
    return {"graded_count": graded_count}


def get_accuracy_stats() -> Dict[str, Any]:
    """채점된 예측으로 적중률 집계"""
    df = _load()
    graded = df[df["graded"].isin([True, "True"])].copy()
    if graded.empty:
        return {"total": len(df), "graded": 0, "pending": len(df)}

    def is_win(o):
        return isinstance(o, str) and "적중" in o

    def is_loss(o):
        return isinstance(o, str) and "실패" in o

    decisive = graded[graded["outcome"].apply(lambda o: is_win(o) or is_loss(o))]
    win_rate = decisive["outcome"].apply(is_win).mean() * 100 if not decisive.empty else None

    buy = graded[graded["action"].astype(str).str.contains("매수")]
    buy_ret = buy["ret_pct"].astype(float).mean() if not buy.empty else None

    setup_stats = {}
    for setup, grp in graded.groupby("setup"):
        dec = grp[grp["outcome"].apply(lambda o: is_win(o) or is_loss(o))]
        if not dec.empty:
            setup_stats[setup] = {
                "n": int(len(dec)),
                "win_rate": round(dec["outcome"].apply(is_win).mean() * 100, 0),
                "avg_ret": round(grp["ret_pct"].astype(float).mean(), 1),
            }

    return {
        "total": len(df), "graded": len(graded), "pending": len(df) - len(graded),
        "win_rate": round(win_rate, 1) if win_rate is not None else None,
        "buy_avg_ret": round(buy_ret, 1) if buy_ret is not None else None,
        "setup_stats": setup_stats,
        "recent": graded.sort_values("pred_date", ascending=False).head(15),
    }
