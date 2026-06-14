"""
매매일지 (Trade Journal)
매수/매도 거래를 기록하고 실현손익·승률·매매 통계를 집계한다.
매도 기록 시 평단가 기준 실현손익을 자동 계산한다.
저장: data/trade_journal.csv
"""
import os
from datetime import date
from typing import Dict, Any

import pandas as pd

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from utils.user_data import trade_journal_path, portfolio_path


def _journal_file() -> str:
    return trade_journal_path()

COLUMNS = ["date", "ticker", "name", "side", "quantity", "price", "avg_price_at_sale", "realized_pnl", "memo"]


def load_journal() -> pd.DataFrame:
    if not os.path.exists(_journal_file()):
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(_journal_file())
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[COLUMNS]


def _save(df: pd.DataFrame):
    os.makedirs(os.path.dirname(_journal_file()), exist_ok=True)
    df.to_csv(_journal_file(), index=False)


def add_trade(trade_date: str, ticker: str, name: str, side: str,
              quantity: float, price: float, memo: str = "",
              avg_price: float = None) -> Dict[str, Any]:
    """
    거래 기록 추가.
    side: "buy" | "sell"
    매도 시 avg_price(매도 시점 평단가)를 주면 실현손익 자동 계산.
    """
    realized = None
    if side == "sell" and avg_price and avg_price > 0:
        realized = round((price - avg_price) * quantity, 2)

    df = load_journal()
    row = {
        "date": trade_date, "ticker": ticker.upper(), "name": name,
        "side": side, "quantity": quantity, "price": price,
        "avg_price_at_sale": avg_price if side == "sell" else None,
        "realized_pnl": realized, "memo": memo,
    }
    row_df = pd.DataFrame([row])
    df = row_df if df.empty else pd.concat([df, row_df], ignore_index=True)
    _save(df)
    return row


def delete_trade(index: int):
    df = load_journal()
    if 0 <= index < len(df):
        df = df.drop(df.index[index]).reset_index(drop=True)
        _save(df)


def get_stats() -> Dict[str, Any]:
    """실현손익·승률 등 매매 통계"""
    df = load_journal()
    if df.empty:
        return {"n_trades": 0}

    sells = df[(df["side"] == "sell") & df["realized_pnl"].notna()].copy()
    total_realized = sells["realized_pnl"].sum() if not sells.empty else 0
    wins = sells[sells["realized_pnl"] > 0]
    win_rate = len(wins) / len(sells) * 100 if len(sells) > 0 else 0
    avg_win = wins["realized_pnl"].mean() if not wins.empty else 0
    losses = sells[sells["realized_pnl"] < 0]
    avg_loss = losses["realized_pnl"].mean() if not losses.empty else 0

    # 손익비 (평균 수익 / 평균 손실)
    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else None

    # 월별 실현손익
    monthly = pd.DataFrame()
    if not sells.empty:
        sells["month"] = pd.to_datetime(sells["date"]).dt.strftime("%Y-%m")
        monthly = sells.groupby("month")["realized_pnl"].sum()

    # 종목별 실현손익
    by_ticker = sells.groupby("ticker")["realized_pnl"].sum().sort_values(ascending=False) if not sells.empty else pd.Series(dtype=float)

    return {
        "n_trades": len(df),
        "n_sells": len(sells),
        "total_realized": round(total_realized, 2),
        "win_rate": round(win_rate, 1),
        "avg_win": round(avg_win, 2) if avg_win else 0,
        "avg_loss": round(avg_loss, 2) if avg_loss else 0,
        "profit_factor": round(profit_factor, 2) if profit_factor else None,
        "monthly": monthly,
        "by_ticker": by_ticker,
    }


def apply_to_portfolio(ticker: str, side: str, quantity: float, price: float,
                       portfolio_file: str = None) -> Dict[str, Any]:
    """
    거래를 portfolio.csv에 반영.
    - 매수: 보유 시 수량 증가 + 평단가 재계산, 미보유 시 신규 행 추가
    - 매도: 수량 차감, 0이 되면 행 제거
    Returns: {"success": bool, "message": str, "avg_price": float(매도 시 평단가)}
    """
    pf_path = portfolio_file or portfolio_path()
    if not os.path.exists(pf_path):
        return {"success": False, "message": "portfolio.csv가 없습니다."}

    df = pd.read_csv(pf_path)
    ticker = ticker.upper()
    mask = df["ticker"].astype(str).str.upper() == ticker

    if side == "buy":
        if mask.any():
            i = df.index[mask][0]
            old_qty = float(df.at[i, "quantity"])
            old_avg = float(df.at[i, "avg_price"])
            new_qty = old_qty + quantity
            df.at[i, "avg_price"] = (old_qty * old_avg + quantity * price) / new_qty
            df.at[i, "quantity"] = new_qty
            msg = f"{ticker} 수량 {old_qty:.0f}→{new_qty:.0f}, 평단가 재계산됨"
        else:
            df = pd.concat([df, pd.DataFrame([{
                "ticker": ticker, "name": ticker, "quantity": quantity,
                "avg_price": price, "current_price": price,
            }])], ignore_index=True)
            msg = f"{ticker} 신규 편입 ({quantity:.0f}주)"
        df.to_csv(pf_path, index=False)
        return {"success": True, "message": msg, "avg_price": None}

    # sell
    if not mask.any():
        return {"success": False, "message": f"{ticker}는 포트폴리오에 없습니다."}
    i = df.index[mask][0]
    old_qty = float(df.at[i, "quantity"])
    avg = float(df.at[i, "avg_price"])
    if quantity > old_qty:
        return {"success": False, "message": f"보유 수량({old_qty:.0f}주)보다 많이 매도할 수 없습니다."}

    new_qty = old_qty - quantity
    if new_qty == 0:
        df = df.drop(i).reset_index(drop=True)
        msg = f"{ticker} 전량 매도 → 포트폴리오에서 제거"
    else:
        df.at[i, "quantity"] = new_qty
        msg = f"{ticker} 수량 {old_qty:.0f}→{new_qty:.0f}"
    df.to_csv(pf_path, index=False)
    return {"success": True, "message": msg, "avg_price": avg}
