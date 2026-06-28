"""
시장 데이터 캐시 레이어 (데이터 수집 하네스 #2)

새벽 cron이 주가/펀더멘털을 미리 긁어 data/cache/ 에 저장 →
페이지/시그널은 yfinance 라이브 호출 대신 캐시를 즉시 읽는다.

핵심 원칙 — **투명한 fallback**:
  캐시가 없거나(콜드) 오래됐으면(stale) 기존처럼 yfinance를 라이브로 호출한다.
  즉 캐시가 비어 있어도 동작은 "오늘과 100% 동일" → 안전하게 배포 가능.

저장 구조:
  data/cache/history/{safe_ticker}.parquet  — 일봉 OHLCV (넉넉히 2년)
  data/cache/info/{safe_ticker}.json        — yfinance .info (펀더멘털)
  data/cache/_meta.json                     — {ticker: {history_at, info_at}}
"""
import os
import json
import logging
from datetime import timedelta
from typing import Dict, Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_DIR = os.path.join(_BASE_DIR, "data", "cache")
HIST_DIR = os.path.join(CACHE_DIR, "history")
INFO_DIR = os.path.join(CACHE_DIR, "info")
META_PATH = os.path.join(CACHE_DIR, "_meta.json")

# 캐시 신선도: 마지막 수집 후 이 시간(h)이 지나면 stale → 라이브 fallback.
# 새벽 cron(KST 06:30경) 1회 수집으로 KST 하루를 커버하도록 18h 기본.
MAX_AGE_HOURS = float(os.getenv("MARKET_CACHE_MAX_AGE_H", "18"))

# 수집 시 보관하는 최대 히스토리 (period 슬라이싱의 상한)
COLLECT_PERIOD = "2y"

# period 문자열 → 대략 일수 (캐시 슬라이싱용, 여유분 포함)
_PERIOD_DAYS = {
    "1d": 4, "5d": 9, "1mo": 33, "3mo": 95, "6mo": 190,
    "1y": 372, "2y": 740, "5y": 1830, "max": 100000,
}


def _now_kst():
    from modules.daily_paper import now_kst
    return now_kst()


def _safe_name(ticker: str) -> str:
    """티커를 파일명 안전 문자열로 (^VIX, KRW=X, 005930.KS 등)."""
    return (ticker.replace("^", "_idx_").replace("=", "_eq_")
                  .replace("/", "_").replace("\\", "_"))


def _load_meta() -> Dict:
    if os.path.exists(META_PATH):
        try:
            with open(META_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_meta(meta: Dict):
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = META_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    os.replace(tmp, META_PATH)


def _touch_meta(ticker: str, key: str):
    meta = _load_meta()
    meta.setdefault(ticker, {})[key] = _now_kst().isoformat()
    _save_meta(meta)


def _is_fresh(ticker: str, key: str) -> bool:
    ts = _load_meta().get(ticker, {}).get(key)
    if not ts:
        return False
    try:
        fetched = pd.Timestamp(ts)
    except (ValueError, TypeError):
        return False
    now = pd.Timestamp(_now_kst())
    if fetched.tzinfo is None:
        now = now.tz_localize(None)
    return (now - fetched) < timedelta(hours=MAX_AGE_HOURS)


def _slice_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """저장된 2년치에서 요청 period만큼 tail 슬라이싱."""
    days = _PERIOD_DAYS.get(period)
    if not days or df.empty:
        return df
    try:
        cutoff = pd.Timestamp.now(tz=df.index.tz) - pd.Timedelta(days=days)
        sliced = df[df.index >= cutoff]
        return sliced if not sliced.empty else df
    except Exception:
        return df


# ──────────────────────────────────────────────
# 쓰기 (collector 전용)
# ──────────────────────────────────────────────
def save_history(ticker: str, df: pd.DataFrame) -> bool:
    if df is None or df.empty:
        return False
    try:
        os.makedirs(HIST_DIR, exist_ok=True)
        path = os.path.join(HIST_DIR, f"{_safe_name(ticker)}.parquet")
        df.to_parquet(path)
        _touch_meta(ticker, "history_at")
        return True
    except Exception as e:
        logger.warning(f"history 저장 실패 ({ticker}): {e}")
        return False


def save_info(ticker: str, info: Dict) -> bool:
    if not info:
        return False
    try:
        os.makedirs(INFO_DIR, exist_ok=True)
        path = os.path.join(INFO_DIR, f"{_safe_name(ticker)}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, default=str)
        _touch_meta(ticker, "info_at")
        return True
    except Exception as e:
        logger.warning(f"info 저장 실패 ({ticker}): {e}")
        return False


# ──────────────────────────────────────────────
# 읽기 (캐시 우선 → 라이브 fallback)
# ──────────────────────────────────────────────
def get_history(ticker: str, period: str = "1y", force_live: bool = False) -> pd.DataFrame:
    """일봉 히스토리. 신선한 캐시가 있으면 즉시 반환, 없으면 yfinance 라이브."""
    if not force_live and _is_fresh(ticker, "history_at"):
        path = os.path.join(HIST_DIR, f"{_safe_name(ticker)}.parquet")
        if os.path.exists(path):
            try:
                df = pd.read_parquet(path)
                if not df.empty:
                    return _slice_period(df, period)
            except Exception as e:
                logger.warning(f"history 읽기 실패 ({ticker}) → 라이브: {e}")

    # fallback: 라이브 호출. 넉넉히 받아 캐시도 갱신(다음 호출 가속).
    try:
        fetch_period = period if _PERIOD_DAYS.get(period, 0) >= _PERIOD_DAYS["2y"] else COLLECT_PERIOD
        df = yf.Ticker(ticker).history(period=fetch_period)
        if df is not None and not df.empty:
            save_history(ticker, df)
            return _slice_period(df, period)
        return df if df is not None else pd.DataFrame()
    except Exception as e:
        logger.warning(f"history 라이브 실패 ({ticker}): {e}")
        return pd.DataFrame()


def get_info(ticker: str, force_live: bool = False) -> Dict:
    """yfinance .info (펀더멘털). 캐시 우선 → 라이브."""
    if not force_live and _is_fresh(ticker, "info_at"):
        path = os.path.join(INFO_DIR, f"{_safe_name(ticker)}.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    info = json.load(f)
                if info:
                    return info
            except Exception as e:
                logger.warning(f"info 읽기 실패 ({ticker}) → 라이브: {e}")

    try:
        info = yf.Ticker(ticker).info
        if info:
            save_info(ticker, info)
        return info or {}
    except Exception as e:
        logger.warning(f"info 라이브 실패 ({ticker}): {e}")
        return {}


def cache_status() -> Dict:
    """캐시 현황 요약 (모니터링/디버깅용)."""
    meta = _load_meta()
    fresh_h = sum(1 for t in meta if _is_fresh(t, "history_at"))
    fresh_i = sum(1 for t in meta if _is_fresh(t, "info_at"))
    return {
        "tickers": len(meta),
        "fresh_history": fresh_h,
        "fresh_info": fresh_i,
        "max_age_hours": MAX_AGE_HOURS,
        "cache_dir": CACHE_DIR,
    }
