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
VAL_START = "2025-01-15"                   # 이 날짜부터 기준일 → val (사이 구간은 embargo)

# ── 샘플 / 라벨 ───────────────────────────────────────────
WINDOW = 60                                # 이미지에 담을 과거 거래일 수
HORIZON = 5                                # 며칠 뒤 수익률로 라벨을 만들지
RET_THRESHOLD = 0.0                        # 초과 시 up (0.0 = 단순 상승/하락)
STRIDE = 5                                 # 며칠 간격으로 샘플을 뽑을지 (1 = 매일)

# ── 이미지 ────────────────────────────────────────────────
IMG_SIZE = 224                             # 픽셀 (정사각형)

# ── 학습 ──────────────────────────────────────────────────
BATCH_SIZE = 64
LR = 1e-4
MAX_EPOCHS = 30
EARLY_STOP_PATIENCE = 5
NUM_WORKERS = 2
