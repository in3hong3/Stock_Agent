"""CNN 패턴 인식기용 데이터셋 — patterns.py 규칙 탐지로 자동 라벨링.

원래 설계(패턴 이미지 vs None 분류)의 복귀판. 달라진 점 하나:
수동 조건으로 찾던 패턴 발생일을 규칙 탐지기(patterns.py)가 자동 라벨링한다.

- positive(pattern/): 이벤트 확정일 기준 과거 WINDOW일 차트 — 창 안에 패턴이 보임
- negative(none/):    이벤트 ±EXCLUDE일을 피한 무작위 날짜의 차트
- split: 기준일 날짜로 train/val 분리 (기존 TRAIN_END/VAL_START 재사용)

사용 (로컬):
    python ml/build_pattern_dataset.py --pattern double_bottom --max-tickers 30  # 테스트
    python ml/build_pattern_dataset.py --pattern double_bottom                   # 전체
"""

import argparse
import random
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_dataset import sp500_tickers
from chart import save_png
from config import IMG_SIZE, MAX_TICKERS, ML_DIR, TRAIN_END, VAL_START, WINDOW
from event_study import PATTERNS, fetch_cached

PATTERN_DATASET_DIR = ML_DIR / "dataset_patterns"
NEG_PER_POS = 2      # 패턴 1건당 none 샘플 수
EXCLUDE = 10         # 이벤트 앞뒤 이 거래일 안은 negative 후보에서 제외

random.seed(42)


def split_of(date: pd.Timestamp) -> str | None:
    if date <= pd.Timestamp(TRAIN_END):
        return "train"
    if date >= pd.Timestamp(VAL_START):
        return "val"
    return None  # embargo


def build(pattern_name: str, max_tickers: int) -> None:
    detect = PATTERNS[pattern_name]
    out_root = PATTERN_DATASET_DIR / pattern_name
    counts = {"train": {"pattern": 0, "none": 0}, "val": {"pattern": 0, "none": 0}}

    for ticker, _name in tqdm(sp500_tickers(max_tickers), desc=f"라벨링({pattern_name})"):
        df = fetch_cached(ticker)
        if df is None:
            continue

        ev_pos = [df.index.get_loc(d) for d in detect(df)]
        ev_pos = [p for p in ev_pos if p >= WINDOW - 1]
        if not ev_pos:
            continue

        # negative 후보: 이벤트 주변(±EXCLUDE) 제외한 모든 위치
        banned = set()
        for p in ev_pos:
            banned.update(range(p - EXCLUDE, p + EXCLUDE + 1))
        neg_cand = [i for i in range(WINDOW - 1, len(df)) if i not in banned]
        neg_pos = random.sample(neg_cand, min(len(neg_cand), len(ev_pos) * NEG_PER_POS))

        for label, positions in (("pattern", ev_pos), ("none", neg_pos)):
            for p in positions:
                date = df.index[p]
                sp = split_of(date)
                if sp is None:
                    continue
                win = df.iloc[p - WINDOW + 1: p + 1]
                if (win["Volume"] == 0).any():
                    continue
                d = out_root / sp / label
                d.mkdir(parents=True, exist_ok=True)
                save_png(win, d / f"{ticker}_{date:%Y%m%d}.png", IMG_SIZE)
                counts[sp][label] += 1

    total = sum(sum(v.values()) for v in counts.values())
    print(f"\n샘플 {total}개 생성 → {out_root}")
    for sp in ("train", "val"):
        c = counts[sp]
        print(f"  {sp}: pattern {c['pattern']} / none {c['none']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", choices=list(PATTERNS), default="double_bottom")
    ap.add_argument("--max-tickers", type=int, default=MAX_TICKERS)
    args = ap.parse_args()
    build(args.pattern, args.max_tickers)


if __name__ == "__main__":
    main()
