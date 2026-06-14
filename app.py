"""
Stock Agent RAG 챗봇 - Streamlit 앱
Multi-Agent 시스템 with Fear & Greed Index 기반 히트맵 테마
"""
import streamlit as st
import os
from pathlib import Path

# Load mobile responsive CSS
mobile_css_path = Path(__file__).parent / "ui" / "mobile.css"
if mobile_css_path.exists():
    with open(mobile_css_path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

import os
import pandas as pd
import datetime
import traceback

from config.settings import PAGE_TITLE, PAGE_ICON, AGENT_REGISTRY
from ui.theme import get_cached_fear_greed_index, get_heatmap_color, apply_theme, get_point_color
from ui.components import (
    render_agent_selector, render_market_summary, render_chat_sources,
    render_ticker_tape, render_fear_greed_gauge, render_login_page
)
from agents.rag_agent import RAGAgent
from agents.quant_agent import QuantAnalyst
from agents.technical_agent import TechnicalAgent
from agents.news_agent import NewsAgent
from agents.router import AgenticRouter
from utils.sector_classifier import SectorClassifier
from utils.portfolio_visualizer import PortfolioVisualizer
from utils.portfolio_utils import calc_portfolio_metrics


# ──────────────────────────────────────────────
# 초기화
# ──────────────────────────────────────────────
def initialize_agents():
    if "agents" not in st.session_state:
        st.session_state.agents = {}
        for agent_id, agent_info in AGENT_REGISTRY.items():
            if not agent_info.get("enabled", True):
                continue
            agent_type = agent_info.get("type", "rag")
            if agent_type == "rag":
                st.session_state.agents[agent_id] = RAGAgent(
                    agent_id=agent_id,
                    name=agent_info["name"],
                    description=agent_info["description"],
                    channel_id=agent_info.get("channel_id"),
                )
            elif agent_type == "technical":
                st.session_state.agents[agent_id] = TechnicalAgent(
                    agent_id=agent_id,
                    name=agent_info["name"],
                    description=agent_info["description"],
                )
            elif agent_type == "news":
                st.session_state.agents[agent_id] = NewsAgent(
                    agent_id=agent_id,
                    name=agent_info["name"],
                    description=agent_info["description"],
                )

    if "agentic_router" not in st.session_state:
        with st.spinner("🔀 Agentic Router 초기화 중..."):
            st.session_state.agentic_router = AgenticRouter()


# ──────────────────────────────────────────────
# 사이드 패널
# ──────────────────────────────────────────────
def render_mobile_nav(selected_tab: str = None):
    """Simple mobile top navigation bar. Returns the selected tab name."""
    tabs = ["트래커", "데일리 신문", "포트폴리오", "AI 평가", "매매일지"]
    icons = ["📌", "📰", "💼", "🤖", "📒"]
    col1, col2 = st.columns([1, 8])
    with col1:
        st.markdown("<div class='mobile-nav'>", unsafe_allow_html=True)
    with col2:
        selected = st.selectbox("", options=[f"{icons[i]} {tabs[i]}" for i in range(len(tabs))], index=0, key="mobile_tab_selector")
    st.markdown("</div>", unsafe_allow_html=True)
    return selected.split(' ', 1)[1]  # return tab name without icon

def render_side_panel(fg_index, fg_status, status_text, point_color):
    # 현재 사용자 + 로그아웃
    uid = st.session_state.get("user_id", "?")
    uc1, uc2 = st.columns([3, 1])
    uc1.markdown(f"👤 **{uid}**님 로그인 중")
    if uc2.button("로그아웃", key="logout_btn", use_container_width=True):
        for k in ("authenticated", "user_id", "_migrated", "df_portfolio",
                  "portfolio_data", "tracker_briefing", "portfolio_eval"):
            st.session_state.pop(k, None)
        st.rerun()
    st.divider()

    st.subheader("🌋 시장 심리 (Fear & Greed)")
    render_fear_greed_gauge(fg_index)
    if fg_index is not None:
        st.info(f"**현재 상태**: {fg_status} ({status_text})")
    st.divider()

    # ── 📅 이벤트 캘린더 ──
    from modules.event_calendar import (
        get_all_events, build_calendar_html, get_upcoming_events,
        add_custom_event, load_custom_events, remove_custom_event,
    )
    from modules.issue_tracker import get_portfolio_holdings

    st.subheader("📅 주요 일정")

    @st.cache_data(ttl=21600)  # 6시간 (실적일 조회가 느려서 길게)
    def cached_events(ticker_tuple, custom_ver):
        return get_all_events(list(ticker_tuple))

    holdings = get_portfolio_holdings()
    tickers = tuple(h["ticker"] for h in holdings)
    custom_ver = len(load_custom_events())  # 커스텀 이벤트 변경 시 캐시 무효화

    with st.spinner("일정 로딩 중..."):
        events = cached_events(tickers, custom_ver)

    # 미니 달력 (이번 달)
    today = datetime.date.today()
    cal_month = st.session_state.get("cal_month", today.month)
    cal_year = st.session_state.get("cal_year", today.year)

    nav1, nav2, nav3 = st.columns([1, 3, 1])
    with nav1:
        if st.button("◀", key="cal_prev", use_container_width=True):
            cal_month -= 1
            if cal_month == 0:
                cal_month, cal_year = 12, cal_year - 1
            st.session_state.cal_month, st.session_state.cal_year = cal_month, cal_year
            st.rerun()
    with nav3:
        if st.button("▶", key="cal_next", use_container_width=True):
            cal_month += 1
            if cal_month == 13:
                cal_month, cal_year = 1, cal_year + 1
            st.session_state.cal_month, st.session_state.cal_year = cal_month, cal_year
            st.rerun()

    st.markdown(build_calendar_html(cal_year, cal_month, events, accent=point_color), unsafe_allow_html=True)
    st.caption("점 표시된 날짜에 마우스를 올리면 일정이 보입니다.")

    # 다가오는 일정 (3주)
    upcoming = get_upcoming_events(events, days=21)
    if upcoming:
        st.markdown("**🔜 다가오는 일정**")
        for ev in upcoming[:8]:
            d_day = f"D-{ev['d_day']}" if ev["d_day"] > 0 else "오늘"
            st.markdown(
                f"<div style='font-size:0.85rem; padding:3px 0;'>"
                f"<span style='color:{point_color}; font-weight:700;'>{d_day}</span> "
                f"<span style='color:#94A3B8;'>{ev['date'].strftime('%m/%d')}</span> "
                f"{ev['title']}</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("3주 이내 일정이 없습니다.")

    # 커스텀 이벤트 추가/관리
    with st.expander("📝 일정 직접 추가"):
        with st.form("add_event_form", clear_on_submit=True):
            ev_date = st.date_input("날짜", value=today, key="ev_date")
            ev_title = st.text_input("일정 내용", placeholder="예: 테슬라 로보택시 발표")
            if st.form_submit_button("➕ 추가", use_container_width=True):
                if ev_title.strip():
                    add_custom_event(ev_date.strftime("%Y-%m-%d"), ev_title.strip())
                    st.cache_data.clear()
                    st.rerun()

        customs = load_custom_events()
        if customs:
            st.markdown("**등록한 일정:**")
            for i, ev in enumerate(customs):
                ec1, ec2 = st.columns([5, 1])
                ec1.markdown(f"<span style='font-size:0.85rem;'>{ev['date']} — {ev['title']}</span>", unsafe_allow_html=True)
                if ec2.button("🗑️", key=f"del_ev_{i}"):
                    remove_custom_event(i)
                    st.cache_data.clear()
                    st.rerun()

    st.divider()

    if st.button("🔄 대화 초기화", icon=":material/refresh:", use_container_width=True):
        for key in ("rag_messages", "quant_messages", "tech_messages",
                    "comprehensive_messages", "personalized_rag_messages"):
            st.session_state[key] = []
        st.success("모든 탭 대화가 초기화됐습니다.")
        st.rerun()


# ──────────────────────────────────────────────
# TAB: 내 종목 트래커
# ──────────────────────────────────────────────
@st.cache_data(ttl=300)
def cached_candle_chart(ticker: str, period: str = "6mo"):
    """캔들차트 공용 캐시 (기술분석관과 동일 차트를 다른 탭에서 재사용)"""
    from utils.chart_builder import build_candlestick_chart
    return build_candlestick_chart(ticker, period)


def render_tab_tracker():
    from modules.issue_tracker import (
        get_portfolio_holdings, get_snapshot,
        fetch_ticker_news, summarize_all_issues,
    )

    st.header("📌 내 종목 트래커")
    st.caption("내 포트폴리오(data/portfolio.csv) 종목을 자동 추적합니다. 종목 추가/수정은 '💼 내 포트폴리오' 탭에서 하세요.")

    tracked = get_portfolio_holdings()
    if not tracked:
        st.info("📂 포트폴리오가 비어 있습니다. '💼 내 포트폴리오' 탭에서 종목을 추가하세요.")
        return

    tickers = [it["ticker"] for it in tracked]

    # ── 가격/지표 스냅샷 (내 보유 종목) ──
    st.subheader(f"📊 실시간 현황 — 보유 {len(tracked)}종목")

    @st.cache_data(ttl=300)
    def cached_snapshot(holdings_key):
        # holdings_key는 캐시 무효화용 (ticker, qty, avg) 튜플
        return get_snapshot(get_portfolio_holdings())

    holdings_key = tuple((h["ticker"], h["quantity"], h["avg_price"]) for h in tracked)
    with st.spinner("시세 조회 중..."):
        snap_df = cached_snapshot(holdings_key)

    # ── ✅ 오늘 할 일 + 🎯 매매 시그널 (규칙 기반, LLM 호출 없음) ──
    signal_result = None
    try:
        from modules.daily_actions import build_actions
        from modules.portfolio_advisor import PERSONAS
        from modules.trade_signal import generate_signals

        # AI 평가에서 선택한 성향 재사용 (선택 전이면 공격적)
        stance = "aggressive"
        saved_label = st.session_state.get("advisor_stance", "")
        for k, v in PERSONAS.items():
            if saved_label.startswith(v["label"]):
                stance = k
                break

        @st.cache_data(ttl=300)
        def cached_signals(h_key, st_key):
            return generate_signals(get_portfolio_holdings(), st_key)

        with st.spinner("매매 시그널 계산 중..."):
            signal_result = cached_signals(holdings_key, stance)

        # 예측 기록 + 만기 도래분 자동 채점 (정확도 추적용, 하루 1회만)
        try:
            from modules.signal_tracker import record_predictions, grade_predictions
            _today_key = f"{datetime.date.today()}|{stance}"
            if st.session_state.get("_pred_recorded") != _today_key:
                record_predictions(signal_result["signals"], stance)
                grade_predictions(horizon_days=10)
                st.session_state["_pred_recorded"] = _today_key
        except Exception as e:
            print(f"예측 기록 실패: {e}")

        actions = build_actions(snap_df, tickers, stance, signals=signal_result["signals"])
        if actions:
            stance_badge = PERSONAS[stance]["label"]
            st.markdown(
                f"<div style='background: linear-gradient(160deg, #1A2340, #16181F); "
                f"border: 1px solid #3b82f655; border-radius: 14px; padding: 16px 20px; margin-bottom: 12px;'>"
                f"<div style='font-weight: 700; font-size: 1.05rem; margin-bottom: 10px;'>"
                f"✅ 오늘 할 일 <span style='font-size: 0.75rem; color: #94A3B8;'>({stance_badge} 기준 · "
                f"{datetime.date.today().strftime('%m/%d')})</span></div>"
                + "".join(
                    f"<div style='padding: 4px 0; font-size: 0.92rem; line-height: 1.6;'>"
                    f"{a['icon']} {a['text'].replace('**', '<b>', 1).replace('**', '</b>', 1)}</div>"
                    for a in actions[:10]
                )
                + "</div>",
                unsafe_allow_html=True,
            )
    except Exception as e:
        print(f"오늘 할 일 생성 실패: {e}")

    # ── 🎯 상세 매매 시그널 ──
    if signal_result:
        regime = signal_result["regime"]
        with st.expander(f"🎯 상세 매매 시그널 — 시장 국면: {regime['label']}", expanded=False):
            st.caption(" · ".join(regime["detail"]) + f" → 전체 점수 보정 {regime['score_modifier']:+d}점")

            for s in signal_result["signals"]:
                profit_str = f"{s['profit_rate']:+.1f}%" if s.get("profit_rate") is not None else "—"
                st.markdown(
                    f"#### {s['icon']} {s['ticker']} — **{s['action']}**  "
                    f"<span style='font-size:0.85rem; color:#00FFA3;'>{s.get('setup', '')}</span>",
                    unsafe_allow_html=True,
                )
                # 밸류에이션 뱃지
                val = s.get("valuation", {})
                vmap = {"저평가": "#00FFA3", "적정": "#94A3B8", "고평가": "#FF4B4B", "평가불가": "#64748B"}
                vcolor = vmap.get(val.get("verdict", "평가불가"), "#64748B")
                st.markdown(
                    f"<span style='font-size:0.85rem;'>🏷️ 밸류에이션: "
                    f"<b style='color:{vcolor};'>{val.get('verdict','?')}</b> "
                    f"<span style='color:#64748B; font-size:0.78rem;'>{val.get('note','')}</span></span>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<span style='font-size:0.8rem; color:#94A3B8;'>"
                    f"현재가 {s['price']:,.2f} · 수익률 {profit_str} · 점수 {s['adj_score']:+.0f} · "
                    f"주봉 {s.get('wk_trend','?')}추세 · {s.get('trend_regime','?')}(ADX {s.get('adx','?')}) · "
                    f"RSI {s.get('rsi','?')} · 변동성(ATR) {s.get('atr_pct','?')}%</span>",
                    unsafe_allow_html=True,
                )

                sg1, sg2 = st.columns([3, 2])
                with sg1:
                    st.markdown("**📋 판단 근거:**")
                    for pts, reason in s["reasons"]:
                        st.markdown(f"- {pts} {reason}")
                    for ex in s.get("extra", []):
                        st.markdown(f"- {ex}")
                with sg2:
                    st.markdown("**🎯 매매 플랜:**")
                    if s.get("entry"):
                        # 진입/손절/목표를 표로 명확하게
                        st.markdown(
                            f"<div style='font-size:0.9rem; line-height:1.9;'>"
                            f"🟢 <b>진입</b>: {s['entry']:,.2f}<br>"
                            f"🛑 <b>손절</b>: {s['stop']:,.2f} "
                            f"<span style='color:#FF4B4B;'>({(s['stop']/s['entry']-1)*100:+.1f}%)</span><br>"
                            f"🎯 <b>목표</b>: {s['target']:,.2f} "
                            f"<span style='color:#00FFA3;'>({(s['target']/s['entry']-1)*100:+.1f}%)</span><br>"
                            f"⚖️ <b>손익비</b>: 1 : {s['rr']}</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(f"- {s['plan']}")
                    if s.get("stop_price") and s.get("avg_price", 0) > 0:
                        st.caption(f"보유분 손절가(ATR): {s['stop_price']:,.2f} (평단 {s['avg_price']:,.2f})")
                    st.markdown(
                        f"<span style='font-size:0.78rem; color:#64748B;'>"
                        f"지지 {s['support']:,.1f} · 저항 {s['resistance']:,.1f} · "
                        f"MA50 {s['ma50']:,.1f} · MA200 {s.get('ma200','?')}</span>",
                        unsafe_allow_html=True,
                    )

                # 기술분석관 차트 재사용 (토글 시에만 로드)
                if st.toggle(f"📈 {s['ticker']} 차트 보기 (캔들+MA+볼린저+RSI+MACD)", key=f"sig_chart_{s['ticker']}"):
                    with st.spinner(f"{s['ticker']} 차트 로딩..."):
                        fig = cached_candle_chart(s["ticker"], "6mo")
                        if fig:
                            st.plotly_chart(fig, use_container_width=True, key=f"sig_fig_{s['ticker']}")
                        else:
                            st.warning("차트 데이터를 가져올 수 없습니다.")
                st.markdown("---")

            st.caption("⚠️ 규칙 기반 기술적 시그널입니다. 펀더멘탈·뉴스는 반영되지 않으니 AI 평가서와 함께 보세요. 투자 권유가 아닙니다.")

    # ── 📈 시그널 정확도 추적 (예측 기록 → 자동 채점) ──
    try:
        from modules.signal_tracker import get_accuracy_stats
        acc = get_accuracy_stats()
        with st.expander(
            f"📈 시그널 정확도 추적 — 기록 {acc.get('total', 0)}건 "
            f"(채점완료 {acc.get('graded', 0)} · 대기 {acc.get('pending', 0)})",
            expanded=False,
        ):
            st.caption("매일 생성된 시그널을 자동 저장하고, 10일 후 실제 가격으로 채점합니다. "
                       "데이터가 쌓이면 어떤 셋업이 잘 맞는지 보이고, 나중에 ML 학습 재료가 됩니다.")
            if acc.get("graded", 0) == 0:
                st.info(f"📝 예측을 기록하는 중입니다. 채점은 예측 10일 후부터 시작돼요. "
                        f"(현재 {acc.get('pending', 0)}건 대기 중)")
            else:
                ac1, ac2, ac3 = st.columns(3)
                wr = acc.get("win_rate")
                ac1.metric("종합 적중률", f"{wr}%" if wr is not None else "—",
                           help="목표 달성/하락 회피 = 적중, 손절/상승 놓침 = 실패")
                br = acc.get("buy_avg_ret")
                ac2.metric("매수 시그널 평균수익", f"{br:+.1f}%" if br is not None else "—")
                ac3.metric("채점 완료", f"{acc['graded']}건")

                if acc.get("setup_stats"):
                    st.markdown("**셋업별 성적:**")
                    for setup, st_ in sorted(acc["setup_stats"].items(), key=lambda x: -x[1]["win_rate"]):
                        st.markdown(f"- {setup} — 적중률 **{st_['win_rate']:.0f}%** "
                                    f"(n={st_['n']}), 평균수익 {st_['avg_ret']:+.1f}%")

                recent = acc.get("recent")
                if recent is not None and not recent.empty:
                    st.markdown("**최근 채점 결과:**")
                    show = recent[["pred_date", "ticker", "action", "setup", "outcome", "ret_pct"]].copy()
                    show.columns = ["예측일", "티커", "액션", "셋업", "결과", "수익률%"]
                    st.dataframe(show, hide_index=True, use_container_width=True)
    except Exception as e:
        print(f"정확도 추적 표시 실패: {e}")

    # ── 총 자산 요약 (실시간 시세 기준) ──
    try:
        from modules.issue_tracker import get_usdkrw_rate

        @st.cache_data(ttl=600)
        def cached_fx_tracker():
            return get_usdkrw_rate()

        fx = cached_fx_tracker()
        fx_factor = snap_df["_is_kr"].map(lambda kr: 1.0 if kr else fx)
        stock_eval = (snap_df["_eval_native"] * fx_factor).sum()
        stock_cost = (snap_df["_cost_native"] * fx_factor).sum()
        pnl = stock_eval - stock_cost
        pnl_rate = (pnl / stock_cost * 100) if stock_cost > 0 else 0

        cash = _load_cash()
        cash_total = cash["krw"] + cash["usd"] * fx
        total_asset = stock_eval + cash_total
        cash_ratio = (cash_total / total_asset * 100) if total_asset > 0 else 0

        tm1, tm2, tm3, tm4 = st.columns(4)
        tm1.metric("💰 총 자산", f"₩{total_asset:,.0f}", delta=f"${total_asset / fx:,.0f}")
        tm2.metric("📈 주식 평가액", f"₩{stock_eval:,.0f}")
        tm3.metric("📊 총 손익", f"₩{pnl:,.0f}", delta=f"{pnl_rate:+.2f}%")
        tm4.metric("💵 현금 비중", f"{cash_ratio:.1f}%", delta=f"₩{cash_total:,.0f}")

        # 자산 스냅샷 자동 기록 + 추이 차트
        from utils.portfolio_utils import record_asset_snapshot, load_asset_history
        if total_asset > 0:
            record_asset_snapshot(total_asset, stock_eval, cash_total)

        history = load_asset_history()
        with st.expander(f"📈 자산 추이 ({len(history)}일 기록됨)", expanded=False):
            if len(history) >= 2:
                first, last = history["total"].iloc[0], history["total"].iloc[-1]
                change = (last / first - 1) * 100 if first > 0 else 0
                st.caption(
                    f"기록 시작 {history.index[0].strftime('%Y-%m-%d')} 대비 "
                    f"**{change:+.2f}%** (₩{last - first:+,.0f})"
                )
                st.area_chart(history[["total"]].rename(columns={"total": "총 자산 (₩)"}))
                st.line_chart(history[["stock", "cash"]].rename(
                    columns={"stock": "주식 (₩)", "cash": "현금 (₩)"}))
            else:
                st.info("접속할 때마다 그날의 총자산이 자동 기록됩니다. 이틀째부터 추이 그래프가 그려져요.")

        st.markdown("---")
    except Exception as e:
        st.warning(f"총 자산 계산 실패: {e}")

    # 숨김 컬럼 제거 후 표시
    snap_df = snap_df.drop(columns=["_eval_native", "_cost_native", "_is_kr"], errors="ignore")

    name_map = {it["ticker"]: it["name"] for it in tracked}
    qty_map = {it["ticker"]: it["quantity"] for it in tracked}
    snap_df.insert(0, "종목명", snap_df["티커"].map(name_map))
    snap_df.insert(2, "수량", snap_df["티커"].map(qty_map))

    def color_change(val):
        if isinstance(val, (int, float)):
            if val > 0:
                return "color: #FF4B4B; font-weight: 700;"
            if val < 0:
                return "color: #4B7BFF; font-weight: 700;"
        return ""

    def color_rsi(val):
        if isinstance(val, (int, float)):
            if val >= 70:
                return "color: #FF4B4B;"
            if val <= 30:
                return "color: #00FFA3;"
        return ""

    styled = (
        snap_df.style
        .map(color_change, subset=["1일", "5일", "수익률"])
        .map(color_rsi, subset=["RSI"])
        .format({"1일": "{:+.2f}%", "5일": "{:+.2f}%", "수익률": "{:+.2f}%", "수량": "{:,.0f}"}, na_rep="-")
    )
    st.dataframe(styled, hide_index=True, use_container_width=True)
    st.caption("수익률: 평단가 대비 · RSI: 🔴70↑ 과매수 / 🟢30↓ 과매도 · 5분 캐시")

    # ── 4. 전체 이슈 브리핑 ──
    st.markdown("---")
    bc1, bc2 = st.columns([1, 1])
    with bc1:
        brief_clicked = st.button("🤖 전체 종목 이슈 브리핑 생성", type="primary", use_container_width=True)
    with bc2:
        if st.button("🔄 시세/뉴스 새로고침", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    @st.cache_data(ttl=600)
    def cached_news(ticker):
        return fetch_ticker_news(ticker, max_news=6)

    if brief_clicked:
        with st.spinner("모든 종목 뉴스 수집 + AI 브리핑 생성 중..."):
            try:
                holdings_news = {t: cached_news(t) for t in tickers}
                briefing = summarize_all_issues(holdings_news)
                st.session_state.tracker_briefing = {
                    "text": briefing,
                    "time": datetime.datetime.now().strftime("%H:%M"),
                }
            except Exception as e:
                st.error(f"❌ 브리핑 생성 실패: {e}")

    if st.session_state.get("tracker_briefing"):
        b = st.session_state.tracker_briefing
        st.markdown(f"#### 📋 이슈 브리핑 <span style='font-size:0.8rem;color:#64748B;'>(생성: {b['time']})</span>", unsafe_allow_html=True)
        st.markdown(b["text"])

    # ── AI 보유종목 평가 (성향 선택형) ──
    st.markdown("---")
    st.subheader("🤖 AI 보유종목 평가")

    from modules.portfolio_advisor import PERSONAS, get_or_create_eval

    stance_labels = {k: f"{v['label']} — {v['description']}" for k, v in PERSONAS.items()}
    selected_label = st.radio(
        "투자 성향을 선택하세요 (성향에 따라 같은 데이터도 다르게 평가합니다)",
        options=list(stance_labels.values()),
        index=0,  # 기본: 공격적
        key="advisor_stance",
    )
    stance = next(k for k, v in stance_labels.items() if v == selected_label)

    ec1, ec2 = st.columns([3, 1])
    with ec1:
        eval_clicked = st.button("📋 평가서 생성 (뉴스 검색 + 밸류에이션 + 이벤트 종합)",
                                 type="primary", use_container_width=True, key="eval_btn")
    with ec2:
        force_eval = st.button("🔄 강제 재생성", use_container_width=True, key="eval_force",
                               help="오늘 캐시를 무시하고 새로 검색/평가")

    if eval_clicked or force_eval:
        from utils.web_llm import get_search_provider
        if not get_search_provider():
            st.error("⚠️ 검색 LLM 키가 없습니다. .env에 PERPLEXITY_API_KEY를 설정하세요.")
        else:
            with st.spinner(f"{PERSONAS[stance]['label']} 관점으로 뉴스 검색 + 평가 작성 중... (30초~1분)"):
                try:
                    result = get_or_create_eval(tracked, stance, force=bool(force_eval))
                    st.session_state.portfolio_eval = {**result, "stance": stance}
                    if result["cached"]:
                        st.toast("📋 오늘 생성된 평가를 불러왔습니다 (API 호출 없음)")
                    else:
                        st.toast("✅ 평가서 생성 완료!")
                except Exception as e:
                    st.error(f"❌ 평가 생성 실패: {e}")

    ev = st.session_state.get("portfolio_eval")
    if ev:
        badge = PERSONAS[ev["stance"]]["label"]
        st.markdown(
            f"<span style='font-size:0.8rem;color:#64748B;'>"
            f"{badge} 관점 · 생성 {ev['time']}{' · 캐시' if ev.get('cached') else ''}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(ev["text"])

    # ── 5. 종목별 뉴스 ──
    st.markdown("---")
    st.subheader("📰 종목별 최신 이슈")

    for item in tracked:
        ticker = item["ticker"]
        with st.expander(f"**{item['name']}** ({ticker})", expanded=False):
            try:
                news_list = cached_news(ticker)
                if news_list:
                    for n in news_list:
                        st.markdown(
                            f"- [{n['title']}]({n['link']})  \n"
                            f"  <span style='color:#64748B; font-size:0.8rem;'>{n['publisher']} · {n['published']}</span>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.info("최근 뉴스가 없습니다.")
            except Exception as e:
                st.warning(f"뉴스 로드 실패: {e}")

            # 기술분석관 차트 재사용
            if st.toggle("📈 차트 보기", key=f"news_chart_{ticker}"):
                with st.spinner(f"{ticker} 차트 로딩..."):
                    fig = cached_candle_chart(ticker, "6mo")
                    if fig:
                        st.plotly_chart(fig, use_container_width=True, key=f"news_fig_{ticker}")
                    else:
                        st.warning("차트 데이터를 가져올 수 없습니다.")


# ──────────────────────────────────────────────
# TAB: 데일리 신문
# ──────────────────────────────────────────────
def render_tab_paper():
    from modules.daily_paper import (
        fetch_holdings_news, get_sec_filings,
        publish_daily_paper, get_saved_paper,
    )
    from modules.market_overview import get_macro_data
    from modules.issue_tracker import get_portfolio_holdings
    from modules.event_calendar import get_all_events, get_upcoming_events

    # ── 신문 마스트헤드 ──
    today_str = datetime.date.today().strftime("%Y년 %m월 %d일")
    weekday = ["월", "화", "수", "목", "금", "토", "일"][datetime.date.today().weekday()]
    st.markdown(f"""
    <div style="text-align:center; border-top: 4px double #E2E8F0; border-bottom: 1px solid #475569; padding: 18px 0 12px 0; margin-bottom: 4px;">
        <div style="font-family: 'Noto Serif KR', 'Pretendard', serif; font-size: 40px; font-weight: 900; letter-spacing: 0.15em; color: #FFFFFF;">
            株式日報
        </div>
        <div style="font-size: 12px; color: #94A3B8; margin-top: 6px; letter-spacing: 0.2em;">
            STOCK AGENT DAILY · {today_str} ({weekday}) · 나만의 투자 신문
        </div>
    </div>
    <div style="border-bottom: 4px double #E2E8F0; margin-bottom: 20px;"></div>
    """, unsafe_allow_html=True)

    holdings = get_portfolio_holdings()
    tickers = [h["ticker"] for h in holdings]

    @st.cache_data(ttl=300)
    def paper_macro():
        return get_macro_data()

    @st.cache_data(ttl=900)
    def paper_news(ticker_tuple):
        return fetch_holdings_news([{"ticker": t, "name": t} for t in ticker_tuple])

    @st.cache_data(ttl=3600)
    def paper_filings(ticker_tuple):
        return get_sec_filings(list(ticker_tuple))

    # ── 1면 발행/증보 버튼 ──
    if st.button("🗞️ 오늘의 신문 발행 / 새 소식 반영", type="primary", use_container_width=True):
        with st.spinner("📰 기사 수집 및 편집 중... (뉴스 + 공시 + 매크로)"):
            try:
                macro = paper_macro()
                news = paper_news(tuple(tickers))
                filings = paper_filings(tuple(tickers))
                result = publish_daily_paper(macro, news, filings, holdings=holdings)
                st.session_state.daily_paper = result

                engine = result.get("engine", "")
                engine_label = f" ({engine.split('-')[0].title()} 웹검색 🔍)" if engine.endswith("websearch") else ""
                if result["status"] == "unchanged":
                    st.toast("📰 새 소식이 없어 기존 신문을 유지합니다 (토큰 절약)")
                elif result["status"] == "updated":
                    st.toast(f"📰 개정판 발행!{engine_label}")
                else:
                    st.toast(f"🗞️ 오늘의 신문이 발행되었습니다{engine_label}")
            except Exception as e:
                st.error(f"❌ 신문 발행 실패: {e}")

    # 앱 재시작 후에도 오늘 신문 복원
    if "daily_paper" not in st.session_state:
        saved = get_saved_paper()
        if saved:
            st.session_state.daily_paper = saved

    # 매크로 1개월 추세 (구 '시장' 탭 흡수)
    with st.expander("📊 매크로 지표 상세 (1개월 추세 차트)", expanded=False):
        render_macro_grid()

    # ── 3단 신문 레이아웃 ──
    col_left, col_center, col_right = st.columns([1, 2.4, 0.9])

    # 좌측: 시장 시세판
    with col_left:
        st.markdown("##### 📊 시세판")
        try:
            macro = paper_macro()
            for m in macro:
                if m["change_pct"] is None:
                    continue
                color = "#FF4B4B" if m["change_pct"] >= 0 else "#4B7BFF"
                st.markdown(
                    f"<div style='display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px dotted #334155; font-size:0.85rem;'>"
                    f"<span>{m['name'].split(' ')[0]} {m['name'].split(' ')[1] if len(m['name'].split(' ')) > 1 else ''}</span>"
                    f"<span><b>{m['value_str']}</b> <span style='color:{color};'>{m['change_pct']:+.2f}%</span></span></div>",
                    unsafe_allow_html=True,
                )
        except Exception as e:
            st.warning(f"시세 로드 실패: {e}")

    # 중앙: AI 1면 기사
    with col_center:
        paper = st.session_state.get("daily_paper")
        if paper:
            st.markdown(
                f"<span style='font-size:0.75rem;color:#64748B;'>발행 {paper['time']} · AI 편집</span>",
                unsafe_allow_html=True,
            )
            st.markdown(paper["front"])
        else:
            st.markdown("""
            <div style="text-align:center; padding: 60px 20px; color: #64748B; border: 1px dashed #334155; border-radius: 12px;">
                <div style="font-size: 40px;">🗞️</div>
                <div style="margin-top: 10px;">위의 <b>'오늘의 신문 발행'</b> 버튼을 누르면<br>
                보유 종목 뉴스 + SEC 공시 + 매크로를 종합한<br>오늘의 1면이 발행됩니다.</div>
            </div>
            """, unsafe_allow_html=True)

    # 우측: 이번 주 일정
    with col_right:
        st.markdown("##### 📅 이번 주 일정")
        try:
            events = get_all_events(tickers)
            upcoming = get_upcoming_events(events, days=7)
            if upcoming:
                for ev in upcoming[:6]:
                    d_day = f"D-{ev['d_day']}" if ev["d_day"] > 0 else "오늘"
                    st.markdown(
                        f"<div style='font-size:0.8rem; padding:3px 0;'>"
                        f"<b style='color:#00FFA3;'>{d_day}</b> {ev['title']}</div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("이번 주 일정 없음")
        except Exception as e:
            st.warning(f"일정 로드 실패: {e}")

    # ── 하단: 종목별 뉴스 전체 ──
    st.markdown("---")
    st.markdown("##### 📰 종목별 상세 뉴스 (구글 뉴스)")
    try:
        news = paper_news(tuple(tickers))
        news_cols = st.columns(2)
        for i, (ticker, items) in enumerate(news.items()):
            with news_cols[i % 2]:
                with st.expander(f"**{ticker}** ({len(items)}건)"):
                    for n in items:
                        st.markdown(
                            f"- [{n['title']}]({n['link']})  \n"
                            f"  <span style='color:#64748B; font-size:0.75rem;'>{n['publisher']} · {n['published']}</span>",
                            unsafe_allow_html=True,
                        )
    except Exception as e:
        st.warning(f"뉴스 로드 실패: {e}")


# ──────────────────────────────────────────────
# 매크로 추세 그리드 (데일리 탭에서 사용)
# ──────────────────────────────────────────────
def render_macro_grid():
    from modules.market_overview import get_macro_data
    import plotly.graph_objects as go

    @st.cache_data(ttl=300)
    def cached_macro():
        return get_macro_data()

    with st.spinner("매크로 지표 조회 중..."):
        macro = cached_macro()

    def mini_spark(spark, up: bool):
        color = "#FF4B4B" if up else "#4B7BFF"
        fig = go.Figure(go.Scatter(
            y=spark, mode="lines",
            line=dict(color=color, width=1.5),
            fill="tozeroy", fillcolor=f"rgba({'255,75,75' if up else '75,123,255'},0.08)",
        ))
        fig.update_layout(
            height=50, margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            showlegend=False,
        )
        return fig

    # 5열 x 2행 그리드
    for row_start in range(0, len(macro), 5):
        cols = st.columns(5)
        for col, m in zip(cols, macro[row_start:row_start + 5]):
            with col:
                delta = f"{m['change_pct']:+.2f}%" if m["change_pct"] is not None else None
                st.metric(m["name"], m["value_str"], delta=delta)
                if m["spark"]:
                    spark_min = min(m["spark"])
                    spark_shift = [v - spark_min for v in m["spark"]]
                    st.plotly_chart(
                        mini_spark(spark_shift, (m["change_pct"] or 0) >= 0),
                        use_container_width=True,
                        config={"displayModeBar": False},
                        key=f"spark_{m['name']}",
                    )

    st.caption("미니 차트: 최근 1개월 추세 · 5분 캐시")


# ──────────────────────────────────────────────
# TAB: 매매일지
# ──────────────────────────────────────────────
def render_tab_journal():
    from modules.trade_journal import (
        load_journal, add_trade, delete_trade, get_stats, apply_to_portfolio,
    )
    from modules.issue_tracker import resolve_ticker

    st.header("📒 매매일지")
    st.caption("매수/매도를 기록하면 실현손익·승률이 자동 집계됩니다. 포트폴리오 반영도 한 번에.")

    # ── 거래 입력 ──
    with st.form("trade_form", clear_on_submit=True):
        jc1, jc2, jc3, jc4, jc5 = st.columns([2, 2, 1.5, 1.5, 1.5])
        with jc1:
            t_date = st.date_input("날짜", value=datetime.date.today())
        with jc2:
            t_ticker = st.text_input("종목", placeholder="NVDA, 엔비디아, 005930")
        with jc3:
            t_side = st.selectbox("구분", ["매수", "매도"])
        with jc4:
            t_qty = st.text_input("수량", placeholder="10")
        with jc5:
            t_price = st.text_input("체결가", placeholder="450.50")

        t_memo = st.text_input("메모 (매매 이유 — 나중에 복기할 때 가장 중요합니다)",
                               placeholder="예: 실적 서프라이즈 + RSI 35 반등 구간 분할매수 1차")
        t_apply = st.checkbox("포트폴리오에 자동 반영 (수량/평단가 갱신)", value=True)
        t_submit = st.form_submit_button("✍️ 기록", use_container_width=True, type="primary")

    if t_submit:
        try:
            qty = float(t_qty.replace(",", ""))
            price = float(t_price.replace(",", ""))
            if not t_ticker.strip() or qty <= 0 or price <= 0:
                raise ValueError
        except ValueError:
            st.error("종목/수량/체결가를 올바르게 입력하세요.")
        else:
            ticker = resolve_ticker(t_ticker.strip())
            side = "buy" if t_side == "매수" else "sell"
            avg_price = None

            if t_apply:
                result = apply_to_portfolio(ticker, side, qty, price)
                if not result["success"]:
                    st.error(f"❌ {result['message']}")
                    st.stop()
                avg_price = result.get("avg_price")
                st.toast(f"💼 {result['message']}")

            row = add_trade(
                t_date.strftime("%Y-%m-%d"), ticker, t_ticker.strip(),
                side, qty, price, memo=t_memo.strip(), avg_price=avg_price,
            )
            if row.get("realized_pnl") is not None:
                pnl = row["realized_pnl"]
                emoji = "🎉" if pnl >= 0 else "📉"
                st.toast(f"{emoji} 실현손익: {pnl:+,.2f} 기록됨")
            st.cache_data.clear()
            st.rerun()

    # ── 통계 ──
    stats = get_stats()
    if stats["n_trades"] == 0:
        st.info("👆 첫 거래를 기록해보세요. 매도 기록부터 실현손익이 집계됩니다.")
        return

    st.markdown("---")
    st.subheader("📊 매매 성과")
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    sc1.metric("총 거래", f"{stats['n_trades']}건")
    sc2.metric("실현손익 합계", f"{stats['total_realized']:+,.0f}")
    sc3.metric("승률", f"{stats['win_rate']}%" if stats["n_sells"] else "—",
               help="실현손익이 양수인 매도 비율")
    sc4.metric("평균 수익/손실", f"{stats['avg_win']:+,.0f} / {stats['avg_loss']:+,.0f}")
    sc5.metric("손익비", f"{stats['profit_factor']}" if stats["profit_factor"] else "—",
               help="평균 수익 ÷ 평균 손실. 1.5 이상이면 양호")

    if len(stats["monthly"]) > 0 or len(stats["by_ticker"]) > 0:
        gc1, gc2 = st.columns(2)
        with gc1:
            if len(stats["monthly"]) > 0:
                st.markdown("**월별 실현손익**")
                st.bar_chart(stats["monthly"])
        with gc2:
            if len(stats["by_ticker"]) > 0:
                st.markdown("**종목별 실현손익**")
                st.bar_chart(stats["by_ticker"])

    # ── 거래 내역 ──
    st.markdown("---")
    st.subheader("📋 거래 내역")
    journal = load_journal()
    display = journal.copy().iloc[::-1]  # 최신순
    display["side"] = display["side"].map({"buy": "🟢 매수", "sell": "🔴 매도"})
    display.columns = ["날짜", "티커", "종목명", "구분", "수량", "체결가", "매도시 평단", "실현손익", "메모"]
    st.dataframe(display, hide_index=True, use_container_width=True)

    with st.expander("🗑️ 기록 삭제"):
        del_idx = st.number_input(
            "삭제할 행 번호 (위 표에서 최신=0번이 아닌, 입력 순서 기준)",
            min_value=0, max_value=max(len(journal) - 1, 0), step=1, key="journal_del_idx",
        )
        old = journal.iloc[int(del_idx)] if len(journal) > 0 else None
        if old is not None:
            st.caption(f"선택됨: {old['date']} {old['ticker']} {old['side']} {old['quantity']}주 @ {old['price']}")
        if st.button("삭제 실행", key="journal_del_btn"):
            delete_trade(int(del_idx))
            st.rerun()


# ──────────────────────────────────────────────
# TAB 1: RAG 챗봇
# ──────────────────────────────────────────────
def render_tab_rag():
    st.header("🎥 영상분석관 챗봇")
    st.caption("YouTube 영상 자막 기반 주식 정보 및 시황 검색")

    if "rag_messages" not in st.session_state:
        st.session_state.rag_messages = []
    if "pending_followup_question" not in st.session_state:
        st.session_state.pending_followup_question = None

    # ── 데이터 수집 (YouTube → Pinecone) ──
    with st.expander("📥 데이터 수집 현황 / 영상 수집", expanded=False):
        from utils.sheet_loader import SheetDataLoader

        if "pipeline_status" not in st.session_state:
            try:
                with st.spinner("수집 현황 조회 중..."):
                    loader = SheetDataLoader()
                    st.session_state.pipeline_status = loader.get_last_data_info()
            except Exception as e:
                st.session_state.pipeline_status = {"youtube_date": "N/A", "market_date": "N/A"}
                print(f"Status loading error: {e}")

        status = st.session_state.pipeline_status
        sc1, sc2 = st.columns(2)
        sc1.metric("🎥 최신 영상", status["youtube_date"])
        sc2.metric("📈 시장 지표", status["market_date"])
        st.caption("YouTube → Pinecone 자동화 (Google Sheets 기준)")

        dc1, dc2 = st.columns(2)
        today = datetime.date.today()
        with dc1:
            start_date = st.date_input("시작일", value=today, key="yt_start_date")
        with dc2:
            end_date = st.date_input("종료일", value=today, key="yt_end_date")

        if st.button("🎬 올랜도킴 영상 수집", icon=":material/movie:", use_container_width=True):
            progress_container = st.empty()
            status_container = st.empty()
            with st.spinner("파이프라인 실행 중..."):
                try:
                    from core.services.data_pipeline import DataPipeline
                    TARGET_CHANNEL_ID_LIST = os.getenv("TARGET_CHANNEL_ID_LIST", "").split(",")
                    ORLANDO_CHANNEL_ID = TARGET_CHANNEL_ID_LIST[0].strip() if TARGET_CHANNEL_ID_LIST else ""
                    pipeline = DataPipeline()

                    def on_status_update(msg):
                        status_container.info(msg)

                    def on_progress_update(ratio, msg):
                        progress_container.progress(ratio, text=msg)

                    result = pipeline.run_youtube_pipeline(
                        channel_id=ORLANDO_CHANNEL_ID,
                        start_date_str=start_date.strftime("%Y-%m-%d"),
                        end_date_str=end_date.strftime("%Y-%m-%d"),
                        progress_callback=on_progress_update,
                        status_callback=on_status_update,
                    )
                    st.success(f"수집 완료: {result.get('success_count', 0)}개")
                    try:
                        loader = SheetDataLoader()
                        st.session_state.pipeline_status = loader.get_last_data_info()
                        st.rerun()
                    except Exception:
                        pass
                except Exception as e:
                    st.error(f"오류: {e}")

    st.markdown("---")

    if st.session_state.pending_followup_question:
        prompt = st.session_state.pending_followup_question
        st.session_state.pending_followup_question = None
    else:
        prompt = st.chat_input("질문을 입력하세요 (예: 삼성전자 전망은?)", key="rag_input")

    if prompt:
        st.session_state.rag_messages.append({"role": "user", "content": prompt})
        with st.spinner("🔀 라우팅 및 답변 생성 중..."):
            try:
                conversation_history = st.session_state.rag_messages[-6:] or None
                result = st.session_state.agentic_router.rag_agent.process(
                    query=prompt, conversation_history=conversation_history
                )
                st.session_state.rag_messages.append({
                    "role": "assistant",
                    "content": result.get("answer", "답변을 생성하지 못했습니다."),
                    "sources": result.get("sources", []),
                    "followup_questions": result.get("followup_questions", []),
                })
            except Exception as e:
                st.session_state.rag_messages.append({
                    "role": "assistant",
                    "content": f"오류 발생: {e}\n\n```\n{traceback.format_exc()}\n```",
                })

    st.markdown("---")
    st.subheader("💬 대화 내역")
    if st.session_state.rag_messages:
        for message in reversed(st.session_state.rag_messages):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if message["role"] == "assistant" and "sources" in message:
                    render_chat_sources(message["sources"])
                    if (
                        message == st.session_state.rag_messages[-1]
                        and message.get("followup_questions")
                    ):
                        st.markdown("**🔍 추가로 궁금하신 사항:**")
                        cols = st.columns(len(message["followup_questions"]))
                        for idx, (col, question) in enumerate(
                            zip(cols, message["followup_questions"])
                        ):
                            with col:
                                if st.button(f"💬 {question}", key=f"followup_{idx}", use_container_width=True):
                                    st.session_state.pending_followup_question = question
                                    st.rerun()
    else:
        st.info("👆 위에서 질문을 입력하세요!")


# ──────────────────────────────────────────────
# TAB 2: 밸류에이션 분석관
# ──────────────────────────────────────────────
def render_tab_quant():
    st.header("📊 밸류에이션 분석관")
    st.caption("보수적인 퀀트 애널리스트 - 적정가 밴드 & 관심 매수 구간을 알아서 판단해 드립니다.")

    if "quant_analyst" not in st.session_state:
        with st.spinner("Quant Analyst 초기화 중..."):
            try:
                st.session_state.quant_analyst = QuantAnalyst()
            except Exception as e:
                st.error(f"Quant Analyst 초기화 실패: {e}")
                st.stop()

    if "quant_messages" not in st.session_state:
        st.session_state.quant_messages = []

    st.markdown("---")
    quant_prompt = st.chat_input(
        "티커와 함께 분석을 요청하세요 (예: 테슬라 DCF 밸류에이션 해봐, NVDA 적정가 얼마야?)",
        key="quant_input",
    )

    if quant_prompt:
        st.session_state.quant_messages.append({"role": "user", "content": quant_prompt})
        with st.spinner("📊 최적의 모델로 밸류에이션 계산 중..."):
            try:
                result = st.session_state.quant_analyst.process(query=quant_prompt)
                if result.get("success"):
                    answer = result.get("analysis", "분석을 완료하지 못했습니다.")
                    stock_info = result.get("stock_data", {})
                    if stock_info and not stock_info.get("error"):
                        answer += (
                            f"\n\n---\n**[수집된 실시간 데이터]**\n"
                            f"- **종목명:** {stock_info.get('company_name')} ({stock_info.get('ticker')})\n"
                            f"- **현재 가격:** ${stock_info.get('price')}\n"
                            f"- **EPS (TTM):** ${stock_info.get('eps_ttm', 'N/A')} | **EPS (FY1):** ${stock_info.get('eps_fy1', 'N/A')}\n"
                            f"- **P/E:** {stock_info.get('pe_ratio', 'N/A')}배\n"
                            f"- **BPS (주당순자산):** ${stock_info.get('book_value', 'N/A')} | **P/B:** {stock_info.get('pb_ratio', 'N/A')}배\n"
                        )
                else:
                    answer = f"⚠️ 분석 실패: {result.get('error', '알 수 없는 오류')}"
                st.session_state.quant_messages.append({"role": "assistant", "content": answer})
            except Exception as e:
                st.session_state.quant_messages.append({
                    "role": "assistant",
                    "content": f"오류 발생: {e}\n\n```\n{traceback.format_exc()}\n```",
                })

    st.markdown("---")
    st.subheader("💬 대화 내역")
    if st.session_state.quant_messages:
        for message in reversed(st.session_state.quant_messages):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
    else:
        st.info("👆 위에서 종목명/티커와 함께 분석을 요청하세요! (알아서 적합한 모델을 선택합니다)")


# ──────────────────────────────────────────────
# TAB 3: 기술분석관
# ──────────────────────────────────────────────
def render_tab_tech():
    st.header("📈 기술분석관 (차트 챗봇)")
    st.caption("yfinance 실시간 주가 및 차트 보조지표 분석 (예: TSLA 매수 타점 어때?)")

    if "tech_messages" not in st.session_state:
        st.session_state.tech_messages = []

    # ── 실시간 캔들차트 ──────────────────────
    with st.expander("🕯️ 실시간 캔들차트 보기", expanded=True):
        cc1, cc2, cc3, cc4 = st.columns([2, 1, 1, 1])
        with cc1:
            chart_ticker = st.text_input("티커", value="NVDA", key="chart_ticker").strip().upper()
        with cc2:
            chart_period = st.selectbox("기간", ["1mo", "3mo", "6mo", "1y", "2y", "5y"], index=2, key="chart_period")
        with cc3:
            show_ma = st.checkbox("이동평균선", value=True, key="chart_ma")
        with cc4:
            show_bb = st.checkbox("볼린저밴드", value=True, key="chart_bb")

        if chart_ticker:
            from utils.chart_builder import build_candlestick_chart

            @st.cache_data(ttl=300)
            def cached_chart(ticker, period, ma, bb):
                return build_candlestick_chart(ticker, period, show_bb=bb, show_ma=ma)

            with st.spinner(f"{chart_ticker} 차트 로딩 중..."):
                fig = cached_chart(chart_ticker, chart_period, show_ma, show_bb)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning(f"⚠️ '{chart_ticker}' 데이터를 가져올 수 없습니다. 티커를 확인하세요.")

    st.markdown("---")
    tech_prompt = st.chat_input(
        "종목명이나 티커와 함께 질문을 입력하세요 (예: 엔비디아 차트 분석해줘)",
        key="tech_input",
    )

    if tech_prompt:
        st.session_state.tech_messages.append({"role": "user", "content": tech_prompt})
        with st.spinner("📈 차트 데이터 불러오는 중..."):
            try:
                result = st.session_state.agentic_router.tech_agent.process(query=tech_prompt)
                if result.get("indicators") and "error" not in result.get("indicators", {}):
                    ind = result["indicators"]
                    ticker = ind.get("ticker", "UNKNOWN")
                    answer = (
                        result.get("analysis", "분석을 완료하지 못했습니다.")
                        + f"\n\n---\n**[{ticker}] 주요 지표 요약**\n"
                        f"- **현재가:** ${ind.get('current_price')} (1일 변동: {ind.get('price_change_1d')}%)\n"
                        f"- **추세 (이동평균선):** {ind.get('trend')} (MA20: ${ind.get('ma20')}, MA50: ${ind.get('ma50')})\n"
                        f"- **RSI (14일):** {ind.get('rsi')} ➜ **{ind.get('rsi_signal')}**\n"
                        f"- **MACD:** {ind.get('macd')} ➜ **{ind.get('macd_trend')} 추세**\n"
                        f"- **볼린저 밴드 위치:** {ind.get('bb_position')}%\n"
                    )
                else:
                    err = (result.get("indicators") or {}).get("error", "알 수 없는 오류")
                    answer = f"⚠️ 분석 실패: {err}"
                st.session_state.tech_messages.append({"role": "assistant", "content": answer})
            except Exception as e:
                st.session_state.tech_messages.append({
                    "role": "assistant",
                    "content": f"오류 발생: {e}\n\n```\n{traceback.format_exc()}\n```",
                })

    st.markdown("---")
    st.subheader("💬 대화 내역")
    if st.session_state.tech_messages:
        for message in reversed(st.session_state.tech_messages):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
    else:
        st.info("👆 위에서 종목명/티커와 함께 질문을 입력하세요!")


# ──────────────────────────────────────────────
# TAB 4: 포트폴리오 서브탭 렌더러
# ──────────────────────────────────────────────
def _render_subtab_detail(data):
    st.subheader("📋 보유 종목 상세")
    for analysis in data.get("stock_analyses", []):
        with st.expander(f"**{analysis['name']}** ({analysis['ticker']})", expanded=False):
            info = analysis.get("current_info", {})
            ticker_str = analysis["ticker"]
            if ticker_str.endswith(".KS") or ticker_str.endswith(".KQ"):
                symbol = "₩"
            elif ticker_str.endswith(".T"):
                symbol = "¥"
            else:
                symbol = "$"

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("보유 수량", f"{info.get('quantity', 0):,}주")
                st.metric("평균 매수가 (KRW)", f"₩{info.get('avg_price', 0):,.0f}")
            with col2:
                st.metric("현재가 (Native)", f"{symbol}{info.get('current_price', 0):,.2f}")
                krw_eval = info.get("quantity", 0) * info.get("current_price_krw", info.get("current_price", 0))
                st.metric("평가금액 (KRW)", f"₩{krw_eval:,.0f}")
            with col3:
                st.metric(
                    "평가손익 (KRW)",
                    f"₩{info.get('profit_loss', 0):,.0f}",
                    delta=f"{info.get('profit_rate', 0):.2f}%",
                )

            st.markdown("---")
            st.markdown("### 🤖 AI 투자 피드백")
            feedback = analysis.get("ai_feedback", "")
            if feedback:
                st.markdown(feedback)
            else:
                st.info("AI 피드백을 생성할 수 없습니다.")

            rag_insights = analysis.get("rag_insights", [])
            if rag_insights:
                st.markdown("### 📺 관련 YouTube 분석")
                for idx, insight in enumerate(rag_insights[:3], 1):
                    meta = insight.get("metadata", {})
                    st.markdown(
                        f"**{idx}. {meta.get('영상제목', 'N/A')}**  \n"
                        f"채널: {meta.get('채널명', 'N/A')} | 업로드: {meta.get('업로드일자', 'N/A')}  \n"
                        f"[영상 보기]({meta.get('영상링크', '#')})"
                    )


def _render_subtab_viz(edited_df):
    st.subheader("📊 포트폴리오 시각화 분석")
    with st.spinner("섹터 분류 및 시각화 준비 중..."):
        try:
            classifier = SectorClassifier()
            df_for_viz = calc_portfolio_metrics(edited_df)
            df_classified = classifier.classify_portfolio(df_for_viz, delay_seconds=0.1)
            sector_summary = classifier.get_sector_summary(df_classified)
            visualizer = PortfolioVisualizer()

            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(visualizer.create_sector_pie_chart(df_classified, sector_summary), use_container_width=True)
            with col2:
                st.plotly_chart(visualizer.create_profit_bar_chart(df_classified), use_container_width=True)

            st.markdown("---")
            st.plotly_chart(visualizer.create_treemap(df_classified), use_container_width=True)
            st.markdown("---")

            col3, col4 = st.columns(2)
            with col3:
                st.plotly_chart(visualizer.create_allocation_sunburst(df_classified), use_container_width=True)
            with col4:
                st.plotly_chart(visualizer.create_sector_performance_chart(df_classified, sector_summary), use_container_width=True)
        except Exception as e:
            st.error(f"❌ 시각화 생성 실패: {e}")
            st.code(traceback.format_exc())


def _render_subtab_alerts(edited_df):
    st.subheader("🔔 포트폴리오 알림")
    if st.button("🔍 알림 확인", use_container_width=True):
        with st.spinner("알림 확인 중..."):
            try:
                from modules.portfolio_alert import PortfolioAlert
                from core.rag_engine import RAGEngine
                rag_engine = RAGEngine()
                alert_system = PortfolioAlert(rag_engine)
                alerts = alert_system.check_portfolio_alerts(calc_portfolio_metrics(edited_df), days_back=7)
                st.markdown(alert_system.format_alerts(alerts))
            except Exception as e:
                st.error(f"❌ 알림 확인 실패: {e}")


def _render_subtab_rebalance(edited_df):
    st.subheader("⚖️ 포트폴리오 리밸런싱 제안")
    if st.button("📊 리밸런싱 분석", use_container_width=True):
        with st.spinner("리밸런싱 분석 중..."):
            try:
                from modules.portfolio_rebalancer import PortfolioRebalancer
                from core.rag_engine import RAGEngine
                rag_engine = RAGEngine()
                rebalancer = PortfolioRebalancer(rag_engine)
                result = rebalancer.generate_rebalancing_suggestions(calc_portfolio_metrics(edited_df))

                if result["status"] == "success":
                    rebal_tab1, rebal_tab2, rebal_tab3 = st.tabs(["📊 분석 결과", "📈 효율적 투자선", "💰 비용 시뮬레이션"])
                    balance = result["current_balance"]

                    with rebal_tab1:
                        st.markdown("### 📊 현재 포트폴리오 균형")
                        col1, col2, col3 = st.columns(3)
                        col1.metric("총 평가금액", f"${balance['total_value']:,.0f}")
                        col2.metric("평균 수익률", f"{balance['risk_metrics']['avg_profit_rate']:.2f}%")
                        col3.metric("손실 종목 비율", f"{balance['risk_metrics']['losing_stocks_ratio']:.1f}%")
                        st.markdown("#### 섹터별 비중")
                        sector_data = pd.DataFrame([
                            {"섹터": s, "비중 (%)": w} for s, w in balance["sector_weights"].items()
                        ])
                        st.bar_chart(sector_data.set_index("섹터"))
                        st.markdown("---")
                        st.markdown("### 💡 리밸런싱 제안")
                        st.markdown(result["suggestions"]["full_text"])

                    with rebal_tab2:
                        st.subheader("📈 Efficient Frontier (효율적 투자선)")
                        opt_result = result.get("optimization", {})
                        if opt_result.get("success"):
                            import plotly.graph_objects as go
                            frontier = opt_result["frontier"]
                            curr = opt_result["current_metrics"]
                            fig = go.Figure()
                            fig.add_trace(go.Scatter(
                                x=frontier["Volatility"], y=frontier["Returns"], mode="markers",
                                marker=dict(color=frontier["Sharpe"], colorscale="Viridis",
                                            showscale=True, colorbar=dict(title="Sharpe Ratio"), size=5),
                                name="Simulation",
                            ))
                            fig.add_trace(go.Scatter(
                                x=[opt_result["volatility"]], y=[opt_result["returns"]], mode="markers",
                                marker=dict(color="red", size=15, symbol="star"), name="Max Sharpe",
                            ))
                            fig.add_trace(go.Scatter(
                                x=[curr["volatility"]], y=[curr["returns"]], mode="markers",
                                marker=dict(color="blue", size=15, symbol="diamond"), name="My Portfolio",
                            ))
                            fig.update_layout(title="Risk vs Return Profile",
                                              xaxis_title="Volatility (Risk)",
                                              yaxis_title="Expected Annual Return", height=500)
                            st.plotly_chart(fig, use_container_width=True)
                            st.info(
                                f"**내 포트폴리오**: 수익률 {curr['returns']*100:.1f}%, "
                                f"변동성 {curr['volatility']*100:.1f}%, Sharpe {curr['sharpe_ratio']:.2f}\n\n"
                                f"**최적 포트폴리오**: 수익률 {opt_result['returns']*100:.1f}%, "
                                f"변동성 {opt_result['volatility']*100:.1f}%, Sharpe {opt_result['sharpe_ratio']:.2f}"
                            )
                        else:
                            st.warning("최적화 데이터를 불러올 수 없습니다.")

                    with rebal_tab3:
                        st.subheader("💰 리밸런싱 비용 시뮬레이션")
                        sim_result = result.get("simulation", {})
                        if sim_result:
                            col1, col2 = st.columns(2)
                            col1.metric("예상 총 비용 (수수료+세금)", f"{sim_result['total_cost']:,.0f}원")
                            col2.metric("비용 비율", f"{sim_result['cost_ratio']:.2f}%")
                            st.markdown("#### 📋 상세 거래 내역")
                            details = pd.DataFrame(sim_result["details"])
                            if not details.empty:
                                st.dataframe(
                                    details[["ticker", "action", "diff", "cost"]].style.format(
                                        {"diff": "{:,.0f}", "cost": "{:,.0f}"}
                                    )
                                )
                            else:
                                st.info("리밸런싱이 필요하지 않습니다.")
                        else:
                            st.info("시뮬레이션 결과가 없습니다.")
                else:
                    st.error(f"❌ 리밸런싱 분석 실패: {result.get('message', '알 수 없는 오류')}")
            except Exception as e:
                st.error(f"❌ 리밸런싱 분석 실패: {e}")


def _render_subtab_personal_chat(edited_df):
    st.subheader("💬 개인화 투자 조언 챗봇")
    st.caption("보유 종목 정보를 활용한 맞춤형 투자 조언")

    if "personalized_rag_messages" not in st.session_state:
        st.session_state.personalized_rag_messages = []

    if "personalized_rag_engine" not in st.session_state:
        try:
            from core.personalized_rag import PersonalizedRAG
            from core.rag_engine import RAGEngine
            st.session_state.personalized_rag_engine = PersonalizedRAG(RAGEngine())
        except Exception as e:
            st.error(f"개인화 RAG 초기화 실패: {e}")

    user_query = st.chat_input("질문을 입력하세요 (예: 내가 보유한 AI 종목들 어때?)", key="personalized_rag_input")

    if user_query:
        st.session_state.personalized_rag_messages.append({"role": "user", "content": user_query})
        with st.spinner("답변 생성 중..."):
            try:
                history = st.session_state.personalized_rag_messages[-6:] or None
                result = st.session_state.personalized_rag_engine.chat(
                    query=user_query, top_k=10, temperature=0.7,
                    conversation_history=history, use_portfolio_context=True,
                )
                st.session_state.personalized_rag_messages.append({
                    "role": "assistant",
                    "content": result["answer"],
                    "sources": result.get("sources", []),
                    "related_holdings": result.get("related_holdings", []),
                    "followup_questions": result.get("followup_questions", []),
                })
            except Exception as e:
                st.session_state.personalized_rag_messages.append({
                    "role": "assistant", "content": f"오류 발생: {e}"
                })

    if st.session_state.personalized_rag_messages:
        for message in reversed(st.session_state.personalized_rag_messages):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if message["role"] == "assistant":
                    holdings = message.get("related_holdings", [])
                    if holdings:
                        with st.expander("💼 관련 보유 종목"):
                            for stock in holdings:
                                c1, c2, c3 = st.columns(3)
                                c1.write(f"**{stock['name']}** ({stock['ticker']})")
                                c2.write(f"{stock['quantity']:,}주")
                                c3.write(f"{stock['profit_rate']:.1f}%")
                    if message.get("sources"):
                        render_chat_sources(message["sources"])
    else:
        st.info("👆 위에서 질문을 입력하세요!")


def _price_meta_file() -> str:
    from utils.user_data import portfolio_meta_path
    return portfolio_meta_path()


def _load_meta() -> dict:
    import json
    try:
        with open(_price_meta_file(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_meta(**updates):
    """기존 메타를 유지하면서 일부 키만 갱신"""
    import json
    meta = _load_meta()
    meta.update(updates)
    path = _price_meta_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _save_price_timestamp():
    _save_meta(price_updated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))


def _load_price_timestamp() -> str:
    return _load_meta().get("price_updated_at", "기록 없음")


def _load_cash() -> dict:
    """{'krw': float, 'usd': float}"""
    meta = _load_meta()
    return {"krw": float(meta.get("cash_krw", 0) or 0), "usd": float(meta.get("cash_usd", 0) or 0)}


def render_tab_portfolio():
    from utils.user_data import portfolio_path, current_user
    st.header(f"💼 내 포트폴리오 — {current_user()}")
    st.caption("개인 보유 종목 — 로그인한 계정별로 따로 저장됩니다.")

    if "portfolio_data" not in st.session_state:
        st.session_state.portfolio_data = None

    PORTFOLIO_FILE = portfolio_path()
    st.subheader("📊 포트폴리오 관리")

    if not os.path.exists(PORTFOLIO_FILE):
        st.info(f"📁 아직 포트폴리오가 비어있습니다. 종목을 추가하거나 샘플로 시작하세요.")
        if st.button("📁 샘플 파일 생성"):
            os.makedirs(os.path.dirname(PORTFOLIO_FILE), exist_ok=True)
            with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
                f.write("ticker,name,quantity,avg_price,current_price\n")
                f.write("TSLA,테슬라,10,200,250\n")
                f.write("NVDA,엔비디아,2,400,600\n")
            st.success("✅ 샘플 파일이 생성되었습니다!")
            st.rerun()
        return

    if "df_portfolio" not in st.session_state or st.session_state.get("reload_csv", False):
        st.session_state.df_portfolio = pd.read_csv(PORTFOLIO_FILE)
        st.session_state.reload_csv = False

    # ── 간편 종목 추가 (표 형태, 여러 개 한 번에) ──
    st.markdown("**➕ 종목 추가** — 행을 추가해 입력하세요. 티커/종목명·현재가는 자동 조회됩니다.")

    if "qa_editor_ver" not in st.session_state:
        st.session_state.qa_editor_ver = 0

    qa_template = pd.DataFrame({
        "종목": pd.Series(dtype="str"),
        "수량": pd.Series(dtype="float"),
        "평단가": pd.Series(dtype="float"),
    })
    qa_df = st.data_editor(
        qa_template,
        num_rows="dynamic",
        use_container_width=True,
        key=f"quick_add_editor_{st.session_state.qa_editor_ver}",
        column_config={
            "종목": st.column_config.TextColumn("종목", help="티커 또는 한글명 (예: 엔비디아, 005930, TSLA)", required=True),
            "수량": st.column_config.NumberColumn("수량", help="비우면 1"),
            "평단가": st.column_config.NumberColumn("평단가", help="비우면 현재가로 설정"),
        },
    )

    if st.button("➕ 일괄 추가", use_container_width=True, key="qa_submit"):
        from modules.issue_tracker import resolve_ticker
        import yfinance as yf

        df_pf = st.session_state.df_portfolio
        added, failed = [], []

        rows = qa_df.dropna(subset=["종목"])
        rows = rows[rows["종목"].astype(str).str.strip() != ""]

        if rows.empty:
            st.warning("추가할 종목을 입력하세요.")
        else:
            with st.spinner("종목 조회 중..."):
                for _, row in rows.iterrows():
                    name_input = str(row["종목"]).strip()
                    qty = float(row["수량"]) if pd.notna(row["수량"]) and row["수량"] > 0 else 1.0
                    avg = float(row["평단가"]) if pd.notna(row["평단가"]) and row["평단가"] > 0 else 0.0

                    try:
                        ticker = resolve_ticker(name_input)
                        if ticker in df_pf["ticker"].astype(str).values:
                            failed.append((name_input, "이미 포트폴리오에 있음"))
                            continue
                        tk = yf.Ticker(ticker)
                        hist = tk.history(period="5d")
                        if hist.empty:
                            failed.append((name_input, f"'{ticker}' 데이터 없음"))
                            continue
                        current = float(hist["Close"].iloc[-1])
                        stock_name = tk.info.get("shortName") or name_input
                        df_pf = pd.concat([df_pf, pd.DataFrame([{
                            "ticker": ticker, "name": stock_name,
                            "quantity": qty,
                            "avg_price": avg if avg > 0 else current,
                            "current_price": current,
                        }])], ignore_index=True)
                        added.append(f"{stock_name} ({ticker})")
                    except Exception as e:
                        failed.append((name_input, str(e)))

            if added:
                st.session_state.df_portfolio = df_pf
                df_pf.to_csv(PORTFOLIO_FILE, index=False)
                _save_price_timestamp()
                st.session_state.qa_editor_ver += 1  # 입력 표 초기화
                st.success(f"✅ {len(added)}개 추가: {', '.join(added)}")
            for name, reason in failed:
                st.warning(f"⚠️ {name}: {reason}")
            if added:
                st.rerun()

    # ── 편집 표 (수정 즉시 자동 저장) ──
    st.markdown("---")
    ic1, ic2 = st.columns([3, 2])
    with ic1:
        st.info("💡 표에서 바로 수정하세요. 변경사항은 **자동 저장**됩니다. 행 삭제는 왼쪽 체크 후 Delete 키.")
    with ic2:
        st.info(f"🕐 **현재가 기준**: {_load_price_timestamp()}  \n"
                f"(yfinance 시세 — 장중 약 15분 지연, 장 마감 후엔 종가)")

    _CORE_COLS = ["ticker", "name", "quantity", "avg_price", "current_price"]

    st.caption("✏️ **티커 · 종목명 · 수량 · 평균 매입가** = 직접 입력 | 🔒 **현재가 · 평가금액** = 자동 (가격 업데이트 버튼) | "
               "금액 입력: 미국 주식 **$ 달러** / 한국 주식(.KS) **₩ 원화** 기준")

    # 표시용: 평가금액 자동 계산 컬럼 추가 (저장 시엔 제외)
    editor_input = st.session_state.df_portfolio.copy()
    editor_input["평가금액"] = editor_input["quantity"] * editor_input["current_price"]

    edited_df = st.data_editor(
        editor_input,
        num_rows="dynamic",
        use_container_width=True,
        key="portfolio_editor",
        column_config={
            "ticker": st.column_config.TextColumn("✏️ 티커", help="직접 입력 — 예: AAPL, 005930.KS"),
            "name": st.column_config.TextColumn("✏️ 종목명", help="직접 입력"),
            "quantity": st.column_config.NumberColumn("✏️ 수량", min_value=0, help="직접 입력 — 보유 주식 수"),
            "avg_price": st.column_config.NumberColumn("✏️ 평균 매입가 ($)", min_value=0, format="%.2f",
                                                       help="직접 입력 — 나무 앱의 '매입단가'. 미국 주식은 달러, 한국 주식은 원화로"),
            "current_price": st.column_config.NumberColumn("🔒 현재가 ($)", min_value=0, format="%.2f",
                                                           help="자동 — '📡 가격 업데이트' 버튼으로 갱신"),
            "평가금액": st.column_config.NumberColumn("🔒 평가금액 ($)", format="%.2f", disabled=True,
                                                  help="자동 계산 — 수량 × 현재가"),
        },
    )

    # 계산 컬럼 제거 후 저장/후속 사용 (한국 주식 행은 원화 기준으로 표시됨)
    edited_df = edited_df[_CORE_COLS].copy()

    # 자동 저장: 표 내용이 바뀌면 즉시 CSV 반영
    if not edited_df.equals(st.session_state.df_portfolio[_CORE_COLS]):
        edited_df.to_csv(PORTFOLIO_FILE, index=False)
        st.session_state.df_portfolio = edited_df.copy()
        st.toast("💾 자동 저장됨")

    # ── 현재가 기준 총 평가액 (원화 환산) ──
    try:
        from modules.issue_tracker import get_usdkrw_rate

        @st.cache_data(ttl=600)
        def cached_fx():
            return get_usdkrw_rate()

        fx = cached_fx()
        import numpy as np
        df_t = edited_df.dropna(subset=["ticker"]).copy()
        is_kr = df_t["ticker"].astype(str).str.endswith((".KS", ".KQ"))
        # 원화 환산: 한국 주식은 그대로, 그 외(달러)는 환율 곱
        fx_factor = np.where(is_kr, 1.0, fx)
        df_t["_eval_krw"] = df_t["quantity"] * df_t["current_price"] * fx_factor
        df_t["_cost_krw"] = df_t["quantity"] * df_t["avg_price"] * fx_factor

        stock_eval = df_t["_eval_krw"].sum()
        total_cost = df_t["_cost_krw"].sum()
        total_pnl = stock_eval - total_cost
        pnl_rate = (total_pnl / total_cost * 100) if total_cost > 0 else 0

        # 현금 합산
        cash = _load_cash()
        cash_krw_total = cash["krw"] + cash["usd"] * fx
        total_asset = stock_eval + cash_krw_total
        cash_ratio = (cash_krw_total / total_asset * 100) if total_asset > 0 else 0

        tc1, tc2, tc3, tc4 = st.columns(4)
        tc1.metric("💰 총 자산 (주식+현금)", f"₩{total_asset:,.0f}", delta=f"${total_asset / fx:,.0f}")
        tc2.metric("📈 주식 평가액", f"₩{stock_eval:,.0f}", delta=f"손익 {pnl_rate:+.2f}%")
        tc3.metric("💵 현금", f"₩{cash_krw_total:,.0f}", delta=f"비중 {cash_ratio:.1f}%")
        tc4.metric("총 매입액", f"₩{total_cost:,.0f}")
        st.caption(f"환율 적용: $1 = ₩{fx:,.1f} (미국 주식·달러 현금은 원화 환산 합산)")

        # ── 현금 입력 ──
        with st.expander(f"💵 보유 현금 입력 (현재: ₩{cash['krw']:,.0f} + ${cash['usd']:,.2f})"):
            with st.form("cash_form"):
                cf1, cf2, cf3 = st.columns([2, 2, 1])
                with cf1:
                    cash_krw_in = st.text_input("원화 현금 (₩)", value=f"{cash['krw']:.0f}")
                with cf2:
                    cash_usd_in = st.text_input("달러 현금 ($)", value=f"{cash['usd']:.2f}")
                with cf3:
                    st.write("")
                    cash_submit = st.form_submit_button("💾 저장", use_container_width=True)
            if cash_submit:
                try:
                    new_krw = float(cash_krw_in.replace(",", "") or 0)
                    new_usd = float(cash_usd_in.replace(",", "") or 0)
                    _save_meta(cash_krw=new_krw, cash_usd=new_usd)
                    st.toast("💾 현금 저장됨")
                    st.rerun()
                except ValueError:
                    st.error("숫자만 입력하세요. (콤마는 허용)")
    except Exception as e:
        st.warning(f"총 평가액 계산 실패: {e}")

    col3, col4 = st.columns(2)
    with col3:
        if st.button("📡 가격 업데이트", use_container_width=True, help="yfinance로 실시간 가격 업데이트"):
            with st.spinner("가격 업데이트 중..."):
                try:
                    from utils.price_updater import PriceUpdater
                    updater = PriceUpdater()
                    updated_df = updater.update_portfolio_prices(edited_df, delay_seconds=0.3)
                    updater.save_portfolio(updated_df, PORTFOLIO_FILE)
                    st.session_state.df_portfolio = updated_df
                    st.session_state.reload_csv = True
                    _save_price_timestamp()
                    st.success("✅ 가격 업데이트 완료!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 가격 업데이트 실패: {e}")
    with col4:
        if st.button("🚀 분석 실행", type="secondary", use_container_width=True):
            with st.spinner("포트폴리오 분석 중..."):
                try:
                    from modules.portfolio_analyzer import PortfolioAnalyzer
                    from core.rag_engine import RAGEngine
                    analyzer = PortfolioAnalyzer(RAGEngine())
                    if not edited_df.empty:
                        result = analyzer.analyze_portfolio(calc_portfolio_metrics(edited_df))
                        if result["status"] == "success":
                            st.session_state.portfolio_data = result
                            st.success("✅ 분석 완료!")
                        else:
                            st.error(f"❌ 분석 실패: {result.get('message', '알 수 없는 오류')}")
                    else:
                        st.warning("⚠️ 포트폴리오 데이터가 비어 있습니다.")
                except Exception as e:
                    st.error(f"❌ 오류 발생: {e}")

    # 서브탭은 항상 표시 (분석 전에는 안내 메시지)
    st.markdown("---")
    subtab1, subtab2, subtab3, subtab4, subtab5 = st.tabs(
        ["📋 종목 상세", "📊 시각화", "🔔 알림", "⚖️ 리밸런싱", "💬 개인화 챗봇"]
    )

    with subtab1:
        if st.session_state.portfolio_data:
            data = st.session_state.portfolio_data
            summary = data.get("summary", {})
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("보유 종목 수", f"{summary.get('total_stocks', 0)}개")
            col2.metric("총 평가액", f"₩{summary.get('total_evaluation', 0):,.0f}")
            col3.metric("총 평가손익", f"₩{summary.get('total_profit_loss', 0):,.0f}")
            col4.metric("평균 수익률", f"{summary.get('average_profit_rate', 0):.2f}%")
            top = summary.get("top_performer", {})
            worst = summary.get("worst_performer", {})
            c5, c6 = st.columns(2)
            c5.success(f"🏆 최고 수익: {top.get('name', 'N/A')} ({top.get('profit_rate', 0):.2f}%)")
            c6.error(f"📉 최저 수익: {worst.get('name', 'N/A')} ({worst.get('profit_rate', 0):.2f}%)")
            st.markdown("---")
            _render_subtab_detail(data)
        else:
            st.info("🚀 위에서 **분석 실행**을 눌러주세요.")

    with subtab2:
        _render_subtab_viz(edited_df)

    with subtab3:
        _render_subtab_alerts(edited_df)

    with subtab4:
        _render_subtab_rebalance(edited_df)

    with subtab5:
        _render_subtab_personal_chat(edited_df)


# ──────────────────────────────────────────────
# TAB: 뉴스 & 감성 분석
# ──────────────────────────────────────────────
def render_tab_news():
    st.header("📰 뉴스분석관")
    st.caption("yfinance 최신 뉴스 수집 + AI 감성 분석")

    nc1, nc2 = st.columns([3, 1])
    with nc1:
        news_ticker = st.text_input("티커 입력", value="NVDA", key="news_ticker").strip().upper()
    with nc2:
        max_news = st.selectbox("뉴스 개수", [5, 10, 15, 20], index=1, key="news_count")

    if st.button("🔍 뉴스 분석", use_container_width=True, type="primary", key="news_analyze"):
        if not news_ticker:
            st.warning("티커를 입력하세요.")
            return

        news_agent = st.session_state.agents.get("news_sentiment")
        if news_agent is None:
            news_agent = NewsAgent()

        with st.spinner(f"📰 {news_ticker} 뉴스 수집 및 감성 분석 중..."):
            try:
                result = news_agent.process(f"{news_ticker} 뉴스", ticker=news_ticker, max_news=max_news)
                st.session_state.news_result = result
            except Exception as e:
                st.error(f"❌ 뉴스 분석 실패: {e}")
                return

    result = st.session_state.get("news_result")
    if not result:
        st.info("👆 티커를 입력하고 분석 버튼을 누르세요.")
        return

    analysis = result.get("analysis", {})
    news_list = result.get("news", [])

    # 감성 점수 시각화
    st.markdown("---")
    score = analysis.get("sentiment_score", 50)
    sentiment = analysis.get("sentiment", "중립")

    sc1, sc2, sc3 = st.columns(3)
    sc1.metric("감성 점수", f"{score}/100")
    sc2.metric("시장 감성", sentiment)
    sc3.metric("분석 뉴스 수", f"{analysis.get('news_count', len(news_list))}건")

    # 점수 바
    bar_color = "#FF4B4B" if score < 40 else ("#FFD700" if score < 60 else "#00FFA3")
    st.markdown(f"""
    <div style="background: rgba(255,255,255,0.08); border-radius: 8px; height: 14px; margin: 8px 0 16px 0;">
        <div style="background: {bar_color}; width: {score}%; height: 100%; border-radius: 8px;"></div>
    </div>
    """, unsafe_allow_html=True)

    topics = analysis.get("key_topics", [])
    if topics:
        st.markdown("**🏷️ 주요 토픽:** " + " · ".join(f"`{t}`" for t in topics if t))

    with st.expander("🤖 AI 분석 전문 보기", expanded=True):
        st.markdown(analysis.get("summary", "분석 결과 없음"))

    # 뉴스 리스트
    st.markdown("---")
    st.subheader(f"📋 최신 뉴스 ({len(news_list)}건)")
    if news_list:
        for i, news in enumerate(news_list, 1):
            st.markdown(
                f"**{i}. [{news['title']}]({news['link']})**  \n"
                f"<span style='color:#94A3B8; font-size:0.85rem;'>"
                f"{news['publisher']} · {news['published']}</span>",
                unsafe_allow_html=True,
            )
    else:
        st.info("수집된 뉴스가 없습니다.")


# ──────────────────────────────────────────────
# TAB: 가격 알림
# ──────────────────────────────────────────────
def render_tab_alerts():
    from modules.price_alert import (
        load_alerts, save_alerts, add_alert, remove_alert,
        run_alert_check, CONDITION_TYPES,
    )

    st.header("🔔 가격 알림")
    st.caption("조건 충족 시 이메일로 알려드립니다. 서버 cron이 30분마다 자동 체크합니다.")

    # ── 알림 추가 폼 ──
    with st.form("add_alert_form"):
        ac1, ac2, ac3, ac4 = st.columns([2, 3, 2, 1])
        with ac1:
            alert_ticker = st.text_input("티커", value="NVDA")
        with ac2:
            cond_label = st.selectbox("조건", list(CONDITION_TYPES.values()))
        with ac3:
            alert_value = st.number_input("기준값", min_value=0.0, value=100.0, step=1.0)
        with ac4:
            st.write("")
            submitted = st.form_submit_button("➕ 추가", use_container_width=True)

        if submitted and alert_ticker.strip():
            cond_key = next(k for k, v in CONDITION_TYPES.items() if v == cond_label)
            add_alert(alert_ticker.strip(), cond_key, alert_value)
            st.success(f"✅ {alert_ticker.upper()} 알림이 추가되었습니다.")
            st.rerun()

    # ── 등록된 알림 목록 ──
    st.markdown("---")
    alerts = load_alerts()
    st.subheader(f"📋 등록된 알림 ({len(alerts)}건)")

    if not alerts:
        st.info("등록된 알림이 없습니다. 위에서 추가하세요.")
    else:
        for alert in alerts:
            lc1, lc2, lc3, lc4, lc5 = st.columns([1.5, 3, 1.5, 1.5, 1])
            status_icon = "🟢" if alert.get("enabled") else "⚪"
            lc1.markdown(f"{status_icon} **{alert['ticker']}**")
            lc2.markdown(CONDITION_TYPES.get(alert["condition"], alert["condition"]))
            lc3.markdown(f"기준: `{alert['value']}`")
            lc4.markdown(
                f"<span style='font-size:0.8rem;color:#94A3B8;'>"
                f"{'발송: ' + alert['last_triggered'] if alert.get('last_triggered') else '대기 중'}</span>",
                unsafe_allow_html=True,
            )
            with lc5:
                bc1, bc2 = st.columns(2)
                if not alert.get("enabled"):
                    if bc1.button("🔄", key=f"reenable_{alert['id']}", help="재활성화"):
                        for a in alerts:
                            if a["id"] == alert["id"]:
                                a["enabled"] = True
                        save_alerts(alerts)
                        st.rerun()
                if bc2.button("🗑️", key=f"del_alert_{alert['id']}", help="삭제"):
                    remove_alert(alert["id"])
                    st.rerun()

    # ── 수동 체크 ──
    st.markdown("---")
    if st.button("📡 지금 바로 조건 체크 + 이메일 발송", use_container_width=True):
        with st.spinner("조건 체크 중..."):
            result = run_alert_check()
            if result["triggered_count"] > 0:
                st.success(
                    f"✅ {result['triggered_count']}건 조건 충족! "
                    f"이메일 발송: {'성공' if result['email_sent'] else '실패 (환경변수 확인)'}"
                )
                for t in result["triggered"]:
                    st.markdown(f"- **{t['ticker']}**: 현재값 `{t['current_value']}` (기준 `{t['value']}`)")
            else:
                st.info("충족된 조건이 없습니다.")


# ──────────────────────────────────────────────
# TAB: 백테스트
# ──────────────────────────────────────────────
def render_tab_backtest():
    from modules.backtester import run_backtest, STRATEGIES

    st.header("🧪 전략 백테스트")
    st.caption("과거 데이터로 매매 전략을 시뮬레이션합니다. (일봉 종가 체결, 수수료 0.1% 가정)")

    bc1, bc2, bc3, bc4 = st.columns([2, 3, 2, 2])
    with bc1:
        bt_ticker = st.text_input("티커", value="NVDA", key="bt_ticker").strip().upper()
    with bc2:
        strat_label = st.selectbox("전략", list(STRATEGIES.values()), key="bt_strategy")
    with bc3:
        bt_period = st.selectbox("기간", ["1y", "2y", "5y", "10y"], index=1, key="bt_period")
    with bc4:
        bt_capital = st.number_input("초기 자본 ($)", min_value=100, value=10000, step=1000, key="bt_capital")

    strat_key = next(k for k, v in STRATEGIES.items() if v == strat_label)

    # 전략별 파라미터
    params = {}
    if strat_key == "rsi":
        pc1, pc2 = st.columns(2)
        params["rsi_buy"] = pc1.slider("매수 RSI (이하)", 10, 50, 30, key="bt_rsi_buy")
        params["rsi_sell"] = pc2.slider("매도 RSI (이상)", 50, 90, 70, key="bt_rsi_sell")

    if st.button("🚀 백테스트 실행", type="primary", use_container_width=True, key="bt_run"):
        if not bt_ticker:
            st.warning("티커를 입력하세요.")
            return
        with st.spinner(f"{bt_ticker} {bt_period} 백테스트 중..."):
            result = run_backtest(
                ticker=bt_ticker, strategy=strat_key, period=bt_period,
                initial_capital=bt_capital, params=params,
            )
            st.session_state.bt_result = result

    result = st.session_state.get("bt_result")
    if not result:
        st.info("👆 조건을 설정하고 백테스트를 실행하세요.")
        return
    if not result["success"]:
        st.error(f"❌ {result['error']}")
        return

    m = result["metrics"]
    st.markdown("---")
    st.subheader("📊 성과 요약")

    mc1, mc2, mc3, mc4 = st.columns(4)
    delta_vs_bh = m["total_return"] - m["bh_return"]
    mc1.metric("전략 수익률", f"{m['total_return']}%", delta=f"{delta_vs_bh:+.2f}%p vs B&H")
    mc2.metric("Buy & Hold", f"{m['bh_return']}%")
    mc3.metric("연환산 수익률 (CAGR)", f"{m['cagr']}%")
    mc4.metric("최대 낙폭 (MDD)", f"{m['mdd']}%")

    mc5, mc6, mc7 = st.columns(3)
    mc5.metric("샤프 비율", f"{m['sharpe']}")
    mc6.metric("승률", f"{m['win_rate']}%")
    mc7.metric("거래 횟수", f"{m['n_trades']}회")

    # 자산 곡선
    st.markdown("---")
    st.subheader("📈 자산 곡선 (전략 vs Buy & Hold)")
    st.line_chart(result["equity_curve"])

    st.subheader("📉 낙폭 (Drawdown)")
    st.area_chart(result["drawdown"])

    # 거래 내역
    if result["trades"]:
        st.markdown("---")
        st.subheader(f"📋 거래 내역 ({len(result['trades'])}건)")
        trades_df = pd.DataFrame(result["trades"])
        st.dataframe(trades_df, hide_index=True, use_container_width=True)
    else:
        st.info("해당 기간 동안 완결된 거래가 없습니다.")

    st.caption("⚠️ 백테스트는 과거 데이터 기반 시뮬레이션이며 미래 수익을 보장하지 않습니다. "
               "슬리피지, 세금, 배당은 단순화되어 있습니다.")


# ──────────────────────────────────────────────
# TAB 5: 종합 분석관
# ──────────────────────────────────────────────
def render_tab_comprehensive():
    st.header("🔀 종합 분석관")
    st.caption("원하는 에이전트들을 선택하여 한 번에 종합 리뷰를 받으세요.")

    if "comprehensive_messages" not in st.session_state:
        st.session_state.comprehensive_messages = []

    st.markdown("---")
    st.subheader("🤖 투입할 에이전트 선택")
    col1, col2, col3 = st.columns(3)
    with col1:
        use_rag = st.checkbox("🎥 영상분석 (유튜버 인사이트)", value=True,
                              help="RAG 시스템을 통해 유튜버들의 의견과 시황을 종합합니다.")
    with col2:
        use_quant = st.checkbox("📊 가치평가 (퀀트/밸류에이션)", value=True,
                                help="yfinance 기본 데이터를 기반으로 보수적 적정가를 산출합니다.")
    with col3:
        use_tech = st.checkbox("📈 기술적 분석 (차트/지표)", value=True,
                               help="이평선, RSI, MACD 등 실시간 보조지표를 분석합니다.")

    st.markdown("---")
    comp_prompt = st.chat_input("종목명과 질문을 입력하세요 (예: 엔비디아 지금 사도 돼?)", key="comp_input")

    if comp_prompt:
        force_agents = (
            (["rag"] if use_rag else [])
            + (["quant"] if use_quant else [])
            + (["tech"] if use_tech else [])
        )
        if not force_agents:
            st.warning("⚠️ 최소 1개 이상의 에이전트를 선택해주세요.")
        else:
            st.session_state.comprehensive_messages.append({"role": "user", "content": comp_prompt})
            with st.spinner("🔀 선택된 에이전트들이 동시 분석 중..."):
                try:
                    result = st.session_state.agentic_router.route(
                        query=comp_prompt, force_agents=force_agents
                    )
                    agent_tags = (
                        (["🎥영상분석"] if use_rag else [])
                        + (["📊가치평가"] if use_quant else [])
                        + (["📈기술적분석"] if use_tech else [])
                    )
                    answer = (
                        result.get("answer", "답변을 생성하지 못했습니다.")
                        + f"\n\n---\n*⚙️ 참여 에이전트: **{' + '.join(agent_tags)}***"
                    )
                    st.session_state.comprehensive_messages.append({
                        "role": "assistant",
                        "content": answer,
                        "sources": result.get("sources", []),
                    })
                except Exception as e:
                    st.session_state.comprehensive_messages.append({
                        "role": "assistant",
                        "content": f"오류 발생: {e}\n\n```\n{traceback.format_exc()}\n```",
                    })

    st.subheader("💬 종합 분석 대화 내역")
    if st.session_state.comprehensive_messages:
        for message in reversed(st.session_state.comprehensive_messages):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if message["role"] == "assistant" and message.get("sources"):
                    render_chat_sources(message["sources"])
    else:
        st.info("👆 위에서 체크박스를 선택하고 질문을 입력하세요!")


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="Stock Agent Terminal",
        page_icon=PAGE_ICON,
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        render_login_page()
        st.stop()

    # 로그인 후 한 번만: 기존 단일 사용자 데이터를 admin 폴더로 마이그레이션
    if not st.session_state.get("_migrated"):
        from utils.user_data import migrate_legacy_to_user
        moved = migrate_legacy_to_user("admin")
        if moved:
            print(f"마이그레이션 완료: {moved}")
        st.session_state["_migrated"] = True

    if "fg_index" not in st.session_state:
        st.session_state.fg_index, st.session_state.fg_status = get_cached_fear_greed_index()

    fg_index = st.session_state.fg_index
    fg_status = st.session_state.fg_status
    bg_color, text_color, emoji, status_text = get_heatmap_color(fg_index)
    point_color, point_text_color = get_point_color(fg_index)
    apply_theme(bg_color, text_color, point_color)

    st.markdown(f"""
    <style>
        .top-announcement-bar {{
            background-color: {point_color};
            color: {point_text_color} !important;
            padding: 10px 0; text-align: center; font-weight: 700;
            font-size: 14px; width: 100%; position: fixed; top: 0; left: 0;
            z-index: 999991; box-shadow: 0 4px 10px rgba(0,0,0,0.3);
            letter-spacing: -0.02em;
        }}
        [data-testid="stMetric"] {{ border-top: 3px solid {point_color} !important; }}
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {{
            border-left: 5px solid {point_color} !important;
        }}
        [data-testid="stChatMessageAvatarAssistant"] + div div {{ color: {point_color} !important; }}
        .main .block-container {{ padding-top: 4rem !important; }}
    </style>
    """, unsafe_allow_html=True)

    render_ticker_tape()
    st.divider()
    st.title("📊 Stock Agent Terminal")

    initialize_agents()

    col_main, col_side = st.columns([7, 3])

    with col_side:
        render_side_panel(fg_index, fg_status, status_text, point_color)

    with col_main:
        tab_tracker, tab_paper, tab_analysts, tab_portfolio, tab_journal, tab_alerts, tab_backtest = st.tabs([
            "📌 내 종목",
            "🗞️ 데일리",
            "🤖 분석관",
            "💼 내 포트폴리오",
            "📒 매매일지",
            "🔔 가격 알림",
            "🧪 백테스트",
        ])
        with tab_tracker:
            render_tab_tracker()
        with tab_paper:
            render_tab_paper()
        with tab_analysts:
            sub_rag, sub_quant, sub_tech, sub_news, sub_comp = st.tabs([
                "🎥 영상분석 (RAG)",
                "📊 밸류에이션",
                "📈 기술분석 (차트)",
                "📰 뉴스분석",
                "🔀 종합분석",
            ])
            with sub_rag:
                render_tab_rag()
            with sub_quant:
                render_tab_quant()
            with sub_tech:
                render_tab_tech()
            with sub_news:
                render_tab_news()
            with sub_comp:
                render_tab_comprehensive()
        with tab_portfolio:
            render_tab_portfolio()
        with tab_journal:
            render_tab_journal()
        with tab_alerts:
            render_tab_alerts()
        with tab_backtest:
            render_tab_backtest()


if __name__ == "__main__":
    main()
