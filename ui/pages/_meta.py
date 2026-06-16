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


def auto_fill_missing_prices(session_key: str = "_auto_price_fill_done"):
    """portfolio.csv에서 current_price가 비어있는 종목을 yfinance로 자동 채움.

    각 페이지 진입 시 1회만 시도 (session_state 가드). 이후 가격 업데이트 버튼
    수동 실행 흐름과 충돌하지 않음. 채움이 일어났으면 rerun으로 갱신.
    """
    if st.session_state.get(session_key):
        return False

    try:
        path = portfolio_path()
        if not os.path.exists(path):
            return False
        df = pd.read_csv(path)
    except Exception as e:
        print(f"가격 자동 채움 — CSV 로드 실패: {e}")
        st.session_state[session_key] = True
        return False

    if df.empty or "current_price" not in df.columns:
        st.session_state[session_key] = True
        return False

    df["current_price"] = pd.to_numeric(df["current_price"], errors="coerce")
    missing_mask = df["current_price"].isna() | (df["current_price"] <= 0)
    if not missing_mask.any():
        st.session_state[session_key] = True
        return False

    # 이번 진입에서는 한 번만 시도 (실패해도 무한루프 방지)
    st.session_state[session_key] = True

    missing_tickers = df.loc[missing_mask, "ticker"].astype(str).tolist()
    from utils.price_updater import PriceUpdater
    updater = PriceUpdater()

    with st.spinner(f"💸 빈 가격 자동 갱신 중 ({len(missing_tickers)}종목)..."):
        filled = []
        failed = []
        # 배치 시도 후 실패한 것만 개별 fallback
        batch = updater.get_batch_prices(missing_tickers)
        for idx in df.index[missing_mask]:
            ticker = str(df.at[idx, "ticker"])
            price = batch.get(ticker)
            if price is None:
                price = updater.get_current_price(ticker)
            if price and price > 0:
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
