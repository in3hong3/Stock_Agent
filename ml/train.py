"""5단계: ResNet18 전이학습 — 차트 이미지 → 5일 뒤 상승 확률.

- ImageFolder 클래스 순서는 알파벳순이라 down=0, up=1. 모델 출력 softmax의
  1번 클래스 확률이 곧 '상승 확률'이다.
- 지표는 Accuracy보다 AUC를 본다. 이런 문제는 val AUC 0.52~0.55만 나와도
  신호로서 의미가 있고, 0.5 근처면 못 배운 것.
- val AUC 기준 Early Stopping + 최고 성능 가중치 저장.

사용:
    python ml/train.py
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대응

from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (BATCH_SIZE, DATASET_DIR, EARLY_STOP_PATIENCE, IMG_SIZE,
                    LR, MAX_EPOCHS, MODELS_DIR, NUM_WORKERS)


def roc_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """rank 기반 AUC (외부 라이브러리 없이)."""
    ranks = pd.Series(y_score).rank().to_numpy()
    n_pos = int(y_true.sum())
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    return (ranks[y_true == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


@torch.no_grad()
def evaluate(model, loader, criterion, device):
    model.eval()
    losses, all_labels, all_probs = [], [], []
    for x, y in loader:
        x, y = x.to(device), y.to(device)
        with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
            out = model(x)
            losses.append(criterion(out, y).item())
        probs = torch.softmax(out.float(), dim=1)[:, 1]  # up(=1) 확률
        all_labels.append(y.cpu().numpy())
        all_probs.append(probs.cpu().numpy())
    labels = np.concatenate(all_labels)
    probs = np.concatenate(all_probs)
    acc = ((probs > 0.5).astype(int) == labels).mean()
    return float(np.mean(losses)), float(acc), roc_auc(labels, probs)


def main() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}"
          + (f" ({torch.cuda.get_device_name(0)})" if device.type == "cuda" else " ⚠ GPU 미인식"))

    tf = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    train_ds = datasets.ImageFolder(DATASET_DIR / "train", transform=tf)
    val_ds = datasets.ImageFolder(DATASET_DIR / "val", transform=tf)
    assert train_ds.class_to_idx == {"down": 0, "up": 1}, train_ds.class_to_idx

    counts = np.bincount(train_ds.targets, minlength=2)
    print(f"train {len(train_ds)}개 (down {counts[0]} / up {counts[1]}) · val {len(val_ds)}개")

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True,
                              num_workers=NUM_WORKERS, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False,
                            num_workers=NUM_WORKERS, pin_memory=True)

    model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
    model.fc = nn.Linear(model.fc.in_features, 2)
    model.to(device)

    # 클래스 불균형 보정
    weights = torch.tensor(counts.sum() / (2.0 * counts), dtype=torch.float32, device=device)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    best_path = MODELS_DIR / "best_resnet18.pth"
    best_auc, patience = -1.0, 0

    for epoch in range(1, MAX_EPOCHS + 1):
        model.train()
        losses = []
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                loss = criterion(model(x), y)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            losses.append(loss.item())

        val_loss, val_acc, val_auc = evaluate(model, val_loader, criterion, device)
        print(f"epoch {epoch:2d} | train loss {np.mean(losses):.4f} | "
              f"val loss {val_loss:.4f} · acc {val_acc:.3f} · AUC {val_auc:.4f}")

        if val_auc > best_auc:
            best_auc, patience = val_auc, 0
            torch.save({"state_dict": model.state_dict(),
                        "class_to_idx": train_ds.class_to_idx,
                        "img_size": IMG_SIZE, "val_auc": float(best_auc)}, best_path)
            print(f"         └ best 갱신 → {best_path.name} 저장")
        else:
            patience += 1
            if patience >= EARLY_STOP_PATIENCE:
                print(f"Early stopping (AUC {EARLY_STOP_PATIENCE}에폭 연속 미개선)")
                break

    print(f"\n최고 val AUC {best_auc:.4f} · 모델: {best_path}")


if __name__ == "__main__":
    main()
