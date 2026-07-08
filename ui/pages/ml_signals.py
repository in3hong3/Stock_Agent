"""🧠 AI 신호 탭 — 차트 이미지 CNN이 매긴 중기(≈1개월) 상승 확률.

⚠ 이 탭은 **표시 전용**이다. 모델 추론은 로컬(GPU 노트북)에서 `ml/predict.py`로
돌려 ml/signals/latest.json 을 만들고 커밋 → 서버가 pull 해서 이 파일을 읽는다.
서버(RAM 1GB)에는 torch/mplfinance가 없으므로 여기서 절대 import 하지 않는다.

신호는 **현재 포트폴리오와 대조**해서 보여준다 — 보유 종목엔 수량을 붙이고,
신호 없는 보유종목(추론 이후 새로 편입)과 이미 매도한 종목을 구분한다.
"""
import json
from pathlib import Path

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


def _is_korean(ticker: str) -> bool:
    t = ticker.upper()
    return t.endswith((".KS", ".KQ")) or (t.isdigit() and len(t) == 6)


def _render_row(sig: dict, hor_txt: str, held: dict | None) -> None:
    """신호 1건을 (보유 정보와 함께) 렌더."""
    prob = sig.get("prob_up", 0.0)
    col_img, col_info = st.columns([1, 2])
    with col_img:
        if sig.get("thumb"):
            st.image(sig["thumb"], use_container_width=True)
    with col_info:
        name = (held or {}).get("name") or sig.get("name", sig["ticker"])
        st.markdown(f"**{name}** `{sig['ticker']}`")
        if held:
            qty = held.get("quantity", 0)
            cur = held.get("current_price", 0) or 0
            price_txt = f" · 현재가 {cur:,.2f}" if cur > 0 else ""
            st.caption(f"📦 보유 {qty:g}주{price_txt}")
        st.progress(min(max(prob, 0.0), 1.0), text=f"상승 확률 {prob:.1%}")
        st.caption(f"기준일 {sig.get('as_of', '-')} · {hor_txt} 뒤 전망")
    st.divider()


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
            "2. `python ml/predict.py` — 보유/관심종목 추론 → `ml/signals/latest.json` 커밋·배포"
        )
        return

    win_txt = _approx_months(data.get("window_days", 120))
    hor_txt = _approx_months(data.get("horizon_days", 20))
    st.caption(
        f"과거 {win_txt} 캔들차트 이미지를 CNN(ResNet18)이 보고 매긴 "
        f"**{hor_txt} 뒤 상승 확률**입니다. 하루하루가 아니라 몇 주~몇 달의 큰 흐름을 봅니다. "
        "규칙 기반 신호가 아니라 미래 수익률로 학습한 별도 모델이며, 보조 참고용입니다."
    )

    # 신호를 티커(대문자)로 색인
    signals = {s["ticker"].upper(): s for s in data.get("signals", [])}

    # 현재 포트폴리오와 대조 (서버에 이미 있는 함수 — 무거운 의존성 없음)
    try:
        from modules.issue_tracker import get_portfolio_holdings
        holdings = get_portfolio_holdings()
    except Exception as e:
        holdings = []
        st.caption(f"(포트폴리오 로드 실패 — 신호만 표시: {e})")

    held_map = {h["ticker"].upper(): h for h in holdings}
    matched = [(t, h) for t, h in held_map.items() if t in signals]          # 보유 + 신호 있음
    missing = [(t, h) for t, h in held_map.items() if t not in signals]      # 보유인데 신호 없음
    extras = [t for t in signals if t not in held_map]                       # 신호 있는데 미보유

    auc = data.get("val_auc")
    auc_txt = f"{auc:.3f}" if isinstance(auc, (int, float)) else "N/A"
    c1, c2, c3 = st.columns(3)
    c1.metric("생성 시각", data.get("generated_at", "-"))
    c2.metric("검증 AUC", auc_txt, help="0.5=무의미, 0.52~0.55면 유의미한 신호")
    c3.metric("보유 종목 신호", f"{len(matched)} / {len(held_map)}",
              help="현재 보유 종목 중 신호가 있는 종목 수")

    if isinstance(auc, (int, float)) and auc < 0.52:
        st.warning(
            f"⚠️ 이 모델의 검증 AUC가 {auc_txt}로 낮습니다 — 아직 신뢰할 신호가 아닙니다. "
            "학습 데이터/기간을 늘려 AUC를 올린 뒤 참고하세요."
        )

    # 보유 종목 중 신호 없는 게 있으면 안내 (추론 이후 새로 편입 등)
    kr_missing = [t for t, _ in missing if _is_korean(t)]
    ref_missing = [t for t, _ in missing if not _is_korean(t)]
    if ref_missing:
        st.info(
            f"🔄 보유 중이지만 신호가 없는 종목: **{', '.join(ref_missing)}** "
            "— 최근 편입된 종목입니다. 로컬에서 `python ml/predict.py` 재실행 후 배포하면 채워집니다."
        )
    if kr_missing:
        st.caption(f"ℹ️ {', '.join(kr_missing)}는 한국 종목 — 이 모델은 미국주(S&P500) 전용이라 대상이 아닙니다.")

    if not held_map:
        st.caption("포트폴리오가 비어 있어 전체 신호를 표시합니다.")

    st.divider()

    # 1) 보유 종목 신호 — 상승확률 높은 순
    rows = matched if held_map else [(t, None) for t in signals]
    rows.sort(key=lambda x: signals[x[0]].get("prob_up", 0.0), reverse=True)
    if held_map:
        st.markdown("#### 📌 내 보유 종목")
    for ticker, held in rows:
        _render_row(signals[ticker], hor_txt, held)

    # 2) 보유 안 하는데 신호 있는 종목 (관심종목 등) — 접어서 표시
    if held_map and extras:
        with st.expander(f"관심종목·기타 신호 {len(extras)}개 (미보유)"):
            for ticker in sorted(extras, key=lambda t: signals[t].get("prob_up", 0.0), reverse=True):
                _render_row(signals[ticker], hor_txt, None)

    with st.expander("이 신호는 어떻게 만들어지나요?"):
        st.markdown(
            f"- **입력**: 종목의 최근 {win_txt}({data.get('window_days', 120)}거래일) 캔들+거래량 차트 이미지 (미래 데이터 없음)\n"
            f"- **출력**: {hor_txt}({data.get('horizon_days', 20)}거래일) 뒤 의미 있는 상승(+5% 이상) 확률\n"
            "- **학습**: S&P500 종목의 과거 차트로, 규칙이 아닌 실제 미래 수익률을 맞히도록 훈련\n"
            "- **주의**: 확률값은 클래스 보정 때문에 부풀려져 있으니 절대값보다 **종목 간 상대 순위**로 보세요. "
            "AUC가 0.5에 가까우면 예측력이 약하니 다른 근거와 함께 보조로만 씁니다."
        )
