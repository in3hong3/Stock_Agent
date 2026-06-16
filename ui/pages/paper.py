"""데일리 신문 탭 + 매크로 그리드."""
import datetime
import streamlit as st


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


def render_tab_paper():
    from modules.daily_paper import (
        fetch_holdings_news, get_sec_filings,
        publish_daily_paper, get_saved_paper,
    )
    from modules.market_overview import get_macro_data
    from modules.issue_tracker import get_portfolio_holdings
    from modules.event_calendar import get_all_events, get_upcoming_events

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

    if st.button("🗞️ 오늘의 신문 발행 / 새 소식 반영", type="primary", use_container_width=True):
        from utils.loading import ProgressBanner
        try:
            with ProgressBanner(
                title="오늘의 신문 발행 중",
                total=5, icon="🗞️",
            ) as banner:
                banner.step("📊 매크로 지표 수집 중 (VIX, S&P500, 달러)...")
                macro = paper_macro()
                banner.step("📰 종목별 뉴스 수집 중...")
                news = paper_news(tuple(tickers))
                banner.step("📋 SEC 공시 조회 중...")
                filings = paper_filings(tuple(tickers))
                banner.step("✍️ AI 편집장이 1면 작성 중... (30~60초)")
                result = publish_daily_paper(macro, news, filings, holdings=holdings)
                banner.done("✅ 신문 발행 완료!")
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

    if "daily_paper" not in st.session_state:
        saved = get_saved_paper()
        if saved:
            st.session_state.daily_paper = saved

    if (not st.session_state.get("daily_paper")
            and tickers
            and not st.session_state.get("_auto_paper_attempted")):
        st.session_state["_auto_paper_attempted"] = True
        from utils.loading import ProgressBanner
        try:
            with ProgressBanner(
                title="오늘의 신문 자동 발행 중 (첫 진입)",
                total=5, icon="🌅",
            ) as banner:
                banner.step("📊 매크로 지표 수집 중...")
                macro_a = paper_macro()
                banner.step("📰 종목별 뉴스 수집 중...")
                news_a = paper_news(tuple(tickers))
                banner.step("📋 SEC 공시 조회 중...")
                filings_a = paper_filings(tuple(tickers))
                banner.step("✍️ AI 편집장이 1면 작성 중... (30~60초)")
                result_a = publish_daily_paper(macro_a, news_a, filings_a, holdings=holdings)
                banner.done("✅ 자동 발행 완료!")
            st.session_state.daily_paper = result_a
            st.toast("🌅 오늘의 신문이 자동 발행되었습니다")
        except Exception as e:
            st.warning(f"⚠️ 자동 발행 실패: {e} — 위 '발행' 버튼으로 수동 시도해주세요.")

    with st.expander("📊 매크로 지표 상세 (1개월 추세 차트)", expanded=False):
        render_macro_grid()

    col_left, col_center, col_right = st.columns([1, 2.4, 0.9])

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

    with col_center:
        paper = st.session_state.get("daily_paper")
        if paper:
            st.markdown(
                f"<span style='font-size:0.75rem;color:#64748B;'>"
                f"📅 {datetime.date.today().strftime('%Y.%m.%d')} 발행 {paper['time']} · AI 편집 · "
                f"<span style='color:#00FFA3;'>오늘 종일 유지됩니다</span></span>",
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
