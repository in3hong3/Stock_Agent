"""1단계: GPU가 PyTorch에서 잡히는지 확인."""

import sys

sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대응

import torch

print(f"PyTorch  : {torch.__version__}")
print(f"CUDA 사용 가능: {torch.cuda.is_available()}")

if torch.cuda.is_available():
    dev = torch.cuda.get_device_properties(0)
    print(f"GPU      : {dev.name}")
    print(f"VRAM     : {dev.total_memory / 1024**3:.1f} GB")
    x = torch.rand(1024, 1024, device="cuda")
    y = x @ x
    torch.cuda.synchronize()
    print(f"행렬곱 테스트 OK — 결과 shape {tuple(y.shape)}, device {y.device}")
else:
    print("GPU가 안 잡힘 — CUDA 빌드 설치 여부를 확인하세요:")
    print("  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128")
