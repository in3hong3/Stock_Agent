"""포트폴리오 메타 (시드/리스크/현금/시세 갱신 시각) 공용 helper.

tracker, portfolio 페이지에서 함께 읽고 씀.
"""
import os
import json
import datetime
import pandas as pd
import streamlit as st
from utils.user_data import portfolio_meta_path, portfolio_path


def _price_meta_file() -> str:
    return portfolio_meta_path()


def load_meta() -> dict:
    try:
        with open(_price_meta_file(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_meta(**updates):
    """기존 메타를 유지하면서 일부 키만 갱신"""
    meta = load_meta()
    meta.update(updates)
    path = _price_meta_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def save_price_timestamp():
    save_meta(price_updated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))


def load_price_timestamp() -> str:
    return load_meta().get("price_updated_at", "기록 없음")


def load_cash() -> dict:
    """{'krw': float, 'usd': float}"""
    meta = load_meta()
    return {"krw": float(meta.get("cash_krw", 0) or 0), "usd": float(meta.get("cash_usd", 0) or 0)}


def resolve_stance() -> str:
    """session_state.advisor_stance(라벨) → stance 키('aggressive' 등). 기본 aggressive."""
    from modules.portfolio_advisor import PERSONAS
    saved_label = st.session_state.get("advisor_stance", "")
    for k, v in PERSONAS.items():
        if saved_label.startswith(v["label"]):
            return k
    return "aggressive"


@st.cache_data(ttl=300)
def get_cached_signals(holdings_key, stance, seed, risk):
    """매매 시그널 캐시 — 사이드/트래커가 같은 결과를 공유 (중복 계산 방지).
    holdings_key는 캐시 무효화용 (ticker/qty/avg/current_price 튜플).
    """
    from modules.trade_signal import generate_signals
    from modules.issue_tracker import get_portfolio_holdings
    return generate_signals(get_portfolio_holdings(), stance, seed, risk)


def compute_total_assets(holdings: list, fx: float) -> dict:
    """보유 종목(csv current_price) + 현금으로 원화 기준 총자산 계산.

    한국주(.KS/.KQ)는 그대로, 그 외(달러)는 fx 곱해서 원화 환산.
    가격 누락 종목은 평가액 0 처리. 트래커/사이드가 같은 값을 쓰도록 단일화.
    """
    cash = load_cash()
    stock_eval = 0.0
    stock_cost = 0.0
    for h in holdings or []:
        try:
            qty = float(h.get("quantity", 0) or 0)
            cur = float(h.get("current_price", 0) or 0)
            avg = float(h.get("avg_price", 0) or 0)
        except (TypeError, ValueError):
            continue
        is_kr = str(h.get("ticker", "")).endswith((".KS", ".KQ"))
        factor = 1.0 if is_kr else fx
        stock_eval += qty * cur * factor
        stock_cost += qty * avg * factor

    pnl = stock_eval - stock_cost
    pnl_rate = (pnl / stock_cost * 100) if stock_cost > 0 else 0.0
    cash_total = cash["krw"] + cash["usd"] * fx
    total = stock_eval + cash_total
    cash_ratio = (cash_total / total * 100) if total > 0 else 0.0
    return {
        "stock_eval": stock_eval, "stock_cost": stock_cost,
        "pnl": pnl, "pnl_rate": pnl_rate,
        "cash_total": cash_total, "total": total, "cash_ratio": cash_ratio,
    }


def auto_fill_missing_prices(session_key: str = "_auto_price_fill_done"):
    """portfolio.csv에서 current_price가 비어있는 종목을 yfinance로 자동 채움.

    가드 없음 — 페이지 진입 시 빈 가격이 있으면 항상 시도. 빈 가격 종목이 없으면
    yfinance 호출 자체가 일어나지 않으므로 비용/지연 부담 없음. (사용자가 명시적으로
    가격 업데이트 버튼을 누르는 흐름과 무관.)
    """
    # session_key 인자는 호환성 유지용 — 더 이상 가드로 사용하지 않음.
    _ = session_key

    try:
        path = portfolio_path()
        if not os.path.exists(path):
            return False
        df = pd.read_csv(path)
    except Exception as e:
        print(f"가격 자동 채움 — CSV 로드 실패: {e}")
        return False

    if df.empty or "current_price" not in df.columns:
        return False

    df["current_price"] = pd.to_numeric(df["current_price"], errors="coerce")
    missing_mask = df["current_price"].isna() | (df["current_price"] <= 0)
    if not missing_mask.any():
        return False

    missing_tickers = df.loc[missing_mask, "ticker"].astype(str).tolist()
    from utils.price_updater import PriceUpdater
    updater = PriceUpdater()

    with st.spinner(f"💸 빈 가격 자동 갱신 중 ({len(missing_tickers)}종목)..."):
        filled = []
        failed = []
        # 빈 가격 종목 수가 적으면 batch yf.download(1m interval)가 휴장/장외에
        # 빈 결과를 자주 줘서 fallback이 더 자주 호출됨. 종목 5개 이하면 처음부터
        # 안정적인 fast_info 경로(get_current_price)를 직접 사용한다.
        if len(missing_tickers) > 5:
            batch = updater.get_batch_prices(missing_tickers)
        else:
            batch = {}
        import math
        for idx in df.index[missing_mask]:
            ticker = str(df.at[idx, "ticker"])
            price = batch.get(ticker)
            # NaN 비교는 항상 False라 따로 잡아야 fallback이 호출됨
            invalid = price is None or (isinstance(price, float) and math.isnan(price)) or price <= 0
            if invalid:
                price = updater.get_current_price(ticker)
            if price and not (isinstance(price, float) and math.isnan(price)) and price > 0:
                df.at[idx, "current_price"] = float(price)
                filled.append(ticker)
            else:
                failed.append(ticker)

    if filled:
        try:
            df.to_csv(path, index=False)
            save_price_timestamp()
            st.session_state["reload_csv"] = True
            # 트래커의 cached_snapshot 등 가격 의존 캐시 무효화
            st.cache_data.clear()
            st.toast(f"💸 {len(filled)}종목 가격 자동 채움 ({', '.join(filled[:5])}{'...' if len(filled) > 5 else ''})")
        except Exception as e:
            print(f"가격 자동 채움 — CSV 저장 실패: {e}")

    if failed:
        st.warning(
            f"⚠️ 자동 갱신 실패한 종목: {', '.join(failed)}. "
            f"포트폴리오 탭의 **'📡 가격 업데이트'** 버튼으로 다시 시도해 보세요."
        )

    if filled:
        st.rerun()

    return bool(filled)
