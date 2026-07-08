"""2~4단계: 코스피200 데이터 다운로드 → 미래 수익률 라벨 → 차트 이미지 데이터셋 생성.

- 입력 이미지: 기준일까지의 과거 WINDOW 거래일 캔들 + 거래량 (미래 데이터 절대 포함 안 함)
- 라벨: HORIZON 거래일 뒤 종가 수익률 > RET_THRESHOLD → 'up', 아니면 'down'
- train/val 분리: 기준일 날짜로 분리 (TRAIN_END 이전 → train, VAL_START 이후 → val,
  사이 구간은 라벨 누수 방지용 embargo로 버림)

사용:
    python ml/build_dataset.py                     # 코스피200 전체
    python ml/build_dataset.py --max-tickers 3     # 테스트용 소량
"""

import argparse
import sys

sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대응

import time

import FinanceDataReader as fdr
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from chart import save_png
from config import (DATASET_DIR, HORIZON, IMG_SIZE, MANIFEST_CSV, MAX_TICKERS,
                    RET_THRESHOLD, START_DATE, STRIDE, TRAIN_END, VAL_START,
                    WINDOW)


def kospi_top_tickers(n: int) -> list[tuple[str, str]]:
    """시가총액 상위 n개 (보통주만, 스팩 제외). [(코드, 종목명), ...]"""
    krx = fdr.StockListing("KOSPI")  # Marcap 내림차순 정렬되어 옴
    krx = krx[krx["Code"].str.endswith("0")]          # 우선주 제외
    krx = krx[~krx["Name"].str.contains("스팩")]
    return list(krx[["Code", "Name"]].head(n).itertuples(index=False, name=None))


def fetch_ohlcv(ticker: str) -> pd.DataFrame:
    df = fdr.DataReader(ticker, START_DATE)
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


def split_of(base_date: pd.Timestamp) -> str | None:
    if base_date <= pd.Timestamp(TRAIN_END):
        return "train"
    if base_date >= pd.Timestamp(VAL_START):
        return "val"
    return None  # embargo 구간


def build_for_ticker(ticker: str, name: str) -> list[dict]:
    df = fetch_ohlcv(ticker)
    rows = []
    close = df["Close"]
    for i in range(WINDOW - 1, len(df) - HORIZON, STRIDE):
        base_date = df.index[i]
        split = split_of(base_date)
        if split is None:
            continue
        win = df.iloc[i - WINDOW + 1: i + 1]
        if (win["Volume"] == 0).any():  # 거래정지 낀 구간 제외
            continue
        fwd_ret = close.iloc[i + HORIZON] / close.iloc[i] - 1
        label = "up" if fwd_ret > RET_THRESHOLD else "down"
        out_dir = DATASET_DIR / split / label
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{ticker}_{base_date:%Y%m%d}.png"
        if not path.exists():  # 재실행 시 이미 만든 이미지는 건너뜀
            save_png(win, path, IMG_SIZE)
        rows.append({"ticker": ticker, "name": name,
                     "date": f"{base_date:%Y-%m-%d}", "fwd_ret": round(fwd_ret, 5),
                     "label": label, "split": split, "path": str(path)})
    return rows


def main() -> None:
    global STRIDE
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-tickers", type=int, default=MAX_TICKERS)
    ap.add_argument("--stride", type=int, default=STRIDE)
    args = ap.parse_args()
    STRIDE = args.stride

    tickers = kospi_top_tickers(args.max_tickers)
    print(f"대상 종목 {len(tickers)}개 · 윈도우 {WINDOW}일 · 라벨 {HORIZON}일 뒤 "
          f"수익률 > {RET_THRESHOLD:+.1%} · stride {STRIDE}")

    all_rows, failed = [], []
    for ticker, name in tqdm(tickers, desc="종목"):
        try:
            all_rows.extend(build_for_ticker(ticker, name))
            time.sleep(0.2)  # 데이터 서버 예의
        except Exception as e:  # 한 종목 실패해도 계속
            failed.append((ticker, str(e)))

    manifest = pd.DataFrame(all_rows)
    MANIFEST_CSV.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(MANIFEST_CSV, index=False, encoding="utf-8-sig")

    print(f"\n샘플 {len(manifest)}개 생성 → {DATASET_DIR}")
    if len(manifest):
        print(manifest.groupby(["split", "label"]).size().to_string())
        print(f"\nup 비율 — train: {(manifest[manifest.split=='train'].label=='up').mean():.1%}"
              f" · val: {(manifest[manifest.split=='val'].label=='up').mean():.1%}")
    if failed:
        print(f"\n실패 종목 {len(failed)}개: {failed[:10]}")


if __name__ == "__main__":
    main()
