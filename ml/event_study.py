"""이벤트 스터디 — "패턴 X 발생 후 N일 뒤 어떻게 됐나"를 과거 데이터로 통계 낸다.

핵심 설계:
- **기저율 비교**: S&P는 우상향이라 아무 날이나 찍어도 1개월 뒤 오를 확률이 ~60%.
  패턴의 승률은 반드시 "같은 종목·기간의 모든 날(기저율)" 대비 몇 %p 우위인지로 본다.
- **전/후반 교차검증**: IS_OOS_SPLIT 이전(전반)에서 보인 우위가 이후(후반)에서도
  유지돼야 진짜. 전반에서만 좋으면 우연(다중 검정)일 가능성.

사용 (로컬):
    python ml/event_study.py --pattern ma50 --max-tickers 30    # 소량 테스트
    python ml/event_study.py --pattern double_bottom            # S&P500 전체
"""

import argparse
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대응

import FinanceDataReader as fdr
import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
import patterns
from build_dataset import sp500_tickers
from config import (CACHE_DIR, EVENT_HORIZONS, IS_OOS_SPLIT, MAX_TICKERS,
                    START_DATE, STUDY_DIR)

PATTERNS = {
    "ma50": patterns.ma50_touch_bounce,
    "double_bottom": patterns.double_bottom,
    "drop10": patterns.sharp_drop,
    "drop10_above200": patterns.sharp_drop_above_ma200,   # 추세 위 급락 = 흔들기?
    "drop10_below200": patterns.sharp_drop_below_ma200,   # 추세 아래 급락 = 붕괴?
    "high52w": patterns.high_52w_breakout,                # 신고가 = 사는 자리 vs 꼭지?
    "head_shoulders": patterns.head_shoulders,            # 약세 반전 — 우위는 음(-)이어야 작동
}


def fetch_cached(ticker: str) -> pd.DataFrame | None:
    """OHLCV 로드 — ml/cache/에 csv 캐시 (재실행 시 재다운로드 방지)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fp = CACHE_DIR / f"{ticker}.csv"
    if fp.exists():
        df = pd.read_csv(fp, index_col=0, parse_dates=True)
    else:
        try:
            df = fdr.DataReader(ticker, START_DATE)[["Open", "High", "Low", "Close", "Volume"]].dropna()
            df.to_csv(fp)
            time.sleep(0.2)  # rate limit 예방
        except Exception:
            return None
    return df if len(df) >= 120 else None


def forward_returns(close: pd.Series, positions: np.ndarray, horizons: list) -> pd.DataFrame:
    """각 위치(iloc)에서 h거래일 뒤 수익률. 미래 데이터가 없는 위치는 NaN."""
    c = close.to_numpy()
    n = len(c)
    out = {}
    for h in horizons:
        r = np.full(len(positions), np.nan)
        ok = positions + h < n
        r[ok] = c[positions[ok] + h] / c[positions[ok]] - 1
        out[f"ret_{h}d"] = r
    return pd.DataFrame(out)


def stats_table(rets: pd.DataFrame, horizons: list) -> pd.DataFrame:
    """승률/평균/중앙값 요약."""
    rows = []
    for h in horizons:
        r = rets[f"ret_{h}d"].dropna()
        rows.append({
            "horizon": f"+{h}d",
            "n": len(r),
            "win%": r.gt(0).mean() * 100 if len(r) else np.nan,
            "avg%": r.mean() * 100 if len(r) else np.nan,
            "med%": r.median() * 100 if len(r) else np.nan,
        })
    return pd.DataFrame(rows).set_index("horizon")


def run_study(pattern_name: str, max_tickers: int) -> None:
    detect = PATTERNS[pattern_name]
    tickers = sp500_tickers(max_tickers)

    ev_rows, base_frames = [], []
    fail = 0
    for ticker, name in tqdm(tickers, desc=f"탐지({pattern_name})"):
        df = fetch_cached(ticker)
        if df is None:
            fail += 1
            continue
        close = df["Close"]

        # 기저율: 이 종목의 '모든 날' 수익률 (같은 분포에서 비교해야 공정)
        all_pos = np.arange(len(df))
        base = forward_returns(close, all_pos, EVENT_HORIZONS)
        base["date"] = df.index
        base_frames.append(base)

        # 이벤트
        for dt in detect(df):
            pos = df.index.get_loc(dt)
            fr = forward_returns(close, np.array([pos]), EVENT_HORIZONS).iloc[0]
            ev_rows.append({"ticker": ticker, "name": name, "date": dt, **fr.to_dict()})

    events = pd.DataFrame(ev_rows)
    baseline = pd.concat(base_frames, ignore_index=True)
    split = pd.Timestamp(IS_OOS_SPLIT)

    print(f"\n{'=' * 62}")
    print(f"패턴: {pattern_name} · 종목 {len(tickers) - fail}개 · 이벤트 {len(events)}건")
    if events.empty:
        print("이벤트가 없습니다 — 조건이 너무 빡빡한지 patterns.py 파라미터 확인.")
        return

    def section(title, ev, ba):
        print(f"\n── {title} " + "─" * (56 - len(title)))
        s_ev = stats_table(ev, EVENT_HORIZONS)
        s_ba = stats_table(ba, EVENT_HORIZONS)
        merged = s_ev.join(s_ba, rsuffix="_기저")
        merged["우위(승률%p)"] = merged["win%"] - merged["win%_기저"]
        merged["우위(평균%p)"] = merged["avg%"] - merged["avg%_기저"]
        cols = ["n", "win%", "win%_기저", "우위(승률%p)", "avg%", "avg%_기저", "우위(평균%p)", "med%"]
        print(merged[cols].round(2).to_string())

    section("전체 기간", events, baseline)
    section(f"전반부 in-sample (< {IS_OOS_SPLIT})",
            events[events["date"] < split], baseline[baseline["date"] < split])
    section(f"후반부 out-of-sample (≥ {IS_OOS_SPLIT})",
            events[events["date"] >= split], baseline[baseline["date"] >= split])

    print(f"\n읽는 법: '우위(승률%p)'가 전반·후반 **둘 다** 같은 방향으로 +면 진짜 우위 후보.")
    print(f"전반만 좋고 후반에서 사라지면 우연일 가능성이 큼.")

    STUDY_DIR.mkdir(parents=True, exist_ok=True)
    ev_path = STUDY_DIR / f"{pattern_name}_events.csv"
    events.to_csv(ev_path, index=False, encoding="utf-8-sig")
    print(f"\n이벤트 상세 저장 → {ev_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", choices=list(PATTERNS), default="ma50")
    ap.add_argument("--max-tickers", type=int, default=MAX_TICKERS)
    args = ap.parse_args()
    run_study(args.pattern, args.max_tickers)


if __name__ == "__main__":
    main()
