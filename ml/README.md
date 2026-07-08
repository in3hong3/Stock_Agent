# 차트 이미지 CNN 매수 신호 모델

과거 60거래일 캔들차트 이미지를 보고 **5거래일 뒤 상승 확률**을 예측하는
ResNet18 전이학습 모델. (참고: Jiang, Kelly, Xiu — *(Re-)Imaging Price Trends*)

⚠ **로컬(RTX 5060 노트북) 전용.** Oracle 서버(RAM 1GB)에서는 PyTorch 로드 불가 —
서버 연동이 필요해지면 로컬 추론 후 결과만 전송하거나 ONNX 변환으로 간다.

## 설계 원칙 (수정 금지 아님, 바꿀 때 아래 함정만 기억)

1. **라벨은 미래 수익률** — 규칙(망치형 등)으로 만든 라벨은 CNN이 그 규칙을
   복제할 뿐 새 정보가 없다.
2. **이미지에 미래 데이터 금지** — 기준일까지의 과거 60일만. 기준일 이후
   데이터가 들어가면 lookahead 누수.
3. **train/val은 기간으로 분리** — 이미지 단위 랜덤 split은 같은 종목의
   비슷한 시기 차트가 양쪽에 들어가 성능이 뻥튀기된다. embargo(HORIZON 이상)
   구간도 사이에 둔다.
4. **지표는 AUC** — val AUC 0.52~0.55면 신호로 유의미, 0.50 근처면 실패.
   90% 정확도가 나오면 좋은 게 아니라 누수를 의심할 것.

## 실행 순서

```bash
python ml/check_gpu.py                      # 1. GPU 인식 확인
python ml/build_dataset.py --max-tickers 3  # 2. 소량 테스트
python ml/build_dataset.py                  # 3. 코스피200 전체 (수 시간 소요)
python ml/train.py                          # 4. 학습 → ml/models/best_resnet18.pth
```

설정(윈도우/호라이즌/임계값/기간)은 전부 [config.py](config.py).
데이터셋 명세는 `ml/dataset/manifest.csv` (종목·날짜·실현수익률·라벨·split).

## 의존성 (로컬 전용 — 서버 requirements에 넣지 말 것)

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install mplfinance finance-datareader tqdm
```
