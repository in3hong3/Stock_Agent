"""포트폴리오 공통 유틸리티"""
import os
from datetime import date
import pandas as pd

from utils.user_data import asset_history_path


def _history_file() -> str:
    return asset_history_path()


def record_asset_snapshot(total_krw: float, stock_krw: float, cash_krw: float):
    """
    오늘자 총자산 스냅샷 기록 (하루 1행, 같은 날 재기록 시 갱신).
    트래커 탭이 열릴 때마다 자동 호출되어 자산 추이가 쌓인다.
    """
    today = date.today().strftime("%Y-%m-%d")
    row = {"date": today, "total": round(total_krw), "stock": round(stock_krw), "cash": round(cash_krw)}

    if os.path.exists(_history_file()):
        df = pd.read_csv(_history_file())
        df = df[df["date"] != today]  # 오늘 기존 행 제거 후 최신값으로 교체
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        os.makedirs(os.path.dirname(_history_file()), exist_ok=True)
        df = pd.DataFrame([row])

    df.sort_values("date").to_csv(_history_file(), index=False)


def load_asset_history() -> pd.DataFrame:
    """자산 추이 로드 (date 인덱스). 없으면 빈 DataFrame."""
    if not os.path.exists(_history_file()):
        return pd.DataFrame()
    df = pd.read_csv(_history_file(), parse_dates=["date"])
    return df.set_index("date").sort_index()


def calc_portfolio_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    eval_amount, profit_loss, profit_rate 컬럼 계산.
    quantity * current_price = 평가금액, 평단가 대비 손익/수익률을 추가한 DataFrame 반환.
    원본 df는 수정하지 않는다.
    """
    out = df.copy()
    out["eval_amount"] = out["quantity"] * out["current_price"]
    cost = out["quantity"] * out["avg_price"]
    out["profit_loss"] = out["eval_amount"] - cost
    out["profit_rate"] = (out["profit_loss"] / cost.replace(0, float("nan"))) * 100
    out["profit_rate"] = out["profit_rate"].fillna(0)
    return out
