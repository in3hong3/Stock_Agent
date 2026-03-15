"""
Stock Bot RAG 챗봇 - Streamlit 앱 (리팩터링 버전)
Multi-Agent 시스템 with Fear & Greed Index 기반 히트맵 테마
"""
import streamlit as st
from config.settings import PAGE_TITLE, PAGE_ICON, AGENT_REGISTRY
from ui.theme import get_cached_fear_greed_index, get_heatmap_color, apply_theme
from ui.components import render_agent_selector, render_market_summary, render_chat_sources
from agents.rag_agent import RAGAgent
from agents.quant_agent import QuantAnalyst


def initialize_agents():
    """에이전트 초기화"""
    if "agents" not in st.session_state:
        st.session_state.agents = {}
        
        # RAG 에이전트 초기화
        for agent_id, agent_info in AGENT_REGISTRY.items():
            if agent_info.get('enabled', True):
                st.session_state.agents[agent_id] = RAGAgent(
                    agent_id=agent_id,
                    name=agent_info['name'],
                    description=agent_info['description'],
                    channel_id=agent_info.get('channel_id')
                )


def main():
    st.set_page_config(
        page_title=PAGE_TITLE,
        page_icon=PAGE_ICON,
        layout="wide"
    )
    
    # Fear & Greed Index 가져오기 (캐싱됨)
    fg_index, fg_status = get_cached_fear_greed_index()
    
    # 히트맵 색상 계산
    bg_color, text_color, emoji, status_text = get_heatmap_color(fg_index)
    
    # 테마 적용
    apply_theme(bg_color, text_color)
    
    # 헤더
    st.title(f"{PAGE_ICON} Stock Bot - Multi-Agent System")
    
    # Fear & Greed Index 표시
    if fg_index is not None:
        st.markdown(f"""
        ### {emoji} CNN Fear & Greed Index: **{fg_index}** ({fg_status})
        **상태**: {status_text}
        """)
    else:
        st.markdown("### ⚪ CNN Fear & Greed Index: 데이터 없음")
    
    st.markdown("---")
    
    # 에이전트 초기화
    initialize_agents()
    
    # 에이전트 선택 UI (메인 화면)
    selected_agent_ids = render_agent_selector()
    
    st.markdown("---")
    
    # 사이드바
    with st.sidebar:
        st.header("⚙️ 설정")
        
        # 시장 상태 요약
        render_market_summary()
        
        st.markdown("---")
        st.caption("💡 RAG 챗봇 또는 밸류에이션 분석을 선택하세요")
    
    # 탭 기반 멀티 에이전트 UI
    tab1, tab2 = st.tabs(["💬 RAG 챗봇", "📊 밸류에이션 분석"])
    
    # ===== TAB 1: RAG 챗봇 =====
    with tab1:
        st.header("💬 RAG 챗봇")
        st.caption("YouTube 영상 자막 기반 주식 정보 검색")
        
        # RAG 설정
        col1, col2 = st.columns(2)
        with col1:
            top_k = st.slider("검색 결과 개수", 1, 15, 8, key="rag_top_k")
        with col2:
            temperature = st.slider("답변 창의성", 0.0, 1.0, 0.3, 0.1, key="rag_temp")
        
        # 세션 상태 초기화 (RAG)
        if "rag_messages" not in st.session_state:
            st.session_state.rag_messages = []
        
        # 사용자 입력 (상단에 배치)
        st.markdown("---")
        prompt = st.chat_input("질문을 입력하세요 (예: 삼성전자 전망은?)", key="rag_input")
        
        if prompt:
            # 사용자 메시지 추가
            st.session_state.rag_messages.append({"role": "user", "content": prompt})
            
            # AI 답변 생성
            with st.spinner("답변 생성 중..."):
                try:
                    # 선택된 에이전트 중 첫 번째 에이전트 사용 (또는 통합 검색)
                    if selected_agent_ids and selected_agent_ids[0] in st.session_state.agents:
                        agent = st.session_state.agents[selected_agent_ids[0]]
                        result = agent.process(
                            query=prompt,
                            top_k=top_k,
                            temperature=temperature,
                            agent_filter=selected_agent_ids  # 선택된 에이전트로 필터링
                        )
                    else:
                        # 기본 RAG 엔진 사용 (모든 에이전트)
                        from core.rag_engine import RAGEngine
                        engine = RAGEngine()
                        result = engine.chat(
                            query=prompt,
                            top_k=top_k,
                            temperature=temperature,
                            agent_filter=None  # 전체 검색
                        )
                    
                    answer = result['answer']
                    sources = result['sources']
                    
                    # 메시지 저장
                    st.session_state.rag_messages.append({
                        "role": "assistant",
                        "content": answer,
                        "sources": sources
                    })
                    
                except Exception as e:
                    error_msg = f"오류 발생: {str(e)}"
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
        else:
            st.info("👆 위에서 질문을 입력하세요!")
    
    # ===== TAB 2: 밸류에이션 분석 =====
    with tab2:
        st.header("📊 밸류에이션 분석")
        st.caption("보수적인 퀀트 애널리스트 - 적정가 밴드 & 관심 매수 구간 계산")
        
        # 세션 상태 초기화 (Quant Analyst)
        if "quant_analyst" not in st.session_state:
            with st.spinner("Quant Analyst 초기화 중..."):
                try:
                    st.session_state.quant_analyst = QuantAnalyst()
                except Exception as e:
                    st.error(f"Quant Analyst 초기화 실패: {e}")
                    st.stop()
        
        if "quant_history" not in st.session_state:
            st.session_state.quant_history = []
        
        # 입력 폼
        st.subheader("🔢 종목 정보 입력")
        
        ticker = st.text_input(
            "종목 티커를 입력하세요 (예: TSLA, AAPL, NVDA, GOOGL)",
            value="",
            placeholder="TSLA",
            key="quant_ticker",
            help="미국 주식: TSLA, AAPL, NVDA, GOOGL 등"
        ).upper().strip()
        
        # 밸류에이션 방법 선택
        st.markdown("---")
        st.subheader("📐 밸류에이션 방법 선택")
        
        valuation_method = st.radio(
            "분석 방법을 선택하세요",
            options=["P/E (주가수익비율)", "DCF (현금흐름 할인)", "SOTP (사업부문별 합산)"],
            index=0,
            horizontal=True,
            help="P/E: 안정적 기업 | DCF: 성장주/적자 기업 | SOTP: 복합 기업"
        )
        
        # 현재가 입력 (공통)
        manual_price = st.number_input(
            "현재가 ($)",
            min_value=0.0,
            value=None,
            step=1.0,
            placeholder="자동 수집 (비워두면 yfinance에서 가져옴)",
            help="수동 입력하거나 비워두면 자동으로 가져옵니다"
        )
        
        # 방법별 동적 입력 필드 (기존 app.py와 동일)
        if "P/E" in valuation_method:
            st.markdown("#### P/E 방식 파라미터")
            
            col1, col2 = st.columns(2)
            with col1:
                manual_eps_ttm = st.number_input("EPS (TTM) ($)", value=None, step=0.1, placeholder="자동 수집")
                manual_eps_fy1 = st.number_input("EPS (FY1 예상) ($)", value=None, step=0.1, placeholder="자동 수집")
            with col2:
                theme = st.text_input("테마/비교군", value="", placeholder="예: Big Tech")
                theme_pe = st.number_input("테마 평균 PER (배)", value=None, min_value=0.0, step=1.0)
            
            col3, col4, col5 = st.columns(3)
            with col3:
                pe_low = st.number_input("보수 PER (배)", value=15.0, min_value=1.0, step=1.0)
            with col4:
                pe_base = st.number_input("기준 PER (배)", value=20.0, min_value=1.0, step=1.0)
            with col5:
                pe_high = st.number_input("낙관 PER (배)", value=25.0, min_value=1.0, step=1.0)
            
            # DCF/SOTP 파라미터는 None
            fcf_current = growth_rate = terminal_growth = wacc = shares_outstanding = None
            segments = net_debt = None
            
        elif "DCF" in valuation_method:
            st.markdown("#### DCF 방식 파라미터")
            st.caption("💡 성장주나 적자 기업 분석에 적합합니다")
            
            col1, col2 = st.columns(2)
            with col1:
                fcf_current = st.number_input(
                    "현재 FCF (백만 달러)",
                    value=None,
                    step=100.0,
                    help="Free Cash Flow (자유현금흐름)"
                )
                growth_rate = st.number_input(
                    "성장률 Year 1-5 (%)",
                    value=20.0,
                    min_value=0.0,
                    max_value=100.0,
                    step=1.0
                )
                terminal_growth = st.number_input(
                    "영구 성장률 (%)",
                    value=3.0,
                    min_value=0.0,
                    max_value=10.0,
                    step=0.5,
                    help="Terminal Growth Rate"
                )
            with col2:
                wacc = st.number_input(
                    "WACC 할인율 (%)",
                    value=10.0,
                    min_value=0.0,
                    max_value=30.0,
                    step=0.5,
                    help="Weighted Average Cost of Capital"
                )
                shares_outstanding = st.number_input(
                    "발행 주식 수 (백만 주)",
                    value=None,
                    step=100.0,
                    help="Shares Outstanding"
                )
            
            # P/E/SOTP 파라미터는 None
            manual_eps_ttm = manual_eps_fy1 = theme = theme_pe = None
            pe_low = 15.0
            pe_base = 20.0
            pe_high = 25.0
            segments = net_debt = None
            
        else:  # SOTP
            st.markdown("#### SOTP 방식 파라미터")
            st.caption("💡 여러 사업 부문을 가진 복합 기업 분석에 적합합니다")
            
            # 사업 부문 입력
            num_segments = st.number_input(
                "사업 부문 개수",
                min_value=1,
                max_value=10,
                value=3,
                step=1
            )
            
            segments = []
            for i in range(int(num_segments)):
                st.markdown(f"**부문 {i+1}**")
                col1, col2, col3 = st.columns(3)
                with col1:
                    seg_name = st.text_input(f"부문명 {i+1}", value=f"Segment {i+1}", key=f"seg_name_{i}")
                with col2:
                    seg_revenue = st.number_input(
                        f"Revenue (백만 달러)",
                        value=1000.0,
                        step=100.0,
                        key=f"seg_rev_{i}"
                    )
                with col3:
                    seg_multiple = st.number_input(
                        f"Multiple (배)",
                        value=5.0,
                        min_value=0.0,
                        step=0.5,
                        key=f"seg_mult_{i}",
                        help="P/S 또는 EV/EBITDA"
                    )
                segments.append({
                    "name": seg_name,
                    "revenue": seg_revenue,
                    "multiple": seg_multiple
                })
            
            col1, col2 = st.columns(2)
            with col1:
                net_debt = st.number_input(
                    "순부채 (백만 달러)",
                    value=0.0,
                    step=1000.0,
                    help="음수면 순현금 (Net Cash)"
                )
            with col2:
                shares_outstanding = st.number_input(
                    "발행 주식 수 (백만 주)",
                    value=None,
                    step=100.0
                )
            
            # P/E/DCF 파라미터는 None
            manual_eps_ttm = manual_eps_fy1 = theme = theme_pe = None
            pe_low = 15.0
            pe_base = 20.0
            pe_high = 25.0
            fcf_current = growth_rate = terminal_growth = wacc = None
        
        st.markdown("---")
        
        # 분석 실행 버튼
        if st.button("🚀 분석 실행", type="primary", use_container_width=True, disabled=not ticker):
            with st.spinner(f"{ticker} 분석 중..."):
                try:
                    # 1. 주식 데이터 먼저 가져오기 (자동 수집)
                    stock_data = st.session_state.quant_analyst.fetch_stock_data(ticker)
                    
                    if stock_data.get('error'):
                        st.error(f"⚠️ {stock_data['error']}")
                        st.info("💡 수동으로 데이터를 입력해주세요.")
                        st.stop()
                    
                    # 2. 수동 입력값이 없으면 자동 수집된 값 사용
                    final_price = manual_price if manual_price else stock_data.get('price')
                    final_eps_ttm = manual_eps_ttm if manual_eps_ttm else stock_data.get('eps_ttm')
                    final_eps_fy1 = manual_eps_fy1 if manual_eps_fy1 else stock_data.get('eps_fy1')
                    
                    # 3. 밸류에이션 방법 결정
                    if "P/E" in valuation_method:
                        method_code = "pe"
                    elif "DCF" in valuation_method:
                        method_code = "dcf"
                    else:
                        method_code = "sotp"
                    
                    # 4. 분석 실행
                    analysis = st.session_state.quant_analyst.generate_analysis(
                        ticker=ticker,
                        price=final_price,
                        valuation_method=method_code,
                        # P/E 파라미터
                        eps_ttm=final_eps_ttm,
                        eps_fy1=final_eps_fy1,
                        theme=theme if theme else None,
                        theme_pe=theme_pe,
                        pe_low=pe_low,
                        pe_base=pe_base,
                        pe_high=pe_high,
                        # DCF 파라미터
                        fcf_current=fcf_current,
                        growth_rate=growth_rate,
                        terminal_growth=terminal_growth,
                        wacc=wacc,
                        shares_outstanding=shares_outstanding,
                        # SOTP 파라미터
                        segments=segments,
                        net_debt=net_debt
                    )
                    
                    # 5. 결과 저장
                    st.session_state.quant_history.append({
                        'ticker': ticker,
                        'method': valuation_method,
                        'stock_data': stock_data,
                        'analysis': analysis
                    })
                    
                except Exception as e:
                    st.error(f"분석 중 오류 발생: {str(e)}")
        
        # 분석 결과 표시
        st.markdown("---")
        st.subheader("📈 분석 결과")
        
        if st.session_state.quant_history:
            # 최신 분석 결과 표시
            latest = st.session_state.quant_history[-1]
            
            # 종목 정보 표시
            if not latest['stock_data'].get('error'):
                st.info(f"""
                **{latest['stock_data'].get('company_name', latest['ticker'])}** ({latest['ticker']})  
                밸류에이션 방법: **{latest.get('method', 'P/E')}**  
                현재가: ${latest['stock_data'].get('price', 'N/A')} | 
                EPS(TTM): ${latest['stock_data'].get('eps_ttm', 'N/A')} | 
                EPS(FY1): ${latest['stock_data'].get('eps_fy1', 'N/A')} | 
                P/E: {latest['stock_data'].get('pe_ratio', 'N/A')}
                """)
            
            # 분석 결과 표시
            st.markdown(latest['analysis'])
            
            # 이전 분석 결과 (Expander)
            if len(st.session_state.quant_history) > 1:
                with st.expander(f"📜 이전 분석 결과 ({len(st.session_state.quant_history) - 1}개)"):
                    for i, item in enumerate(reversed(st.session_state.quant_history[:-1])):
                        st.markdown(f"### {i+1}. {item['ticker']}")
                        st.markdown(item['analysis'])
                        st.markdown("---")
        else:
            st.info("👆 위에서 종목 티커를 입력하고 '분석 실행' 버튼을 클릭하세요.")


if __name__ == "__main__":
    main()
