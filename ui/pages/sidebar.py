"""사이드 패널 (사용자 정보, 시장 심리, 일정 캘린더)."""
import datetime
import streamlit as st

from ui.components import render_fear_greed_gauge


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

    @st.cache_data(ttl=21600)
    def cached_events(ticker_tuple, custom_ver):
        return get_all_events(list(ticker_tuple))

    holdings = get_portfolio_holdings()
    tickers = tuple(h["ticker"] for h in holdings)
    custom_ver = len(load_custom_events())

    with st.spinner("일정 로딩 중..."):
        events = cached_events(tickers, custom_ver)

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
