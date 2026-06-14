"""
간단한 전략 백테스터
yfinance 일봉 데이터로 RSI / MA 크로스 / 볼린저밴드 전략을 시뮬레이션한다.
수수료 반영, Buy & Hold 대비 성과 비교.
"""
from typing import Dict, Any
import numpy as np
import pandas as pd
import yfinance as yf

STRATEGIES = {
    "rsi": "RSI 역추세 (과매도 매수 / 과매수 매도)",
    "ma_cross": "이동평균 골든/데드 크로스",
    "bollinger": "볼린저밴드 (하단 매수 / 상단 매도)",
}


def _prepare_data(ticker: str, period: str) -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period=period)
    if df.empty:
        return df

    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df["RSI"] = 100 - (100 / (1 + gain / loss))

    df["MA_FAST"] = df["Close"].rolling(20).mean()
    df["MA_SLOW"] = df["Close"].rolling(60).mean()

    df["BB_MID"] = df["Close"].rolling(20).mean()
    bb_std = df["Close"].rolling(20).std()
    df["BB_UP"] = df["BB_MID"] + bb_std * 2
    df["BB_LO"] = df["BB_MID"] - bb_std * 2

    return df.dropna()


def _generate_signals(df: pd.DataFrame, strategy: str, params: Dict) -> pd.Series:
    """1 = 보유, 0 = 현금. 신호는 다음 날 시가가 아닌 당일 종가 체결로 단순화."""
    if strategy == "rsi":
        buy_th = params.get("rsi_buy", 30)
        sell_th = params.get("rsi_sell", 70)
        position = pd.Series(np.nan, index=df.index)
        position[df["RSI"] < buy_th] = 1
        position[df["RSI"] > sell_th] = 0
        return position.ffill().fillna(0)

    if strategy == "ma_cross":
        return (df["MA_FAST"] > df["MA_SLOW"]).astype(int)

    if strategy == "bollinger":
        position = pd.Series(np.nan, index=df.index)
        position[df["Close"] <= df["BB_LO"]] = 1
        position[df["Close"] >= df["BB_UP"]] = 0
        return position.ffill().fillna(0)

    raise ValueError(f"알 수 없는 전략: {strategy}")


def run_backtest(
    ticker: str,
    strategy: str = "rsi",
    period: str = "2y",
    initial_capital: float = 10_000.0,
    fee_rate: float = 0.001,
    params: Dict = None,
) -> Dict[str, Any]:
    """
    백테스트 실행.

    Returns:
        {
            success, equity_curve(DF), trades(list), metrics(dict), error
        }
    """
    params = params or {}
    df = _prepare_data(ticker, period)
    if df.empty:
        return {"success": False, "error": f"{ticker} 데이터를 가져올 수 없습니다."}
    if len(df) < 70:
        return {"success": False, "error": "데이터가 부족합니다 (최소 70 거래일 필요). 기간을 늘려보세요."}

    position = _generate_signals(df, strategy, params)
    daily_ret = df["Close"].pct_change().fillna(0)

    # 포지션 변경일에 수수료 차감 (전일 포지션 기준으로 수익 반영)
    pos_shift = position.shift(1).fillna(0)
    strat_ret = daily_ret * pos_shift
    trade_days = position.diff().abs().fillna(0) > 0
    strat_ret[trade_days] -= fee_rate

    equity = initial_capital * (1 + strat_ret).cumprod()
    bh_equity = initial_capital * (1 + daily_ret).cumprod()

    # 거래 내역 추출
    trades = []
    entry_price, entry_date = None, None
    for date, pos_now, pos_prev, price in zip(df.index, position, pos_shift, df["Close"]):
        if pos_now == 1 and pos_prev == 0:
            entry_price, entry_date = price, date
        elif pos_now == 0 and pos_prev == 1 and entry_price:
            trades.append({
                "매수일": entry_date.strftime("%Y-%m-%d"),
                "매도일": date.strftime("%Y-%m-%d"),
                "매수가": round(entry_price, 2),
                "매도가": round(price, 2),
                "수익률(%)": round((price / entry_price - 1) * 100 - fee_rate * 200, 2),
            })
            entry_price = None

    # 성과 지표
    total_return = (equity.iloc[-1] / initial_capital - 1) * 100
    bh_return = (bh_equity.iloc[-1] / initial_capital - 1) * 100
    n_years = max(len(df) / 252, 1e-6)
    cagr = ((equity.iloc[-1] / initial_capital) ** (1 / n_years) - 1) * 100

    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max * 100
    mdd = drawdown.min()

    ann_vol = strat_ret.std() * np.sqrt(252)
    sharpe = (strat_ret.mean() * 252) / ann_vol if ann_vol > 0 else 0

    wins = [t for t in trades if t["수익률(%)"] > 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0

    equity_df = pd.DataFrame({
        "전략": equity,
        "Buy & Hold": bh_equity,
    })

    return {
        "success": True,
        "equity_curve": equity_df,
        "drawdown": drawdown,
        "trades": trades,
        "metrics": {
            "total_return": round(total_return, 2),
            "bh_return": round(bh_return, 2),
            "cagr": round(cagr, 2),
            "mdd": round(mdd, 2),
            "sharpe": round(sharpe, 2),
            "win_rate": round(win_rate, 1),
            "n_trades": len(trades),
        },
    }
