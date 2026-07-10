"""CNN 매수 신호 모델 — 공용 설정.

라벨 정의: 기준일 종가 대비 HORIZON 거래일 뒤 종가 수익률이
RET_THRESHOLD 초과면 'up', 아니면 'down'.
이미지 입력: 기준일까지의 과거 WINDOW 거래일 캔들+거래량 차트 (미래 데이터 없음).
"""

from pathlib import Path

ML_DIR = Path(__file__).resolve().parent

# ── 데이터셋 ──────────────────────────────────────────────
DATASET_DIR = ML_DIR / "dataset"          # dataset/{train,val}/{up,down}/*.png
MANIFEST_CSV = ML_DIR / "dataset" / "manifest.csv"
MODELS_DIR = ML_DIR / "models"

# ── 유니버스 / 기간 ───────────────────────────────────────
# 미국주식(S&P500)으로 학습 — 사용자 포트폴리오가 미국주라 분포를 맞춘다.
MAX_TICKERS = 500                          # S&P500 중 앞에서 N개 (줄이면 학습 빨라짐)
START_DATE = "2020-01-01"                  # 다운로드 시작일
TRAIN_END = "2024-12-31"                   # 이 날짜까지 기준일 → train
VAL_START = "2025-02-15"                   # 이 날짜부터 기준일 → val
#   embargo: HORIZON(20거래일≈1개월)만큼 train 라벨이 미래로 뻗으므로,
#   TRAIN_END 이후 최소 1개월+ 띄워야 train 라벨이 val 구간과 겹치지 않는다.

# ── 샘플 / 라벨 ───────────────────────────────────────────
# "하루하루"가 아니라 몇 주~몇 달의 큰 흐름을 예측하는 게 목표:
#   입력은 6개월(120일) 차트로 큰 그림을 보고, 1개월(20일) 뒤의 방향을 맞힌다.
WINDOW = 120                               # 이미지에 담을 과거 거래일 수 (≈6개월)
HORIZON = 20                               # 며칠 뒤 수익률로 라벨을 만들지 (≈1개월)
RET_THRESHOLD = 0.05                       # HORIZON 동안 +5% 초과 상승이면 up (노이즈 컷)
STRIDE = 5                                 # 며칠 간격으로 샘플을 뽑을지 (1 = 매일)

# ── 이벤트 스터디 (규칙 기반 패턴 통계 — ML 없음) ─────────
CACHE_DIR = ML_DIR / "cache"               # OHLCV 캐시 (재다운로드 방지)
STUDY_DIR = ML_DIR / "study"               # 이벤트 스터디 결과 (csv)
EVENT_HORIZONS = [5, 10, 21, 63]           # 이벤트 후 N거래일 뒤 수익률 (1주/2주/1달/3달)
IS_OOS_SPLIT = "2023-07-01"                # 전반(in-sample)/후반(out-of-sample) 분할일
#   전반부에서 보인 우위가 후반부에서도 유지돼야 진짜 (다중 검정/우연 방지)

# ── 이미지 ────────────────────────────────────────────────
IMG_SIZE = 224                             # 픽셀 (정사각형)

# ── 학습 ──────────────────────────────────────────────────
BATCH_SIZE = 64
LR = 5e-5                                   # 낮춰서 급한 과적합 방지 (기존 1e-4는 epoch2부터 외움)
WEIGHT_DECAY = 1e-4                         # 가중치 규제 → 과적합 억제
DROPOUT = 0.4                               # 분류층 dropout → 암기 방지
MAX_EPOCHS = 30
EARLY_STOP_PATIENCE = 5
NUM_WORKERS = 2
