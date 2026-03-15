"""
Stock Agent RAG 챗봇 - Streamlit 앱 (리팩터링 버전)
Multi-Agent 시스템 with Fear & Greed Index 기반 히트맵 테마
"""
import streamlit as st
import os
import pandas as pd
import datetime
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
from agents.router import get_router
from utils.sector_classifier import SectorClassifier
from utils.portfolio_visualizer import PortfolioVisualizer
import traceback


def initialize_agents():
    """에이전트 초기화"""
    if "agents" not in st.session_state:
        st.session_state.agents = {}
        
        # 에이전트 타입별 초기화
        for agent_id, agent_info in AGENT_REGISTRY.items():
            if not agent_info.get('enabled', True):
                continue
            
            agent_type = agent_info.get('type', 'rag')
            
            if agent_type == 'rag':
                # RAG 에이전트
                st.session_state.agents[agent_id] = RAGAgent(
                    agent_id=agent_id,
                    name=agent_info['name'],
                    description=agent_info['description'],
                    channel_id=agent_info.get('channel_id')
                )
            elif agent_type == 'technical':
                # 기술적 분석 에이전트
                st.session_state.agents[agent_id] = TechnicalAgent(
                    agent_id=agent_id,
                    name=agent_info['name'],
                    description=agent_info['description']
                )
            elif agent_type == 'news':
                # 뉴스 & 감성 분석 에이전트
                st.session_state.agents[agent_id] = NewsAgent(
                    agent_id=agent_id,
                    name=agent_info['name'],
                    description=agent_info['description']
                )

    # AgenticRouter 싱글톤 초기화 (최초 1회만)
    if "agentic_router" not in st.session_state:
        with st.spinner("🔀 Agentic Router 초기화 중..."):
            st.session_state.agentic_router = get_router()


def main():
    st.set_page_config(
        page_title="Stock Agent Terminal",
        page_icon=PAGE_ICON,
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    # 0. 인증 체크 (Login)
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        render_login_page()
        st.stop()
    
    # Fear & Greed Index 가져오기 (창을 처음 열었을 때만 1회 가져와서 세션에 저장)
    if "fg_index" not in st.session_state:
        st.session_state.fg_index, st.session_state.fg_status = get_cached_fear_greed_index()
    
    fg_index = st.session_state.fg_index
    fg_status = st.session_state.fg_status
    
    # 히트맵 색상 계산
    bg_color, text_color, emoji, status_text = get_heatmap_color(fg_index)
    
    # 포인트 컬러 시스템 구축
    point_color, point_text_color = get_point_color(fg_index)
    
    # 테마 적용 (Investment Platform UI + Accent Color)
    apply_theme(bg_color, text_color, point_color)
    
    # 전략적 포인트 컬러 및 배너 스타일링
    st.markdown(f"""
    <style>
        /* 1. 상단 배너 스타일 (포인트 컬러 반영) */
        .top-announcement-bar {{
            background-color: {point_color};
            color: {point_text_color} !important;
            padding: 10px 0;
            text-align: center;
            font-weight: 700;
            font-size: 14px;
            width: 100%;
            position: fixed;
            top: 0;
            left: 0;
            z-index: 999991;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
            letter-spacing: -0.02em;
        }}
        
        /* 2. 메트릭 카드 시각 효과 (상단 악센트 라인) */
        [data-testid="stMetric"] {{
            border-top: 3px solid {point_color} !important;
        }}
        
        /* 3. 가상 유튜버 응답 강조 (Persona Accent) */
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {{
            border-left: 5px solid {point_color} !important;
        }}
        
        /* 작성자 이름 포인트 컬러 강조 */
        [data-testid="stChatMessageAvatarAssistant"] + div div {{
            color: {point_color} !important;
        }}

        /* 메인 컨텐츠 상단 여백 조절 (배너 공간 확보) */
        .main .block-container {{
            padding-top: 4rem !important;
        }}
    </style>
    """, unsafe_allow_html=True)

    # 1. 상단 티커 테이프 출력
    render_ticker_tape()
    st.divider()

    # 2. 메인 페이지 제목
    st.title(f"📊 Stock Agent Terminal")
    
    # 에이전트 초기화
    initialize_agents()
    
    # 3. 메인 레이아웃 7:3 분할
    col_main, col_side = st.columns([7, 3])
    
    # --- 🎯 우측 사이드 패널 (3 비율) : 요약 데이터 및 지표 ---
    with col_side:
        st.subheader("🌋 시장 심리 (Fear & Greed)")
        # 게이지 차트 출력
        render_fear_greed_gauge(fg_index)
        
        if fg_index is not None:
             st.info(f"**현재 상태**: {fg_status} ({status_text})")
        
        st.divider()

        # 관심 종목 미니 테이블 (Watchlist)
        st.markdown("**🔥 실시간 Watchlist**")
        
        @st.cache_data(ttl=600)
        def get_realtime_watchlist():
            from utils.price_updater import PriceUpdater
            updater = PriceUpdater()
            watch_tickers = ["NVDA", "TSLA", "AAPL", "005930.KS"]
            df_watch = updater.get_watchlist_data(watch_tickers)
            
            # 포맷팅
            if not df_watch.empty:
                df_watch['현재가'] = df_watch.apply(
                    lambda x: f"₩{x['현재가']:,.0f}" if x['종목'].endswith('.KS') or x['종목'].endswith('.KQ') or x['종목'] == '005930.KS' else f"${x['현재가']:,.2f}", 
                    axis=1
                )
            return df_watch

        with st.spinner("Watchlist 로딩 중..."):
            watch_df = get_realtime_watchlist()
            st.dataframe(watch_df, hide_index=True, use_container_width=True)
        
        st.divider()
        
        # YouTube 데이터 수집 섹션 (기존 사이드바에서 이동)
        st.subheader("⚙️ 파이프라인 관리")
        st.caption("YouTube → Pinecone 자동화")
        
        today = datetime.date.today()
        start_date = st.date_input("시작일", value=today, key="yt_start_date")
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
                    start_date_str = start_date.strftime("%Y-%m-%d")
                    end_date_str = end_date.strftime("%Y-%m-%d")
                    
                    def on_status_update(msg):
                        status_container.info(msg)
                    def on_progress_update(ratio, msg):
                        progress_container.progress(ratio, text=msg)

                    result = pipeline.run_youtube_pipeline(
                        channel_id=ORLANDO_CHANNEL_ID,
                        start_date_str=start_date_str,
                        end_date_str=end_date_str,
                        progress_callback=on_progress_update,
                        status_callback=on_status_update
                    )
                    st.success(f"수집 완료: {result.get('success_count', 0)}개")
                except Exception as e:
                    st.error(f"오류: {e}")

        if st.button("🔄 대화 초기화", icon=":material/refresh:", use_container_width=True):
            st.session_state.rag_messages = []
            st.success("대화 초기화됨")
            st.rerun()

    # --- 🎯 좌측 메인 패널 (7 비율) ---
    with col_main:
        # 탭 기반 멀티 에이전트 UI
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "🎥 영상분석관 (RAG)", 
            "📊 밸류에이션 분석관", 
            "📈 기술분석관 (차트)", 
            "💼 내 포트폴리오", 
            "🔀 종합 분석관"
        ])
    
        # ===== TAB 1: RAG 챗봇 =====
        with tab1:
            st.header("🎥 영상분석관 챗봇")
            st.caption("YouTube 영상 자막 기반 주식 정보 및 시황 검색")
            # (검색 결과 개수와 답변 창의성은 고정 설정값을 사용합니다)
            # 세션 상태 초기화 (RAG)
            if "rag_messages" not in st.session_state:
                st.session_state.rag_messages = []
            
            # 후속 질문 클릭 처리를 위한 세션 상태
            if "pending_followup_question" not in st.session_state:
                st.session_state.pending_followup_question = None
            
            # 사용자 입력 (상단에 배치)
            st.markdown("---")
            
            # 후속 질문 클릭 시 자동 입력
            if st.session_state.pending_followup_question:
                prompt = st.session_state.pending_followup_question
                st.session_state.pending_followup_question = None
            else:
                prompt = st.chat_input("질문을 입력하세요 (예: 삼성전자 전망은?)", key="rag_input")
            
            if prompt:
                # 사용자 메시지 추가
                st.session_state.rag_messages.append({"role": "user", "content": prompt})
                
                # AI 답변 생성 (AgenticRouter 경유)
                with st.spinner("🔀 라우팅 및 답변 생성 중..."):
                    try:
                        # 대화 히스토리 준비 (최근 6개 메시지만)
                        conversation_history = st.session_state.rag_messages[-6:] if st.session_state.rag_messages else None

                        # ── RAG Agent 직접 호출 ─────────────────────
                        result = st.session_state.agentic_router.rag_agent.process(
                            query=prompt,
                            conversation_history=conversation_history
                        )

                        answer = result.get('answer', '답변을 생성하지 못했습니다.')
                        sources = result.get('sources', [])
                        followup_questions = result.get('followup_questions', [])

                        answer_with_badge = answer

                        # 메시지 저장
                        st.session_state.rag_messages.append({
                            "role": "assistant",
                            "content": answer_with_badge,
                            "sources": sources,
                            "followup_questions": followup_questions
                        })

                    except Exception as e:
                        error_msg = f"오류 발생: {str(e)}\n\n```\n{traceback.format_exc()}\n```"
                        st.session_state.rag_messages.append({
                            "role": "assistant",
                            "content": error_msg
                        })
            
            # 대화 히스토리 표시 (아래에 배치, 최신순)
            st.markdown("---")
            st.subheader("💬 대화 내역")
            
            if st.session_state.rag_messages:
                # 최신 메시지가 위로 오도록 역순 정렬
                for message in reversed(st.session_state.rag_messages):
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])
                        
                        # 소스 정보 표시
                        if message["role"] == "assistant" and "sources" in message:
                            render_chat_sources(message["sources"])
                            
                            # 후속 질문 버튼 표시 (최신 메시지만)
                            if message == st.session_state.rag_messages[-1] and "followup_questions" in message and message["followup_questions"]:
                                st.markdown("")
                                st.markdown("**🔍 추가로 궁금하신 사항:**")
                                cols = st.columns(len(message["followup_questions"]))
                                for idx, (col, question) in enumerate(zip(cols, message["followup_questions"])):
                                    with col:
                                        if st.button(f"💬 {question}", key=f"followup_{idx}", use_container_width=True):
                                            st.session_state.pending_followup_question = question
                                            st.rerun()
            else:
                st.info("👆 위에서 질문을 입력하세요!")
    
        # ===== TAB 2: 밸류에이션 분석관 =====
        with tab2:
            st.header("📊 밸류에이션 분석관")
            st.caption("보수적인 퀀트 애널리스트 - 적정가 밴드 & 관심 매수 구간을 알아서 판단해 드립니다.")
            
            # 세션 상태 초기화 (Quant Analyst)
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
            
            quant_prompt = st.chat_input("티커와 함께 분석을 요청하세요 (예: 테슬라 DCF 밸류에이션 해봐, NVDA 적정가 얼마야?)", key="quant_input")
            
            if quant_prompt:
                # 사용자 메시지 추가
                st.session_state.quant_messages.append({"role": "user", "content": quant_prompt})
                
                with st.spinner("📊 최적의 모델로 밸류에이션 계산 중..."):
                    try:
                        # 퀀트 분석 처리 (QuantAnalyst process 직접 호출)
                        result = st.session_state.quant_analyst.process(
                            query=quant_prompt
                        )
                        
                        if result.get("success"):
                            answer = result.get("analysis", "분석을 완료하지 못했습니다.")
                            stock_info = result.get("stock_data", {})
                            
                            if stock_info and not stock_info.get("error"):
                                meta_info = f"\n\n---\n**[수집된 실시간 데이터]**\n"
                                meta_info += f"- **종목명:** {stock_info.get('company_name')} ({stock_info.get('ticker')})\n"
                                meta_info += f"- **현재 가격:** ${stock_info.get('price')}\n"
                                meta_info += f"- **EPS (TTM):** ${stock_info.get('eps_ttm', 'N/A')} | **EPS (FY1):** ${stock_info.get('eps_fy1', 'N/A')}\n"
                                meta_info += f"- **P/E:** {stock_info.get('pe_ratio', 'N/A')}배\n"
                                answer += meta_info
                        else:
                            answer = f"⚠️ 분석 실패: {result.get('error', '알 수 없는 오류')}"
                            
                        st.session_state.quant_messages.append({
                            "role": "assistant",
                            "content": answer
                        })
                    except Exception as e:
                        import traceback
                        st.session_state.quant_messages.append({
                            "role": "assistant",
                            "content": f"오류 발생: {str(e)}\n\n```\n{traceback.format_exc()}\n```"
                        })
            
            # 대화 히스토리 표시
            st.markdown("---")
            st.subheader("💬 대화 내역")
            
            if st.session_state.quant_messages:
                for message in reversed(st.session_state.quant_messages):
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])
            else:
                st.info("👆 위에서 종목명/티커와 함께 분석을 요청하세요! (알아서 적합한 모델을 선택합니다)")
    
        # ===== TAB 3: 기술분석관 =====
        with tab3:
            st.header("📈 기술분석관 (차트 챗봇)")
            st.caption("yfinance 실시간 주가 및 차트 보조지표 분석 (예: TSLA 매수 타점 어때?)")
            
            # 세션 상태 초기화 (Tech)
            if "tech_messages" not in st.session_state:
                st.session_state.tech_messages = []
                
            st.markdown("---")
            
            tech_prompt = st.chat_input("종목명이나 티커와 함께 질문을 입력하세요 (예: 엔비디아 차트 분석해줘)", key="tech_input")
            
            if tech_prompt:
                # 사용자 메시지 추가
                st.session_state.tech_messages.append({"role": "user", "content": tech_prompt})
                
                with st.spinner("📈 차트 데이터 불러오는 중..."):
                    try:
                        # 기술 분석 처리 (TechnicalAgent 직접 호출)
                        result = st.session_state.agentic_router.tech_agent.process(
                            query=tech_prompt
                        )
                        
                        if result.get("indicators") and "error" not in result.get("indicators", {}):
                            answer = result.get("analysis", "분석을 완료하지 못했습니다.")
                            ind = result["indicators"]
                            ticker = ind.get('ticker', 'UNKNOWN')
                            answer += f"\n\n---\n**[{ticker}] 주요 지표 요약**\n"
                            answer += f"- **현재가:** ${ind.get('current_price')} (1일 변동: {ind.get('price_change_1d')}%)\n"
                            answer += f"- **추세 (이동평균선):** {ind.get('trend')} (MA20: ${ind.get('ma20')}, MA50: ${ind.get('ma50')})\n"
                            answer += f"- **RSI (14일):** {ind.get('rsi')} ➜ **{ind.get('rsi_signal')}**\n"
                            answer += f"- **MACD:** {ind.get('macd')} ➜ **{ind.get('macd_trend')} 추세**\n"
                            answer += f"- **볼린저 밴드 위치:** {ind.get('bb_position')}%\n"
                        else:
                            answer = f"⚠️ 분석 실패: {result.get('error', result.get('indicators', {}).get('error', '알 수 없는 오류'))}"
                            
                        st.session_state.tech_messages.append({
                            "role": "assistant",
                            "content": answer
                        })
                    except Exception as e:
                        import traceback
                        st.session_state.tech_messages.append({
                            "role": "assistant",
                            "content": f"오류 발생: {str(e)}\n\n```\n{traceback.format_exc()}\n```"
                        })
            
            # 대화 히스토리 표시
            st.markdown("---")
            st.subheader("💬 대화 내역")
            
            if st.session_state.tech_messages:
                for message in reversed(st.session_state.tech_messages):
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])
            else:
                st.info("👆 위에서 종목명/티커와 함께 질문을 입력하세요!")

        # ===== TAB 4: 내 포트폴리오 =====
        with tab4:
            st.header("💼 내 포트폴리오")
            st.caption("로컬 데이터 기반 보유 주식 분석 (data/portfolio.csv 파일을 수정하세요)")
            
            # 세션 상태 초기화
            if "portfolio_data" not in st.session_state:
                st.session_state.portfolio_data = None
            
            # 데이터 파일 경로
            PORTFOLIO_FILE = "data/portfolio.csv"
            
            # 포트폴리오 로드 및 관리 섹션
            st.subheader("📊 포트폴리오 관리")
            
            if not os.path.exists(PORTFOLIO_FILE):
                st.error(f"⚠️ `{PORTFOLIO_FILE}` 파일을 찾을 수 없습니다.")
                if st.button("📁 샘플 파일 생성"):
                    os.makedirs("data", exist_ok=True)
                    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
                        f.write("ticker,name,quantity,avg_price,current_price\n")
                        f.write("TSLA,테슬라,10,200,250\n")
                        f.write("NVDA,엔비디아,2,400,600\n")
                    st.success("✅ 샘플 파일이 생성되었습니다!")
                    st.rerun()
                st.stop()
                
            # 데이터 로드
            if "df_portfolio" not in st.session_state or st.session_state.get("reload_csv", False):
                st.session_state.df_portfolio = pd.read_csv(PORTFOLIO_FILE)
                st.session_state.reload_csv = False

            # 포트폴리오 편집기
            st.info("💡 아래 표에서 직접 종목 정보를 수정하고 **'변경사항 저장'**을 누르세요.")
            edited_df = st.data_editor(
                st.session_state.df_portfolio,
                num_rows="dynamic",
                use_container_width=True,
                key="portfolio_editor",
                column_config={
                    "ticker": st.column_config.TextColumn("티커", help="예: AAPL, 005930.KS"),
                    "name": st.column_config.TextColumn("종목명"),
                    "quantity": st.column_config.NumberColumn("수량", min_value=0),
                    "avg_price": st.column_config.NumberColumn("평단가", min_value=0, format="$%.2f"),
                    "current_price": st.column_config.NumberColumn("현재가", min_value=0, format="$%.2f"),
                }
            )

            col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
            with col1:
                if st.button("💾 변경사항 저장", use_container_width=True, type="primary"):
                    edited_df.to_csv(PORTFOLIO_FILE, index=False)
                    st.session_state.df_portfolio = edited_df
                    st.success("✅ `portfolio.csv`에 저장되었습니다!")
            with col2:
                if st.button("🔄 데이터 불러오기", use_container_width=True):
                    st.session_state.reload_csv = True
                    st.rerun()
            with col3:
                # 실시간 가격 업데이트 버튼
                if st.button("📡 가격 업데이트", use_container_width=True, help="yfinance로 실시간 가격 업데이트"):
                    with st.spinner("가격 업데이트 중..."):
                        try:
                            from utils.price_updater import PriceUpdater
                            
                            updater = PriceUpdater()
                            updated_df = updater.update_portfolio_prices(edited_df, delay_seconds=0.3)
                            
                            # 저장
                            updater.save_portfolio(updated_df, PORTFOLIO_FILE)
                            st.session_state.df_portfolio = updated_df
                            st.session_state.reload_csv = True
                            st.success("✅ 가격 업데이트 완료!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ 가격 업데이트 실패: {str(e)}")
            with col4:
                # 분석 실행 버튼
                if st.button("🚀 분석 실행", type="secondary", use_container_width=True):
                    with st.spinner("포트폴리오 분석 중..."):
                        try:
                            from modules.portfolio_analyzer import PortfolioAnalyzer
                            from core.rag_engine import RAGEngine
                            
                            # RAG 엔진 초기화
                            rag_engine = RAGEngine()
                            
                            # 포트폴리오 분석기 생성 (수정된 데이터 사용)
                            analyzer = PortfolioAnalyzer(rag_engine)
                            
                            if not edited_df.empty:
                                # 분석 시에는 계산된 컬럼이 필요하므로 내부 로직 태움
                                # load_portfolio_from_csv의 계산 로직을 수동으로 적용
                                df_for_analysis = edited_df.copy()
                                df_for_analysis['eval_amount'] = df_for_analysis['quantity'] * df_for_analysis['current_price']
                                df_for_analysis['profit_loss'] = df_for_analysis['eval_amount'] - (df_for_analysis['quantity'] * df_for_analysis['avg_price'])
                                df_for_analysis['profit_rate'] = (df_for_analysis['profit_loss'] / (df_for_analysis['quantity'] * df_for_analysis['avg_price'])) * 100
                                df_for_analysis['profit_rate'] = df_for_analysis['profit_rate'].fillna(0)
                                
                                result = analyzer.analyze_portfolio(df_for_analysis)
                                
                                if result['status'] == 'success':
                                    st.session_state.portfolio_data = result
                                    st.success("✅ 분석 완료!")
                                else:
                                    st.error(f"❌ 분석 실패: {result.get('message', '알 수 없는 오류')}")
                            else:
                                st.warning("⚠️ 포트폴리오 데이터가 비어 있습니다.")
                        
                        except Exception as e:
                            st.error(f"❌ 오류 발생: {str(e)}")
            
            # 포트폴리오 데이터 표시
            if st.session_state.portfolio_data:
                data = st.session_state.portfolio_data
                
                st.markdown("---")
                st.subheader("📈 포트폴리오 요약")
                
                # 요약 정보 표시
                summary = data.get('summary', {})
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("보유 종목 수", f"{summary.get('total_stocks', 0)}개")
                with col2:
                    total_eval = summary.get('total_evaluation', 0)
                    st.metric("총 평가액", f"₩{total_eval:,.0f}")
                with col3:
                    total_profit = summary.get('total_profit_loss', 0)
                    st.metric("총 평가손익", f"₩{total_profit:,.0f}")
                with col4:
                    avg_rate = summary.get('average_profit_rate', 0)
                    st.metric("평균 수익률", f"{avg_rate:.2f}%")
                
                col5, col6 = st.columns(2)
                with col5:
                    top = summary.get('top_performer', {})
                    st.success(f"🏆 최고 수익: {top.get('name', 'N/A')} ({top.get('profit_rate', 0):.2f}%)")
                with col6:
                    worst = summary.get('worst_performer', {})
                    st.error(f"📉 최저 수익: {worst.get('name', 'N/A')} ({worst.get('profit_rate', 0):.2f}%)")
                
                # 알림 및 리밸런싱 탭
                st.markdown("---")
                subtab1, subtab2, subtab3, subtab4, subtab5 = st.tabs(["📋 종목 상세", "📊 시각화", "🔔 알림", "⚖️ 리밸런싱", "💬 개인화 챗봇"])
                
                # 서브탭 1: 종목 상세 (기존)
                with subtab1:
                    st.subheader("📋 보유 종목 상세")
                    
                    # 종목별 분석 결과
                    for analysis in data.get('stock_analyses', []):
                        with st.expander(f"**{analysis['name']}** ({analysis['ticker']})", expanded=False):
                            # 현재 정보
                            info = analysis.get('current_info', {})
                            ticker_str = analysis['ticker']
                            
                            # 통화 기호 결정
                            if ticker_str.endswith('.KS') or ticker_str.endswith('.KQ'): symbol = '₩'
                            elif ticker_str.endswith('.T'): symbol = '¥'
                            elif ticker_str == 'USD': symbol = '₩' # 환율이므로 원화
                            else: symbol = '$'
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("보유 수량", f"{info.get('quantity', 0):,}주")
                                st.metric("평균 매수가 (KRW)", f"₩{info.get('avg_price', 0):,.0f}") # avg_price는 KRW로 관리됨
                            with col2:
                                st.metric("현재가 (Native)", f"{symbol}{info.get('current_price', 0):,.2f}")
                                st.metric("평가금액 (KRW)", f"₩{info.get('quantity', 0) * info.get('current_price_krw', info.get('current_price', 0)):,.0f}")
                            with col3:
                                profit_loss = info.get('profit_loss', 0)
                                profit_rate = info.get('profit_rate', 0)
                                st.metric(
                                    "평가손익 (KRW)", 
                                    f"₩{profit_loss:,.0f}",
                                    delta=f"{profit_rate:.2f}%"
                                )
                            
                            st.markdown("---")
                            
                            # AI 피드백
                            st.markdown("### 🤖 AI 투자 피드백")
                            feedback = analysis.get('ai_feedback', '')
                            if feedback:
                                st.markdown(feedback)
                            else:
                                st.info("AI 피드백을 생성할 수 없습니다.")
                            
                            # RAG 검색 결과
                            rag_insights = analysis.get('rag_insights', [])
                            if rag_insights:
                                st.markdown("### 📺 관련 YouTube 분석")
                                for idx, insight in enumerate(rag_insights[:3], 1):
                                    meta = insight.get('metadata', {})
                                    st.markdown(f"""
                                    **{idx}. {meta.get('영상제목', 'N/A')}**  
                                    채널: {meta.get('채널명', 'N/A')} | 업로드: {meta.get('업로드일자', 'N/A')}  
                                    [영상 보기]({meta.get('영상링크', '#')})
                                    """)
            
                # 서브탭 2: 시각화
                with subtab2:
                    st.subheader("📊 포트폴리오 시각화 분석")
                    
                    with st.spinner("섹터 분류 및 시각화 준비 중..."):
                        try:
                            # 1. 섹터 분류
                            classifier = SectorClassifier()
                            df_for_viz = edited_df.copy()
                            # 계산된 컬럼 추가 (시각화에 필수)
                            df_for_viz['eval_amount'] = df_for_viz['quantity'] * df_for_viz['current_price']
                            df_for_viz['profit_loss'] = df_for_viz['eval_amount'] - (df_for_viz['quantity'] * df_for_viz['avg_price'])
                            df_for_viz['profit_rate'] = (df_for_viz['profit_loss'] / (df_for_viz['quantity'] * df_for_viz['avg_price'])) * 100
                            df_for_viz['profit_rate'] = df_for_viz['profit_rate'].fillna(0)
                        
                            df_classified = classifier.classify_portfolio(df_for_viz, delay_seconds=0.1)
                            sector_summary = classifier.get_sector_summary(df_classified)
                            
                            # 2. 시각화 객체 초기화
                            visualizer = PortfolioVisualizer()
                            
                            # 차트 표시 (2열 배치)
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                # 섹터 비중 파이 차트
                                fig_pie = visualizer.create_sector_pie_chart(df_classified, sector_summary)
                                st.plotly_chart(fig_pie, use_container_width=True)
                            
                            with col2:
                                # 종목별 수익률 막대 차트
                                fig_bar = visualizer.create_profit_bar_chart(df_classified)
                                st.plotly_chart(fig_bar, use_container_width=True)
                            
                            st.markdown("---")
                            
                            # 트리맵: 비중과 수익률을 한눈에
                            fig_tree = visualizer.create_treemap(df_classified)
                            st.plotly_chart(fig_tree, use_container_width=True)
                            
                            st.markdown("---")
                            
                            # 추가 분석 (선버스트 & 섹터 성과)
                            col3, col4 = st.columns(2)
                            with col3:
                                fig_sun = visualizer.create_allocation_sunburst(df_classified)
                                st.plotly_chart(fig_sun, use_container_width=True)
                            with col4:
                                fig_perf = visualizer.create_sector_performance_chart(df_classified, sector_summary)
                                st.plotly_chart(fig_perf, use_container_width=True)
                                
                        except Exception as e:
                            st.error(f"❌ 시각화 생성 실패: {str(e)}")
                            st.code(traceback.format_exc())

                # 서브탭 3: 알림
                with subtab3:
                    st.subheader("🔔 포트폴리오 알림")
                    
                    if st.button("🔍 알림 확인", use_container_width=True):
                        with st.spinner("알림 확인 중..."):
                            try:
                                from modules.portfolio_alert import PortfolioAlert
                                from core.rag_engine import RAGEngine
                                
                                rag_engine = RAGEngine()
                                alert_system = PortfolioAlert(rag_engine)
                                
                                # 포트폴리오 데이터프레임 준비
                                df_for_alert = edited_df.copy()
                                df_for_alert['eval_amount'] = df_for_alert['quantity'] * df_for_alert['current_price']
                                df_for_alert['profit_loss'] = df_for_alert['eval_amount'] - (df_for_alert['quantity'] * df_for_alert['avg_price'])
                                df_for_alert['profit_rate'] = (df_for_alert['profit_loss'] / (df_for_alert['quantity'] * df_for_alert['avg_price'])) * 100
                                df_for_alert['profit_rate'] = df_for_alert['profit_rate'].fillna(0)
                                
                                alerts = alert_system.check_portfolio_alerts(df_for_alert, days_back=7)
                                formatted_alerts = alert_system.format_alerts(alerts)
                                
                                st.markdown(formatted_alerts)
                                
                            except Exception as e:
                                st.error(f"❌ 알림 확인 실패: {str(e)}")
                
                # 서브탭 4: 리밸런싱
                with subtab4:
                    st.subheader("⚖️ 포트폴리오 리밸런싱 제안")
                    
                    if st.button("📊 리밸런싱 분석", use_container_width=True):
                        with st.spinner("리밸런싱 분석 중..."):
                            try:
                                from modules.portfolio_rebalancer import PortfolioRebalancer
                                from core.rag_engine import RAGEngine
                                
                                rag_engine = RAGEngine()
                                rebalancer = PortfolioRebalancer(rag_engine)
                                
                                # 포트폴리오 데이터프레임 준비
                                df_for_rebal = edited_df.copy()
                                df_for_rebal['eval_amount'] = df_for_rebal['quantity'] * df_for_rebal['current_price']
                                df_for_rebal['profit_loss'] = df_for_rebal['eval_amount'] - (df_for_rebal['quantity'] * df_for_rebal['avg_price'])
                                df_for_rebal['profit_rate'] = (df_for_rebal['profit_loss'] / (df_for_rebal['quantity'] * df_for_rebal['avg_price'])) * 100
                                df_for_rebal['profit_rate'] = df_for_rebal['profit_rate'].fillna(0)
                                
                                result = rebalancer.generate_rebalancing_suggestions(df_for_rebal)
                                
                                if result['status'] == 'success':
                                    # 탭 구성: 분석 결과 / 최적화 차트 / 시뮬레이션
                                    rebal_tab1, rebal_tab2, rebal_tab3 = st.tabs(["📊 분석 결과", "📈 효율적 투자선", "💰 비용 시뮬레이션"])
                                    
                                    balance = result['current_balance']
                                
                                    # 1. 분석 결과 탭
                                    with rebal_tab1:
                                        # 현재 균형 표시
                                        st.markdown("### 📊 현재 포트폴리오 균형")
                                        
                                        col1, col2, col3 = st.columns(3)
                                        with col1:
                                            st.metric("총 평가금액", f"${balance['total_value']:,.0f}")
                                        with col2:
                                            st.metric("평균 수익률", f"{balance['risk_metrics']['avg_profit_rate']:.2f}%")
                                        with col3:
                                            st.metric("손실 종목 비율", f"{balance['risk_metrics']['losing_stocks_ratio']:.1f}%")
                                        
                                        # 섹터별 비중
                                        st.markdown("#### 섹터별 비중")
                                        sector_data = pd.DataFrame([
                                            {"섹터": sector, "비중 (%)": weight}
                                            for sector, weight in balance['sector_weights'].items()
                                        ])
                                        st.bar_chart(sector_data.set_index("섹터"))
                                        
                                        # 리밸런싱 제안
                                        st.markdown("---")
                                        st.markdown("### 💡 리밸런싱 제안")
                                        st.markdown(result['suggestions']['full_text'])

                                    # 2. 효율적 투자선 탭 (Plotly)
                                    with rebal_tab2:
                                        st.subheader("📈 Efficient Frontier (효율적 투자선)")
                                        
                                        opt_result = result.get('optimization', {})
                                        if opt_result.get('success'):
                                            import plotly.graph_objects as go
                                            
                                            frontier = opt_result['frontier']
                                            curr = opt_result['current_metrics']
                                            
                                            # 산점도 (시뮬레이션 점들)
                                            fig = go.Figure()
                                            
                                            fig.add_trace(go.Scatter(
                                                x=frontier['Volatility'],
                                                y=frontier['Returns'],
                                                mode='markers',
                                                marker=dict(
                                                    color=frontier['Sharpe'],
                                                    colorscale='Viridis',
                                                    showscale=True,
                                                    colorbar=dict(title="Sharpe Ratio"),
                                                    size=5
                                                ),
                                                name='Simulation'
                                            ))
                                            
                                            # 최적점 (Max Sharpe)
                                            fig.add_trace(go.Scatter(
                                                x=[opt_result['volatility']],
                                                y=[opt_result['returns']],
                                                mode='markers',
                                                marker=dict(color='red', size=15, symbol='star'),
                                                name='Max Sharpe'
                                            ))
                                            
                                            # 내 포트폴리오
                                            fig.add_trace(go.Scatter(
                                                x=[curr['volatility']],
                                                y=[curr['returns']],
                                                mode='markers',
                                                marker=dict(color='blue', size=15, symbol='diamond'),
                                                name='My Portfolio'
                                            ))
                                            
                                            fig.update_layout(
                                                title="Risk vs Return Profile",
                                                xaxis_title="Volatility (Risk)",
                                                yaxis_title="Expected Annual Return",
                                                height=500
                                            )
                                            
                                            st.plotly_chart(fig, use_container_width=True)
                                            
                                            st.info(f"""
                                            **내 포트폴리오**: 수익률 {curr['returns']*100:.1f}%, 변동성 {curr['volatility']*100:.1f}%, Sharpe {curr['sharpe_ratio']:.2f}
                                            **최적 포트폴리오**: 수익률 {opt_result['returns']*100:.1f}%, 변동성 {opt_result['volatility']*100:.1f}%, Sharpe {opt_result['sharpe_ratio']:.2f}
                                            """)
                                        else:
                                            st.warning("최적화 데이터를 불러올 수 없습니다.")

                                    # 3. 비용 시뮬레이션 탭
                                    with rebal_tab3:
                                        st.subheader("💰 리밸런싱 비용 시뮬레이션")
                                        
                                        sim_result = result.get('simulation', {})
                                        if sim_result:
                                            col1, col2 = st.columns(2)
                                            with col1:
                                                st.metric("예상 총 비용 (수수료+세금)", f"{sim_result['total_cost']:,.0f}원")
                                            with col2:
                                                st.metric("비용 비율", f"{sim_result['cost_ratio']:.2f}%")
                                        
                                            st.markdown("#### 📋 상세 거래 내역")
                                            details = pd.DataFrame(sim_result['details'])
                                            if not details.empty:
                                                st.dataframe(
                                                    details[['ticker', 'action', 'diff', 'cost']].style.format({
                                                        'diff': '{:,.0f}',
                                                        'cost': '{:,.0f}'
                                                    })
                                                )
                                            else:
                                                st.info("리밸런싱이 필요하지 않습니다.")
                                        else:
                                            st.info("시뮬레이션 결과가 없습니다.")

                                else:
                                    st.error(f"❌ 리밸런싱 분석 실패: {result.get('message', '알 수 없는 오류')}")
                                    
                            except Exception as e:
                                st.error(f"❌ 리밸런싱 분석 실패: {str(e)}")
            
                # 서브탭 5: 개인화 챗봇
                with subtab5:
                    st.subheader("💬 개인화 투자 조언 챗봇")
                    st.caption("보유 종목 정보를 활용한 맞춤형 투자 조언")
                    
                    # 세션 상태 초기화
                    if "personalized_rag_messages" not in st.session_state:
                        st.session_state.personalized_rag_messages = []
                    
                    # 개인화 RAG 초기화
                    if "personalized_rag_engine" not in st.session_state:
                        try:
                            from core.personalized_rag import PersonalizedRAG
                            from core.rag_engine import RAGEngine
                            
                            base_rag = RAGEngine()
                            st.session_state.personalized_rag_engine = PersonalizedRAG(base_rag)
                        except Exception as e:
                            st.error(f"개인화 RAG 초기화 실패: {str(e)}")
                    
                    # 채팅 입력
                    user_query = st.chat_input("질문을 입력하세요 (예: 내가 보유한 AI 종목들 어때?)", key="personalized_rag_input")
                    
                    if user_query:
                        # 사용자 메시지 추가
                        st.session_state.personalized_rag_messages.append({"role": "user", "content": user_query})
                        
                        # AI 답변 생성
                        with st.spinner("답변 생성 중..."):
                            try:
                                # 대화 히스토리 준비
                                conversation_history = st.session_state.personalized_rag_messages[-6:] if len(st.session_state.personalized_rag_messages) > 0 else None
                                
                                result = st.session_state.personalized_rag_engine.chat(
                                    query=user_query,
                                    top_k=10,
                                    temperature=0.7,
                                    conversation_history=conversation_history,
                                    use_portfolio_context=True
                                )
                                
                                # 메시지 저장
                                st.session_state.personalized_rag_messages.append({
                                    "role": "assistant",
                                    "content": result['answer'],
                                    "sources": result.get('sources', []),
                                    "related_holdings": result.get('related_holdings', []),
                                    "followup_questions": result.get('followup_questions', [])
                                })
                                
                            except Exception as e:
                                error_msg = f"오류 발생: {str(e)}"
                                st.session_state.personalized_rag_messages.append({
                                    "role": "assistant",
                                    "content": error_msg
                                })
                    
                    # 대화 히스토리 표시
                    if st.session_state.personalized_rag_messages:
                        for message in reversed(st.session_state.personalized_rag_messages):
                            with st.chat_message(message["role"]):
                                st.markdown(message["content"])
                                
                                # 관련 보유 종목 표시
                                if message["role"] == "assistant" and "related_holdings" in message and message["related_holdings"]:
                                    with st.expander("💼 관련 보유 종목"):
                                        for stock in message["related_holdings"]:
                                            col1, col2, col3 = st.columns(3)
                                            col1.write(f"**{stock['name']}** ({stock['ticker']})")
                                            col2.write(f"{stock['quantity']:,}주")
                                            col3.write(f"{stock['profit_rate']:.1f}%")
                                
                                # 소스 정보 표시
                                if message["role"] == "assistant" and "sources" in message and message["sources"]:
                                    render_chat_sources(message["sources"])
                    else:
                        st.info("👆 위에서 질문을 입력하세요!")
                    
                    # 대화 초기화 버튼
                    if st.button("🔄 대화 초기화", key="personalized_rag_reset"):
                        st.session_state.personalized_rag_messages = []
                        st.rerun()

        # ===== TAB 5: 🔀 종합 분석관 =====
        with tab5:
            st.header("🔀 종합 분석관")
            st.caption("원하는 에이전트들을 선택하여 한 번에 종합 리뷰를 받으세요.")
            
            if "comprehensive_messages" not in st.session_state:
                st.session_state.comprehensive_messages = []

            st.markdown("---")
            st.subheader("🤖 투입할 에이전트 선택")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                use_rag = st.checkbox("🎥 영상분석 (유튜버 인사이트)", value=True, help="RAG 시스템을 통해 유튜버들의 의견과 시황을 종합합니다.")
            with col2:
                use_quant = st.checkbox("📊 가치평가 (퀀트/밸류에이션)", value=True, help="yfinance 기본 데이터를 기반으로 보수적 적정가를 산출합니다.")
            with col3:
                use_tech = st.checkbox("📈 기술적 분석 (차트/지표)", value=True, help="이평선, RSI, MACD 등 실시간 보조지표를 분석합니다.")

            st.markdown("---")
            
            comp_prompt = st.chat_input("종목명과 질문을 입력하세요 (예: 엔비디아 지금 사도 돼?)", key="comp_input")
            
            if comp_prompt:
                force_agents = []
                if use_rag: force_agents.append("rag")
                if use_quant: force_agents.append("quant")
                if use_tech: force_agents.append("tech")
                
                if not force_agents:
                    st.warning("⚠️ 최소 1개 이상의 에이전트를 선택해주세요.")
                else:
                    st.session_state.comprehensive_messages.append({"role": "user", "content": comp_prompt})
                    
                    with st.spinner("🔀 선택된 에이전트들이 동시 분석 중..."):
                        try:
                            result = st.session_state.agentic_router.route(
                                query=comp_prompt,
                                force_agents=force_agents
                            )
                            
                            answer = result.get('answer', '답변을 생성하지 못했습니다.')
                            sources = result.get('sources', [])
                            route_used = result.get('route', '')
                            
                            agent_tags = []
                            if use_rag: agent_tags.append("🎥영상분석")
                            if use_quant: agent_tags.append("📊가치평가")
                            if use_tech: agent_tags.append("📈기술적분석")
                            
                            route_info = f"\n\n---\n*⚙️ 참여 에이전트: **{' + '.join(agent_tags)}***"
                            answer_with_badge = answer + route_info
                            
                            st.session_state.comprehensive_messages.append({
                                "role": "assistant",
                                "content": answer_with_badge,
                                "sources": sources
                            })
                        except Exception as e:
                            import traceback
                            st.session_state.comprehensive_messages.append({
                                "role": "assistant",
                                "content": f"오류 발생: {str(e)}\n\n```\n{traceback.format_exc()}\n```"
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


if __name__ == "__main__":
    main()
