"""🧠 AI 신호 탭 — 차트 이미지 CNN이 매긴 '5일 뒤 상승 확률'.

⚠ 이 탭은 **표시 전용**이다. 모델 추론은 로컬(GPU 노트북)에서 `ml/predict.py`로
돌려 ml/signals/latest.json 을 만들고 커밋 → 서버가 pull 해서 이 파일을 읽는다.
서버(RAM 1GB)에는 torch/mplfinance가 없으므로 여기서 절대 import 하지 않는다.
"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

_SIGNALS_JSON = Path(__file__).resolve().parents[2] / "ml" / "signals" / "latest.json"


def _load_signals() -> dict | None:
    try:
        with open(_SIGNALS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _approx_months(trading_days: int) -> str:
    """거래일 수 → 사람이 읽는 근사 기간 (예: 120 → '약 6개월')."""
    months = round(trading_days / 21)  # 월 ≈ 21거래일
    return f"약 {months}개월" if months >= 1 else f"{trading_days}거래일"


def render_tab_ml_signals() -> None:
    st.subheader("🧠 AI 패턴 신호 (실험적)")

    data = _load_signals()
    if not data:
        st.caption(
            "과거 차트 이미지를 CNN(ResNet18)이 보고 매긴 **중기 상승 확률**입니다. "
            "규칙 기반 신호가 아니라 미래 수익률로 학습한 별도 모델이며, 보조 참고용입니다."
        )
        st.info(
            "아직 생성된 신호가 없습니다.\n\n"
            "로컬(GPU 노트북)에서 아래를 실행하면 이 탭에 채워집니다:\n"
            "1. `python ml/train.py` — 모델 학습\n"
            "2. `python ml/predict.py` — 관심종목 추론 → `ml/signals/latest.json` 커밋·배포"
        )
        return

    win_txt = _approx_months(data.get("window_days", 120))
    hor_txt = _approx_months(data.get("horizon_days", 20))
    st.caption(
        f"과거 {win_txt} 캔들차트 이미지를 CNN(ResNet18)이 보고 매긴 "
        f"**{hor_txt} 뒤 상승 확률**입니다. 하루하루가 아니라 몇 주~몇 달의 큰 흐름을 봅니다. "
        "규칙 기반 신호가 아니라 미래 수익률로 학습한 별도 모델이며, 보조 참고용입니다."
    )

    signals = data.get("signals", [])
    auc = data.get("val_auc")
    auc_txt = f"{auc:.3f}" if isinstance(auc, (int, float)) else "N/A"
    c1, c2, c3 = st.columns(3)
    c1.metric("생성 시각", data.get("generated_at", "-"))
    c2.metric("검증 AUC", auc_txt, help="0.5=무의미, 0.52~0.55면 유의미한 신호")
    c3.metric("대상 종목", f"{len(signals)}개")

    if isinstance(auc, (int, float)) and auc < 0.52:
        st.warning(
            f"⚠️ 이 모델의 검증 AUC가 {auc_txt}로 낮습니다 — 아직 신뢰할 신호가 아닙니다. "
            "학습 데이터/기간을 늘려 AUC를 올린 뒤 참고하세요."
        )

    if not signals:
        st.write("표시할 종목이 없습니다.")
        return

    st.divider()
    for s in signals:
        prob = s.get("prob_up", 0.0)
        col_img, col_info = st.columns([1, 2])
        with col_img:
            if s.get("thumb"):
                st.image(s["thumb"], use_container_width=True)
        with col_info:
            st.markdown(f"**{s.get('name', s['ticker'])}** `{s['ticker']}`")
            st.progress(min(max(prob, 0.0), 1.0),
                        text=f"상승 확률 {prob:.1%}")
            st.caption(f"기준일 {s.get('as_of', '-')} · {hor_txt} 뒤 전망")
        st.divider()

    with st.expander("이 신호는 어떻게 만들어지나요?"):
        st.markdown(
            f"- **입력**: 종목의 최근 {win_txt}({data.get('window_days', 120)}거래일) 캔들+거래량 차트 이미지 (미래 데이터 없음)\n"
            f"- **출력**: {hor_txt}({data.get('horizon_days', 20)}거래일) 뒤 의미 있는 상승(+5% 이상) 확률\n"
            "- **학습**: S&P500 종목의 과거 차트로, 규칙이 아닌 실제 미래 수익률을 맞히도록 훈련\n"
            "- **주의**: 시장 예측은 본질적으로 어렵습니다. AUC가 0.5에 가까우면 동전던지기와 같으니 "
            "확률값을 맹신하지 말고 다른 근거와 함께 보세요."
        )
