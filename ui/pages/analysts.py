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
