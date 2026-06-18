"""AI 핫 섹터 조사 탭 — 섹터/테마 ETF 모멘텀 랭킹 + AI 해설."""
import streamlit as st


def render_tab_hot_sectors():
    from modules.sector_scanner import scan_sectors, explain_hot_sectors, score_stocks
    from modules.issue_tracker import get_portfolio_holdings

    st.header("🔥 AI 핫 섹터 조사")
    st.caption("미국 섹터·테마 ETF의 상대강도(모멘텀)를 정량 측정해 '지금 뜨는 섹터'를 랭킹하고, "
               "AI가 그 이유를 최신 뉴스 기반으로 해설합니다.")

    inc1, inc2 = st.columns([3, 1])
    with inc1:
        include_themes = st.checkbox("세부 테마 ETF 포함 (반도체·원전·방산·바이오 등)", value=True)
    with inc2:
        if st.button("🔄 새로고침", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    @st.cache_data(ttl=1800)
    def _cached_scan(themes):
        return scan_sectors(include_themes=themes)

    with st.spinner("섹터 ETF 모멘텀 계산 중..."):
        scan = _cached_scan(include_themes)

    if scan.get("error"):
        st.error(f"❌ {scan['error']}")
        return

    rows = scan.get("rows", [])
    if not rows:
        st.info("스캔 결과가 없습니다.")
        return

    bench = scan.get("benchmark_1m")
    st.caption(f"기준: {scan.get('generated','')} · 벤치마크 SPY 1개월 {bench:+.1f}% · "
               f"30분 캐시 · 모멘텀 = 1주 0.2 + 1개월 0.5 + 3개월 0.3 + 벤치 초과 가산")

    # ── 핫 섹터 카드 (상위) ──
    hot = [r for r in rows if r.get("hot")]
    UP, DOWN, MUTED, MAIN = "#FF4B4B", "#4B7BFF", "#94A3B8", "#E2E8F0"
    cards = ""
    for r in hot:
        c = UP if r["r_1m"] >= 0 else DOWN
        rs_c = UP if r["rs_1m"] >= 0 else DOWN
        cards += (
            f"<div style='background:#16181F; border:1px solid #FF4B4B33; border-radius:10px; "
            f"padding:10px 12px; min-width:0;'>"
            f"<div style='display:flex; justify-content:space-between; align-items:baseline;'>"
            f"<span style='font-size:0.82rem; font-weight:700; color:{MAIN};'>{r['name']}</span>"
            f"<span style='font-size:0.66rem; color:{MUTED};'>{r['ticker']}·{r['kind']}</span></div>"
            f"<div style='font-size:1.1rem; font-weight:700; color:{c}; margin:3px 0 1px;'>{r['r_1m']:+.1f}%</div>"
            f"<div style='font-size:0.7rem; color:{MUTED};'>1개월 · 벤치대비 "
            f"<span style='color:{rs_c};'>{r['rs_1m']:+.1f}%p</span></div></div>"
        )
    st.markdown(
        f"<div style='background:linear-gradient(160deg,#2A1414,#16181F); border:1px solid #FF4B4B55; "
        f"border-radius:14px; padding:14px 18px; margin-bottom:12px;'>"
        f"<div style='font-weight:700; font-size:1.05rem; margin-bottom:10px;'>🔥 지금 뜨는 섹터 TOP {len(hot)}</div>"
        f"<div style='display:grid; grid-template-columns:repeat(auto-fill, minmax(140px,1fr)); gap:8px;'>"
        f"{cards}</div></div>",
        unsafe_allow_html=True,
    )

    # ── 전체 랭킹 표 ──
    import pandas as pd
    df = pd.DataFrame(rows)
    df_show = df[["ticker", "name", "kind", "r_1w", "r_1m", "r_3m", "rs_1m", "momentum_score"]].copy()
    df_show.columns = ["티커", "섹터/테마", "구분", "1주%", "1개월%", "3개월%", "vs벤치%p", "모멘텀점수"]

    def _color(v):
        if isinstance(v, (int, float)):
            if v > 0:
                return "color:#FF4B4B; font-weight:700;"
            if v < 0:
                return "color:#4B7BFF; font-weight:700;"
        return ""

    styled = df_show.style.map(_color, subset=["1주%", "1개월%", "3개월%", "vs벤치%p"]).format(
        {"1주%": "{:+.1f}", "1개월%": "{:+.1f}", "3개월%": "{:+.1f}",
         "vs벤치%p": "{:+.1f}", "모멘텀점수": "{:.1f}"}, na_rep="-")
    st.dataframe(styled, hide_index=True, use_container_width=True)
    st.caption("vs벤치 = SPY 대비 1개월 초과수익 · 빨강 상승 / 파랑 하락")

    # ── AI 해설 (버튼 클릭 시에만 — 토큰 비용) ──
    st.markdown("---")
    st.subheader("🤖 AI 섹터 해설")
    st.caption("상위 섹터가 '왜 지금 강한지'를 최신 뉴스 기반으로 분석합니다. (LLM 웹검색 — 토큰 비용 발생)")

    ec1, ec2 = st.columns([3, 1])
    with ec1:
        top_n = st.slider("해설할 상위 섹터 수", 3, 8, 5, key="hot_top_n")
    with ec2:
        st.write("")
        explain_clicked = st.button("📝 AI 해설 생성", type="primary", use_container_width=True)

    if explain_clicked:
        from utils.web_llm import get_search_provider
        if not get_search_provider():
            st.error("⚠️ 검색 LLM 키가 없습니다. .env에 PERPLEXITY_API_KEY / GEMINI_API_KEY 중 하나를 설정하세요.")
        else:
            from utils.loading import ProgressBanner
            try:
                with ProgressBanner(title="AI가 핫 섹터 분석 중", total=2, icon="🔥") as banner:
                    banner.step("📰 상위 섹터 최신 뉴스·자금흐름 검색 중...")
                    banner.step("✍️ 섹터 전략 분석 작성 중... (15~30초)")
                    holdings = get_portfolio_holdings()
                    result = explain_hot_sectors(scan, top_n=top_n, holdings=holdings)
                    banner.done("✅ 분석 완료!")
                st.session_state["hot_sector_explain"] = result
            except Exception as e:
                st.error(f"❌ 해설 생성 실패: {e}")

    if st.session_state.get("hot_sector_explain"):
        st.markdown(st.session_state["hot_sector_explain"])

    # ── 🏆 종목 스코어링 (월스트리트 100점) ──
    st.markdown("---")
    st.subheader("🏆 종목 스코어링 (월스트리트 100점)")
    st.caption("섹터/테마를 입력하면 그 안에서 8-10곳을 발굴해 랭킹, 티커를 나열하면 그 종목들만 점수화합니다. "
               "밸류에이션(30) + 미래 성장 모멘텀(40) + 경제적 해자(30). (LLM 웹검색 — 토큰 비용)")

    # 핫 섹터 순위에서 바로 가져오기 편하도록 상위 섹터명 제시
    hot_names = " · ".join(r["name"].split(" (")[0] for r in hot[:5])
    st.caption(f"💡 지금 핫한 섹터: {hot_names}")

    sc1, sc2 = st.columns([4, 1])
    with sc1:
        score_query = st.text_input(
            "섹터/테마 또는 티커",
            placeholder="예: 원전  /  방산  /  NVDA TSLA AVGO",
            key="score_query",
            label_visibility="collapsed",
        )
    with sc2:
        score_clicked = st.button("🏆 스코어링", type="primary", use_container_width=True)

    if score_clicked:
        if not score_query.strip():
            st.warning("섹터명 또는 티커를 입력하세요.")
        else:
            from utils.web_llm import get_search_provider
            if not get_search_provider():
                st.error("⚠️ 검색 LLM 키가 없습니다. .env에 PERPLEXITY_API_KEY / GEMINI_API_KEY 중 하나를 설정하세요.")
            else:
                from utils.loading import ProgressBanner
                try:
                    with ProgressBanner(title=f"'{score_query}' 종목 스코어링 중", total=2, icon="🏆") as banner:
                        banner.step("📰 수주·계약·밸류에이션 데이터 검색 중...")
                        banner.step("✍️ 100점 랭킹 분석 작성 중... (20~40초)")
                        holdings = get_portfolio_holdings()
                        result = score_stocks(score_query.strip(), holdings=holdings)
                        banner.done("✅ 스코어링 완료!")
                    st.session_state["stock_score_result"] = result
                except Exception as e:
                    st.error(f"❌ 스코어링 실패: {e}")

    if st.session_state.get("stock_score_result"):
        st.markdown(st.session_state["stock_score_result"])

    st.caption("⚠️ ETF 모멘텀·AI 스코어링은 분석 참고자료이며 미래 수익을 보장하지 않습니다. 투자 권유가 아닙니다.")
