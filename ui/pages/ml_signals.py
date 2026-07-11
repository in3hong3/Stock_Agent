"""🧠 AI 신호 탭 — CNN 기반 두 가지 신호를 표시 전용으로 보여준다.

  ① 상승확률 (수익률 모델): 최근 6개월 차트 → 1개월 뒤 상승 확률 (약한 우위, 참고용)
  ② 패턴 감지 (패턴 인식 모델): 차트에서 이중바닥 등 패턴을 인식 (val AUC 0.99)
     + 그 패턴의 과거 통계(이벤트 스터디)를 함께 표시

⚠ 이 탭은 **표시 전용**이다. 추론은 로컬(GPU 노트북)에서:
  python ml/predict.py          → ml/signals/latest.json          (①)
  python ml/predict_pattern.py  → ml/signals/patterns_latest.json (②)
커밋 → 서버 pull. 서버(RAM 1GB)에는 torch/mplfinance가 없으므로 절대 import 금지.
"""
import json
from pathlib import Path

import streamlit as st

_SIGNALS_DIR = Path(__file__).resolve().parents[2] / "ml" / "signals"


def _load_json(name: str) -> dict | None:
    try:
        with open(_SIGNALS_DIR / name, "r", encoding="utf-8") as f:
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


def _load_holdings() -> dict:
    """{티커: 보유정보} — 실패하면 빈 dict (신호만 표시)."""
    try:
        from modules.issue_tracker import get_portfolio_holdings
        return {h["ticker"].upper(): h for h in get_portfolio_holdings()}
    except Exception as e:
        st.caption(f"(포트폴리오 로드 실패 — 신호만 표시: {e})")
        return {}


# ══════════════════ ① 상승확률 (수익률 모델) ══════════════════

def _render_row(sig: dict, hor_txt: str, held: dict | None) -> None:
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


def _render_return_model(held_map: dict) -> None:
    data = _load_json("latest.json")
    if not data:
        st.info("아직 생성된 신호가 없습니다 — 로컬에서 `python ml/predict.py` 실행 후 배포하세요.")
        return

    win_txt = _approx_months(data.get("window_days", 120))
    hor_txt = _approx_months(data.get("horizon_days", 20))
    st.caption(
        f"과거 {win_txt} 캔들차트를 CNN이 보고 매긴 **{hor_txt} 뒤 상승 확률**입니다. "
        "약한 우위(AUC 0.54) 모델이라 절대값보다 **종목 간 상대 순위**로만 참고하세요."
    )

    signals = {s["ticker"].upper(): s for s in data.get("signals", [])}
    matched = [(t, h) for t, h in held_map.items() if t in signals]
    missing = [t for t in held_map if t not in signals]

    auc = data.get("val_auc")
    auc_txt = f"{auc:.3f}" if isinstance(auc, (int, float)) else "N/A"
    c1, c2, c3 = st.columns(3)
    c1.metric("생성 시각", data.get("generated_at", "-"))
    c2.metric("검증 AUC", auc_txt, help="0.5=무의미, 0.52~0.55면 유의미한 신호")
    c3.metric("보유 종목 신호", f"{len(matched)} / {len(held_map)}" if held_map else f"{len(signals)}개")

    ref_missing = [t for t in missing if not _is_korean(t)]
    if ref_missing:
        st.info(f"🔄 신호 없는 보유 종목: **{', '.join(ref_missing)}** — 로컬에서 "
                "`python ml/predict.py` 재실행 후 배포하면 채워집니다.")
    kr_missing = [t for t in missing if _is_korean(t)]
    if kr_missing:
        st.caption(f"ℹ️ {', '.join(kr_missing)}는 한국 종목 — 미국주 전용 모델이라 대상 아님.")

    st.divider()
    rows = matched if held_map else [(t, None) for t in signals]
    rows.sort(key=lambda x: signals[x[0]].get("prob_up", 0.0), reverse=True)
    for ticker, held in rows:
        _render_row(signals[ticker], hor_txt, held)

    extras = [t for t in signals if t not in held_map]
    if held_map and extras:
        with st.expander(f"관심종목·기타 신호 {len(extras)}개 (미보유)"):
            for t in sorted(extras, key=lambda t: signals[t].get("prob_up", 0.0), reverse=True):
                _render_row(signals[t], hor_txt, None)


# ══════════════════ ② 패턴 감지 (패턴 인식 모델) ══════════════════

_DETECT_THRESHOLD = 0.5  # 이 이상이면 '패턴 감지'로 취급


def _render_pattern_model(held_map: dict) -> None:
    data = _load_json("patterns_latest.json")
    if not data:
        st.info("아직 패턴 스캔 결과가 없습니다 — 로컬에서 `python ml/predict_pattern.py` 실행 후 배포하세요.")
        return

    stats = data.get("event_stats", {})
    pattern_kr = stats.get("pattern_kr", "이중바닥")
    scans = data.get("scans", [])
    detected = [s for s in scans if s.get("prob_pattern", 0) >= _DETECT_THRESHOLD]

    st.caption(
        f"패턴 인식 CNN(검증 AUC {data.get('val_auc', 0):.3f})이 각 보유 종목의 최근 "
        f"{_approx_months(data.get('window_days', 120))} 차트에서 **{pattern_kr}** 모양을 찾습니다. "
        "매매 신호가 아니라 '패턴 발견 + 그 패턴의 과거 통계' 정보입니다."
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("스캔 시각", data.get("generated_at", "-"))
    c2.metric("스캔 종목", f"{len(scans)}개")
    c3.metric("패턴 감지", f"{len(detected)}개")

    st.divider()

    if not detected:
        st.success(f"✅ 현재 스캔된 {len(scans)}개 종목 중 {pattern_kr} 패턴이 감지된 종목은 없습니다.")
    else:
        for s in detected:
            prob = s.get("prob_pattern", 0.0)
            col_img, col_info = st.columns([1, 2])
            with col_img:
                if s.get("thumb"):
                    st.image(s["thumb"], use_container_width=True)
            with col_info:
                held = held_map.get(s["ticker"].upper())
                name = (held or {}).get("name") or s.get("name", s["ticker"])
                st.markdown(f"**{name}** `{s['ticker']}`")
                if held:
                    st.caption(f"📦 보유 {held.get('quantity', 0):g}주")
                rule = " · ✓ 규칙 탐지기도 최근 확정" if s.get("rule_confirmed_recent") else ""
                st.progress(prob, text=f"{pattern_kr} 확률 {prob:.1%}{rule}")
                st.caption(f"기준일 {s.get('as_of', '-')}")
                if stats.get("summary"):
                    st.warning(f"📊 과거 통계 ({stats.get('n_events', '-')}건): {stats['summary']}")
            st.divider()

    # 전체 종목 확률 (감지 안 된 것 포함) — 컴팩트 목록
    with st.expander("전체 종목 스캔 확률 보기"):
        for s in scans:
            prob = s.get("prob_pattern", 0.0)
            st.progress(min(max(prob, 0.0), 1.0),
                        text=f"{s['ticker']} · {s.get('name', '')} — {prob:.1%}")

    if stats.get("summary"):
        with st.expander(f"'{pattern_kr}' 패턴의 과거 통계 (이벤트 스터디)"):
            st.markdown(
                f"- **표본**: S&P500 496종목, 2020~2026, 이벤트 {stats.get('n_events', '-')}건\n"
                f"- **결과**: {stats['summary']}\n"
                "- **방법**: 승률을 기저율(아무 날) 대비로 보고, 전/후반 교차검증 통과한 결론만 기재"
            )


# ══════════════════ ③ 데일리 판정 (서버 cron이 매일 생성) ══════════════════

_SCAN_JSON = Path(__file__).resolve().parents[2] / "data" / "market_scan.json"


def _render_daily_verdict() -> None:
    try:
        with open(_SCAN_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        st.info("아직 판정이 없습니다 — 매일 미국장 마감 후(KST 오전) 자동 생성됩니다.")
        return

    st.caption(
        f"규칙 기반 패턴 탐지 + 이벤트 스터디 통계(S&P500 496종목, 2020~2026)로 만든 "
        f"자동 판정입니다. 투자 자문이 아니라 데이터 참고 자료입니다. · 생성 {data.get('generated_at', '-')}"
    )

    # 판정문
    for line in data.get("verdict", []):
        if line.startswith("🔴"):
            st.error(line)
        elif line.startswith("🟡"):
            st.warning(line)
        elif line.startswith("🟢"):
            st.success(line)
        else:
            st.info(line)

    st.divider()

    def _table(rows: list, title: str):
        if not rows:
            return
        st.markdown(f"**{title}**")
        disp = [{
            "종목": r["ticker"], "이름": r.get("name", ""), "현재가": f"{r['price']:,}",
            "10일%": r["ret10"], "21일%": r["ret21"], "고점比%": r["off_high"],
            "200일선": "위" if r["above_ma200"] else "⚠ 아래",
            "50일선": "위" if r["above_ma50"] else "아래",
            "패턴": " ".join(r.get("flags", [])) or "-",
        } for r in rows]
        st.dataframe(disp, use_container_width=True, hide_index=True)

    _table(data.get("market", []), "📊 지수")
    _table(data.get("holdings", []), "📦 보유 종목")


# ══════════════════ 탭 진입점 ══════════════════

def render_tab_ml_signals() -> None:
    st.subheader("🧠 AI 신호 (실험적)")
    held_map = _load_holdings()

    sub_daily, sub_return, sub_pattern = st.tabs(
        ["📋 데일리 판정", "📈 상승확률 (수익률 모델)", "🔍 패턴 감지 (이중바닥)"])
    with sub_daily:
        _render_daily_verdict()
    with sub_return:
        _render_return_model(held_map)
    with sub_pattern:
        _render_pattern_model(held_map)

    with st.expander("이 신호들은 어떻게 만들어지나요?"):
        st.markdown(
            "- **상승확률 모델**: 과거 6개월 차트 이미지 → 1개월 뒤 +5% 상승 확률. "
            "S&P500 8.6만 장으로 학습, 검증 AUC 0.536 = **약한 우위** → 상대 순위로만 참고.\n"
            "- **패턴 인식 모델**: 규칙 탐지기가 자동 라벨링한 2.2만 장으로 학습, 검증 AUC 0.988. "
            "패턴을 '찾는' 것이고, 그 패턴이 좋은지 나쁜지는 **이벤트 스터디 통계**가 말해줍니다.\n"
            "- 두 모델 다 로컬 GPU에서 추론해 결과 JSON만 서버로 배포 — 서버에서는 표시만 합니다."
        )
