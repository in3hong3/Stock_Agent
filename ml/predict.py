"""로컬 추론: 관심/보유 종목의 최근 6개월 차트 → 약 1개월 뒤 상승 확률.

결과를 ml/signals/latest.json 에 저장한다 (차트 썸네일은 base64로 임베드).
이 JSON은 git에 커밋되어 Oracle 서버로 pull되고, Streamlit 'AI 신호' 탭이
읽어서 표시만 한다 — 서버에는 torch/mplfinance가 없어도 된다.

⚠ 로컬(GPU 노트북)에서만 실행. 서버에서 실행 금지.

사용:
    python ml/predict.py                          # 관심종목(admin) 자동
    python ml/predict.py --tickers 005930 000660  # 종목 직접 지정
"""

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대응

import FinanceDataReader as fdr
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import models, transforms

sys.path.insert(0, str(Path(__file__).resolve().parent))    # ml/ 우선 (chart, config)
sys.path.append(str(Path(__file__).resolve().parent.parent))  # 루트는 뒤 (modules — 루트 config 패키지와 충돌 방지)
from chart import to_png_bytes
from config import DROPOUT, HORIZON, IMG_SIZE, MODELS_DIR, WINDOW

SIGNALS_DIR = Path(__file__).resolve().parent / "signals"
LATEST_JSON = SIGNALS_DIR / "latest.json"

_TF = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


def to_symbol(ticker: str) -> str | None:
    """티커를 FDR 미국 심볼로. 이 모델은 S&P500(미국)으로 학습 → 미국 종목만 지원."""
    t = ticker.strip().upper()
    if t.endswith((".KS", ".KQ")) or (t.isdigit() and len(t) == 6):
        return None  # 한국 종목은 이 모델(미국 차트 학습) 대상 아님 → 건너뜀
    return t  # 미국 심볼 (AAPL, GOOGL 등)


def load_watchlist_tickers() -> list[tuple[str, str]]:
    """admin 관심종목 + 보유종목 → [(미국심볼, 종목명)] (미국 종목만, 중복 제거)."""
    os.environ.setdefault("STOCK_AGENT_USER", "admin")
    pairs, seen = [], set()
    try:
        from modules.issue_tracker import get_portfolio_holdings
        from modules.watchlist import load_watchlist
        raw = [(h["ticker"], h.get("name", h["ticker"])) for h in get_portfolio_holdings()]
        raw += [(it["ticker"], it.get("name", it["ticker"])) for it in load_watchlist()]
    except Exception as e:
        print(f"관심종목 로드 실패 → 빈 목록: {e}")
        return []
    for tk, name in raw:
        sym = to_symbol(tk)
        if sym and sym not in seen:
            seen.add(sym)
            pairs.append((sym, name))
        elif sym is None:
            print(f"  {tk} {name}: 한국 종목 → 이 모델(미국 학습) 대상 아님, 건너뜀")
    return pairs


def load_model(device):
    ckpt_path = MODELS_DIR / "best_resnet18.pth"
    if not ckpt_path.exists():
        sys.exit(f"학습된 모델이 없습니다: {ckpt_path}\n먼저 python ml/train.py 를 실행하세요.")
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)  # 자체 생성 파일
    model = models.resnet18(weights=None)
    model.fc = torch.nn.Sequential(torch.nn.Dropout(DROPOUT),
                                   torch.nn.Linear(model.fc.in_features, 2))  # train.py와 동일 구조
    model.load_state_dict(ckpt["state_dict"])
    model.eval().to(device)
    return model, ckpt


@torch.no_grad()
def predict_one(model, device, code: str) -> tuple[float, bytes, str] | None:
    """(상승확률, png_bytes, 기준일) 반환. 데이터 부족/거래정지면 None."""
    start = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")  # WINDOW(120거래일) 확보용 여유
    df = fdr.DataReader(code, start)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    if len(df) < WINDOW:
        return None
    win = df.iloc[-WINDOW:]
    if (win["Volume"] == 0).any():
        return None
    png = to_png_bytes(win, IMG_SIZE)
    img = Image.open(__import__("io").BytesIO(png)).convert("RGB")
    x = _TF(img).unsqueeze(0).to(device)
    prob_up = F.softmax(model(x).float(), dim=1)[0, 1].item()  # 클래스 1 = up
    return prob_up, png, f"{win.index[-1]:%Y-%m-%d}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*", help="FDR 코드 직접 지정 (예: 005930 000660)")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, ckpt = load_model(device)
    print(f"모델 로드 (val AUC {ckpt.get('val_auc', float('nan')):.4f}) · device {device}")

    if args.tickers:
        targets = [(c, c) for c in args.tickers]
    else:
        targets = load_watchlist_tickers()
    if not targets:
        sys.exit("대상 종목이 없습니다. --tickers 로 지정하거나 관심종목을 추가하세요.")

    signals = []
    for code, name in targets:
        try:
            res = predict_one(model, device, code)
            if res is None:
                print(f"  {code} {name}: 데이터 부족/거래정지 → 건너뜀")
                continue
            prob_up, png, as_of = res
            signals.append({
                "ticker": code, "name": name, "as_of": as_of,
                "prob_up": round(prob_up, 4),
                "thumb": "data:image/png;base64," + base64.b64encode(png).decode(),
            })
            print(f"  {code} {name}: 상승확률 {prob_up:.1%} (기준 {as_of})")
        except Exception as e:
            print(f"  {code} {name}: 실패 → {e}")

    signals.sort(key=lambda s: s["prob_up"], reverse=True)
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "model": "resnet18",
        "val_auc": ckpt.get("val_auc"),
        "horizon_days": HORIZON,
        "window_days": WINDOW,
        "signals": signals,
    }
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LATEST_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    kb = LATEST_JSON.stat().st_size / 1024
    print(f"\n{len(signals)}종목 → {LATEST_JSON} ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
