"""분석관 5종 — RAG / 밸류에이션 / 기술분석 / 뉴스 / 종합."""
import traceback
import streamlit as st

from ui.components import render_chat_sources
from agents.quant_agent import QuantAnalyst
from agents.news_agent import NewsAgent


def render_tab_rag():
    st.header("🎥 영상분석관 챗봇")
    st.caption("YouTube 영상 자막 기반 주식 정보 및 시황 검색")

    if "rag_messages" not in st.session_state:
        st.session_state.rag_messages = []
    if "pending_followup_question" not in st.session_state:
        st.session_state.pending_followup_question = None

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


def render_tab_tech():
    st.header("📈 기술분석관 (차트 챗봇)")
    st.caption("yfinance 실시간 주가 및 차트 보조지표 분석 (예: TSLA 매수 타점 어때?)")

    if "tech_messages" not in st.session_state:
        st.session_state.tech_messages = []

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

    st.markdown("---")
    score = analysis.get("sentiment_score", 50)
    sentiment = analysis.get("sentiment", "중립")

    sc1, sc2, sc3 = st.columns(3)
    sc1.metric("감성 점수", f"{score}/100")
    sc2.metric("시장 감성", sentiment)
    sc3.metric("분석 뉴스 수", f"{analysis.get('news_count', len(news_list))}건")

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


def render_tab_entry_check():
    """🎯 진입 점검 — '이 종목 지금 사도 될까?'를 시그널 엔진으로 종합 판단."""
    st.header("🎯 진입 점검 — 지금 사도 될까?")
    st.caption("매수 전에 물어보세요. 진입 타이밍·밸류에이션·실적 엔진을 종합해 "
               "'지금 진입 / 조정 대기 / 비추천'을 판단합니다. (규칙 기반·무료)")

    from modules.portfolio_advisor import PERSONAS

    ec1, ec2, ec3 = st.columns([2, 2, 1.3])
    with ec1:
        ticker = st.text_input("티커 또는 종목명", value="", placeholder="예: NVDA, 엔비디아, 005930",
                               key="entry_ticker")
    with ec2:
        stance_label = st.selectbox("투자 성향", [v["label"] for v in PERSONAS.values()],
                                    index=3, key="entry_stance")  # 기본 전문가
        stance = next(k for k, v in PERSONAS.items() if v["label"] == stance_label)
    with ec3:
        st.write("")
        go = st.button("🔍 점검", type="primary", use_container_width=True)

    if not go:
        st.info("👆 사려는 종목을 입력하고 점검을 눌러보세요.")
        return

    if not ticker.strip():
        st.warning("종목을 입력하세요.")
        return

    from modules.issue_tracker import resolve_ticker
    from modules.trade_signal import get_market_regime, analyze_stock, decide_action, _PROFILE

    tk = resolve_ticker(ticker.strip())

    @st.cache_data(ttl=300)
    def _entry_analyze(tk_, stance_):
        regime = get_market_regime()
        analysis = analyze_stock(tk_, 0, 0)  # 신규 진입 관점 (미보유)
        if "error" in analysis:
            return {"error": analysis["error"], "regime": regime}
        decision = decide_action(analysis, stance_, regime["score_modifier"])
        return {"regime": regime, **analysis, **decision}

    with st.spinner(f"{tk} 분석 중... (시세·지표·밸류에이션)"):
        r = _entry_analyze(tk, stance)

    if r.get("error"):
        st.error(f"❌ {tk}: {r['error']} — 티커를 확인하세요.")
        return

    buy_th, strong_th, sell_th = _PROFILE.get(stance, _PROFILE["neutral"])[:3]
    score = r["adj_score"]

    # ── 결론 카드 ──
    if score >= strong_th:
        verdict, vcolor, vicon = "지금 진입 가능 (적극)", "#00FFA3", "🟢🟢"
    elif score >= buy_th:
        verdict, vcolor, vicon = "분할 진입 고려", "#1D9E75", "🟢"
    elif score <= sell_th:
        verdict, vcolor, vicon = "진입 비추천 — 지금은 피하기", "#FF4B4B", "🔴"
    else:
        verdict, vcolor, vicon = "관망 — 더 좋은 자리 대기", "#FFD700", "⚪"

    val = r.get("valuation", {})
    st.markdown(
        f"<div style='background:linear-gradient(160deg,#16202A,#16181F); "
        f"border:1px solid {vcolor}55; border-radius:14px; padding:18px 20px; margin:6px 0 14px;'>"
        f"<div style='font-size:0.8rem; color:#94A3B8;'>{tk} · {PERSONAS[stance]['label']} 관점 · "
        f"시장국면 {r['regime']['label']}</div>"
        f"<div style='font-size:1.5rem; font-weight:700; color:{vcolor}; margin:6px 0;'>{vicon} {verdict}</div>"
        f"<div style='font-size:0.85rem; color:#94A3B8;'>종합 점수 {score:+.0f} · 셋업: {r.get('setup','')}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── 3대 관점 ──
    c1, c2, c3 = st.columns(3)
    c1.metric("📈 타이밍", f"RSI {r.get('rsi','?')}",
              help=f"MACD {r.get('macd_hist','?'):.2f} · ADX {r.get('adx','?')} {r.get('trend_regime','')} · 주봉 {r.get('wk_trend','')}추세")
    vmap = {"저평가": "🟢 저평가", "적정": "🟡 적정", "고평가": "🔴 고평가", "평가불가": "⚪ 평가불가"}
    c2.metric("🏷️ 밸류에이션", vmap.get(val.get("verdict", "평가불가"), "?"),
              help=val.get("note", ""))
    eps = val.get("eps_growth")
    c3.metric("⚙️ 실적 엔진", f"EPS {eps:+.0f}%" if isinstance(eps, (int, float)) else "데이터 없음",
              help="EPS 성장 추세 — 강하면 과열에도 추세 유지 가능 (올랜도 킴식)")

    # ── 진입 플랜 ──
    if r.get("entry"):
        st.markdown("#### 🎯 진입 플랜")
        pc1, pc2, pc3, pc4 = st.columns(4)
        pc1.metric("진입가", f"{r['entry']:,.2f}")
        pc2.metric("손절가", f"{r['stop']:,.2f}", delta=f"{(r['stop']/r['entry']-1)*100:+.1f}%")
        pc3.metric("목표가", f"{r['target']:,.2f}", delta=f"{(r['target']/r['entry']-1)*100:+.1f}%")
        pc4.metric("손익비", f"1 : {r['rr']}")
    else:
        st.info(f"💡 {r.get('plan','명확한 진입 트리거가 없어 관망 구간입니다.')}")

    # ── 판단 근거 ──
    with st.expander("📋 판단 근거 상세", expanded=True):
        for pts, reason in r.get("reasons", []):
            st.markdown(f"- {pts} {reason}")
        for ex in r.get("extra", []):
            st.markdown(f"- {ex}")
        st.caption(f"지지 {r.get('support','?')} · 저항 {r.get('resistance','?')} · "
                   f"MA50 {r.get('ma50','?')} · MA200 {r.get('ma200','?')} · "
                   f"현재가 {r.get('price','?')}")

    # ── 차트 ──
    if st.toggle("📈 차트 보기 (캔들+MA+볼린저+RSI+MACD)", key="entry_chart"):
        from utils.chart_builder import build_candlestick_chart
        with st.spinner("차트 로딩..."):
            fig = build_candlestick_chart(tk, "6mo")
            if fig:
                st.plotly_chart(fig, use_container_width=True, key="entry_fig")

    st.caption("⚠️ 규칙 기반 기술·밸류 종합 신호입니다. 최신 뉴스·이벤트는 별도 확인하세요. 투자 권유가 아닙니다.")
