"""보유 종목 패턴 스캔 — "지금 이 종목 차트에 이중바닥 모양이 있나?"

패턴 인식 CNN(pattern_double_bottom.pth, val AUC 0.988)이 각 보유 종목의
최근 WINDOW일 차트를 보고 '이중바닥 확률'을 매긴다. 규칙 탐지기(patterns.py)의
판정과 이벤트 스터디 통계를 함께 담아 ml/signals/patterns_latest.json 저장.

⚠ 로컬(GPU 노트북) 전용. 매매 신호가 아니라 '패턴 감지 + 그 패턴의 과거 통계' 정보.

사용:
    python ml/predict_pattern.py
    python ml/predict_pattern.py --tickers NVDA AMZN
"""

import argparse
import base64
import io
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import FinanceDataReader as fdr
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import models

sys.path.insert(0, str(Path(__file__).resolve().parent))
import patterns
from chart import to_png_bytes
from config import DROPOUT, IMG_SIZE, MODELS_DIR, WINDOW
from predict import _TF, SIGNALS_DIR, load_watchlist_tickers

PATTERNS_JSON = SIGNALS_DIR / "patterns_latest.json"

# 이벤트 스터디(S&P500 496종목, 2020~2026, 7,716건) 요약 — event_study.py 재실행으로 갱신
DOUBLE_BOTTOM_STATS = {
    "pattern_kr": "이중바닥 (넥라인 돌파)",
    "n_events": 7716,
    "summary": "돌파 후 1~2주 승률은 기저율 수준, 3개월은 오히려 시장평균보다 -1.5~-2.2%p 열위 (전/후반 일관). "
               "'이중바닥 = 중기 강세'라는 통설은 이 데이터에서 확인되지 않음 — 중기 홀드 근거로 쓰지 말 것.",
}


def load_pattern_model(device):
    ckpt_path = MODELS_DIR / "pattern_double_bottom.pth"
    if not ckpt_path.exists():
        sys.exit(f"패턴 모델이 없습니다: {ckpt_path}\n"
                 "python ml/build_pattern_dataset.py && python ml/train.py "
                 "--data-dir ml/dataset_patterns/double_bottom --out pattern_double_bottom.pth")
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)  # 자체 생성 파일
    model = models.resnet18(weights=None)
    model.fc = torch.nn.Sequential(torch.nn.Dropout(DROPOUT),
                                   torch.nn.Linear(model.fc.in_features, 2))
    model.load_state_dict(ckpt["state_dict"])
    model.eval().to(device)
    return model, ckpt


@torch.no_grad()
def scan_one(model, device, symbol: str):
    """(패턴확률, 규칙탐지 최근여부, png, 기준일) — 데이터 부족 시 None."""
    start = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
    df = fdr.DataReader(symbol, start)[["Open", "High", "Low", "Close", "Volume"]].dropna()
    if len(df) < WINDOW:
        return None
    win = df.iloc[-WINDOW:]
    png = to_png_bytes(win, IMG_SIZE)
    x = _TF(Image.open(io.BytesIO(png)).convert("RGB")).unsqueeze(0).to(device)
    prob = F.softmax(model(x).float(), dim=1)[0, 1].item()  # 클래스1 = pattern

    # 규칙 탐지기 교차확인: 최근 10거래일 내 확정 이벤트가 있었나
    events = patterns.double_bottom(df)
    recent_rule = any(df.index.get_loc(d) >= len(df) - 10 for d in events)
    return prob, recent_rule, png, f"{win.index[-1]:%Y-%m-%d}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, ckpt = load_pattern_model(device)
    print(f"패턴 인식 CNN 로드 (val AUC {ckpt.get('val_auc', float('nan')):.4f}) · device {device}")

    targets = [(t, t) for t in args.tickers] if args.tickers else load_watchlist_tickers()
    if not targets:
        sys.exit("대상 종목이 없습니다.")

    results = []
    for symbol, name in targets:
        try:
            res = scan_one(model, device, symbol)
            if res is None:
                print(f"  {symbol} {name}: 데이터 부족 → 건너뜀")
                continue
            prob, recent_rule, png, as_of = res
            tag = " ✓규칙탐지도 최근 확정" if recent_rule else ""
            print(f"  {symbol} {name}: 이중바닥 확률 {prob:.1%}{tag}")
            results.append({
                "ticker": symbol, "name": name, "as_of": as_of,
                "prob_pattern": round(prob, 4), "rule_confirmed_recent": recent_rule,
                "thumb": "data:image/png;base64," + base64.b64encode(png).decode(),
            })
        except Exception as e:
            print(f"  {symbol} {name}: 실패 → {e}")

    results.sort(key=lambda r: r["prob_pattern"], reverse=True)
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "model": "pattern_double_bottom(resnet18)",
        "val_auc": ckpt.get("val_auc"),
        "window_days": WINDOW,
        "event_stats": DOUBLE_BOTTOM_STATS,
        "scans": results,
    }
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    with open(PATTERNS_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n{len(results)}종목 → {PATTERNS_JSON} ({PATTERNS_JSON.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
