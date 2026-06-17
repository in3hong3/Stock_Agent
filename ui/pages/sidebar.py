"""사이드 패널 (사용자 정보, 시장 심리, 일정 캘린더)."""
import datetime
import streamlit as st

from ui.components import render_fear_greed_bar


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
    return selected.split(' ', 1)[1]


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

    # ── 🌋 시장 심리 (컴팩트 막대) ──
    render_fear_greed_bar(fg_index, status_text)
    st.divider()

    # ── 📅 일정 (다가오는 일정 전면, 월별 달력은 expander로 접음) ──
    from modules.event_calendar import (
        get_all_events, build_calendar_html, get_upcoming_events,
        add_custom_event, load_custom_events, remove_custom_event,
    )
    from modules.issue_tracker import get_portfolio_holdings

    @st.cache_data(ttl=21600)
    def cached_events(ticker_tuple, custom_ver):
        return get_all_events(list(ticker_tuple))

    holdings = get_portfolio_holdings()
    tickers = tuple(h["ticker"] for h in holdings)
    custom_ver = len(load_custom_events())

    with st.spinner("일정 로딩 중..."):
        events = cached_events(tickers, custom_ver)

    today = datetime.date.today()

    st.markdown("**📅 다가오는 일정**")
    upcoming = get_upcoming_events(events, days=21)
    if upcoming:
        for ev in upcoming[:8]:
            d_day = f"D-{ev['d_day']}" if ev["d_day"] > 0 else "오늘"
            st.markdown(
                f"<div style='font-size:0.85rem; padding:2px 0; display:flex; gap:8px;'>"
                f"<span style='color:{point_color}; font-weight:700; min-width:38px;'>{d_day}</span>"
                f"<span style='color:#94A3B8; min-width:38px;'>{ev['date'].strftime('%m/%d')}</span>"
                f"<span>{ev['title']}</span></div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("3주 이내 일정이 없습니다.")

    # 월별 달력 (기본 접힘)
    with st.expander("🗓️ 월별 달력 보기"):
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

    # 일정 직접 추가 (기본 접힘)
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

    # ── 💰 총 자산 미니 요약 (어느 탭에서든 항상 보임) ──
    st.divider()
    try:
        from modules.issue_tracker import get_usdkrw_rate
        from ui.pages._meta import compute_total_assets
        from utils.portfolio_utils import record_asset_snapshot

        @st.cache_data(ttl=600)
        def _side_fx():
            return get_usdkrw_rate()

        fx = _side_fx() or 1400.0
        a = compute_total_assets(holdings, fx)
        if a["total"] > 0:
            # 자산 추이 기록 (하루치 누적 — 트래커 자산추이 차트가 이 데이터를 읽음)
            record_asset_snapshot(a["total"], a["stock_eval"], a["cash_total"])

            pnl_color = "#FF4B4B" if a["pnl"] >= 0 else "#4B7BFF"
            usd_total = a["total"] / fx if fx else 0
            st.markdown(
                f"<div style='background:#16181F; border:1px solid rgba(255,255,255,0.05); "
                f"border-radius:12px; padding:12px 14px;'>"
                f"<div style='font-size:0.85rem; font-weight:700; margin-bottom:8px;'>💰 내 자산</div>"
                f"<div style='font-size:1.35rem; font-weight:700; color:#E2E8F0; line-height:1.1;'>"
                f"₩{a['total']:,.0f}</div>"
                f"<div style='font-size:0.72rem; color:#94A3B8; margin:2px 0 8px;'>≈ ${usd_total:,.0f}</div>"
                f"<div style='display:flex; justify-content:space-between; font-size:0.8rem; padding:2px 0;'>"
                f"<span style='color:#94A3B8;'>주식 평가</span>"
                f"<span style='color:#E2E8F0;'>₩{a['stock_eval']:,.0f}</span></div>"
                f"<div style='display:flex; justify-content:space-between; font-size:0.8rem; padding:2px 0;'>"
                f"<span style='color:#94A3B8;'>평가 손익</span>"
                f"<span style='color:{pnl_color}; font-weight:700;'>{a['pnl']:+,.0f} ({a['pnl_rate']:+.1f}%)</span></div>"
                f"<div style='display:flex; justify-content:space-between; font-size:0.8rem; padding:2px 0;'>"
                f"<span style='color:#94A3B8;'>현금 비중</span>"
                f"<span style='color:#E2E8F0;'>{a['cash_ratio']:.1f}%</span></div>"
                f"</div>",
                unsafe_allow_html=True,
            )
    except Exception as e:
        print(f"사이드 자산 요약 실패: {e}")
