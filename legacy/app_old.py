"""
Stock Bot RAG 챗봇 - Streamlit 앱
Fear & Greed Index 기반 히트맵 테마 적용
"""
import streamlit as st
from modules.rag_engine import RAGEngine
from utils.sheet_loader import SheetDataLoader
import os
from dotenv import load_dotenv

load_dotenv()


# 캐싱된 데이터 로더 함수들 (API 호출 최소화)
@st.cache_data(ttl=300)  # 5분간 캐시
def get_cached_fear_greed_index():
    """Fear & Greed Index 캐싱 (5분)"""
    try:
        loader = SheetDataLoader()
        return loader.get_latest_fear_greed_index()
    except Exception as e:
        st.warning(f"Fear & Greed Index 로드 실패: {e}")
        return None, "오류"


@st.cache_data(ttl=300)  # 5분간 캐시
def get_cached_market_data():
    """시장 데이터 캐싱 (5분)"""
    try:
        loader = SheetDataLoader()
        return loader.load_market_data()
    except Exception as e:
        st.warning(f"시장 데이터 로드 실패: {e}")
        return None


def get_heatmap_color(index_value):
    """
    Fear & Greed Index 값에 따라 히트맵 색상 반환 (선형 보간)
    Args:
        index_value: CNN Fear & Greed Index (0-100)
    Returns:
        tuple: (배경색, 텍스트색, 상태 이모지, 상태 텍스트)
    """
    if index_value is None:
        return "#2d2d2d", "#ffffff", "⚪", "데이터 없음"
    
    try:
        idx = float(index_value)
    except:
        return "#2d2d2d", "#ffffff", "⚪", "데이터 오류"
    
    # 색상 구간 정의 (RGB)
    # 극공포(0) -> 공포(25) -> 중립(50) -> 탐욕(75) -> 극탐욕(100)
    
    if idx <= 25:  # 극공포: 진한 초록
        # 0-25: #1a4d2e (진한 초록)
        ratio = idx / 25
        r = int(26 + (45 - 26) * ratio)
        g = int(77 + (107 - 77) * ratio)
        b = int(46 + (74 - 46) * ratio)
        emoji = "💚"
        status = "극공포 (매수 기회)"
    
    elif idx <= 45:  # 공포: 연한 초록
        # 25-45: #2d6b4a (연한 초록)
        ratio = (idx - 25) / 20
        r = int(45 + (61 - 45) * ratio)
        g = int(107 + (107 - 107) * ratio)
        b = int(74 + (74 - 74) * ratio)
        emoji = "🟢"
        status = "공포 (매수 고려)"
    
    elif idx <= 55:  # 중립: 회색/베이지
        # 45-55: #3d3d3d ~ #4a4a4a (회색)
        ratio = (idx - 45) / 10
        r = int(61 + (74 - 61) * ratio)
        g = int(61 + (74 - 61) * ratio)
        b = int(61 + (74 - 61) * ratio)
        emoji = "⚪"
        status = "중립 (관망)"
    
    elif idx <= 75:  # 탐욕: 연한 빨강
        # 55-75: #6b3d3d (연한 빨강)
        ratio = (idx - 55) / 20
        r = int(74 + (107 - 74) * ratio)
        g = int(74 + (61 - 74) * ratio)
        b = int(74 + (61 - 74) * ratio)
        emoji = "🟠"
        status = "탐욕 (주의)"
    
    else:  # 극탐욕: 진한 빨강
        # 75-100: #4d1a1a (진한 빨강)
        ratio = (idx - 75) / 25
        r = int(107 + (77 - 107) * ratio)
        g = int(61 + (26 - 61) * ratio)
        b = int(61 + (26 - 61) * ratio)
        emoji = "🔴"
        status = "극탐욕 (과열 경고)"
    
    bg_color = f"#{r:02x}{g:02x}{b:02x}"
    text_color = "#ffffff" if idx < 50 else "#f0f0f0"
    
    return bg_color, text_color, emoji, status


def apply_theme(bg_color, text_color):
    """
    Streamlit 페이지에 커스텀 CSS 테마 적용
    """
    st.markdown(f"""
    <style>
        /* 전체 페이지 배경 */
        .stApp {{
            background-color: {bg_color};
            color: {text_color};
        }}
        
        /* 사이드바 */
        [data-testid="stSidebar"] {{
            background-color: {bg_color};
        }}
        
        /* 입력 필드 */
        .stTextInput > div > div > input {{
            background-color: rgba(255, 255, 255, 0.9);
            color: #000000 !important;
            border: 1px solid rgba(255, 255, 255, 0.3);
        }}
        
        /* 버튼 */
        .stButton > button {{
            background-color: rgba(255, 255, 255, 0.2);
            color: {text_color};
            border: 1px solid rgba(255, 255, 255, 0.3);
        }}
        
        .stButton > button:hover {{
            background-color: rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.5);
        }}
        
        /* 채팅 메시지 */
        .stChatMessage {{
            background-color: rgba(255, 255, 255, 0.1);
        }}
        
        /* Expander */
        .streamlit-expanderHeader {{
            background-color: rgba(255, 255, 255, 0.1);
            color: {text_color};
        }}
        
        /* 텍스트 색상 */
        h1, h2, h3, h4, h5, h6, p, span, div {{
            color: {text_color} !important;
        }}
        
        /* 링크 */
        a {{
            color: #88ccff !important;
        }}
        
        /* Streamlit 상단 헤더/툴바 숨기기 또는 스타일링 */
        header[data-testid="stHeader"] {{
            background-color: {bg_color} !important;
        }}
        
        /* Streamlit 상단 툴바 */
        .stDeployButton {{
            visibility: hidden;
        }}
        
        /* Running 표시 영역 */
        [data-testid="stStatusWidget"] {{
            visibility: hidden;
        }}
        
        /* 탭 스타일링 */
        .stTabs [data-baseweb="tab-list"] {{
            background-color: rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            padding: 4px;
        }}
        
        .stTabs [data-baseweb="tab"] {{
            background-color: transparent;
            color: {text_color};
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: 500;
        }}
        
        .stTabs [data-baseweb="tab"]:hover {{
            background-color: rgba(255, 255, 255, 0.15);
        }}
        
        .stTabs [aria-selected="true"] {{
            background-color: rgba(255, 255, 255, 0.25) !important;
            color: {text_color} !important;
            font-weight: 600;
        }}
        
        /* 탭 패널 배경 */
        .stTabs [data-baseweb="tab-panel"] {{
            background-color: rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            padding: 20px;
            margin-top: 10px;
        }}
        
        /* 날짜 입력 필드 스타일링 */
        .stDateInput > div > div > input {{
            background-color: rgba(255, 255, 255, 0.95) !important;
            color: #000000 !important;
            border: 1px solid rgba(255, 255, 255, 0.3);
            font-weight: 500;
            min-width: 140px !important;
        }}
        
        /* 날짜 입력 레이블 */
        .stDateInput label {{
            color: {text_color} !important;
            font-weight: 500;
        }}
        
        /* 날짜 선택 팝업 */
        [data-baseweb="calendar"] {{
            background-color: #ffffff !important;
        }}
        
        [data-baseweb="calendar"] * {{
            color: #000000 !important;
        }}
    </style>
    """, unsafe_allow_html=True)


def main():
    st.set_page_config(
        page_title="Stock Bot - Multi-Agent",
        page_icon="📈",
        layout="wide"
    )
    
    # Fear & Greed Index 가져오기 (캐싱됨)
    fg_index, fg_status = get_cached_fear_greed_index()
    
    # 히트맵 색상 계산
    bg_color, text_color, emoji, status_text = get_heatmap_color(fg_index)
    
    # 테마 적용
    apply_theme(bg_color, text_color)
    
    # 헤더
    st.title("📈 Stock Bot - Multi-Agent System")
    
    # Fear & Greed Index 표시
    if fg_index is not None:
        st.markdown(f"""
        ### {emoji} CNN Fear & Greed Index: **{fg_index}** ({fg_status})
        **상태**: {status_text}
        """)
    else:
        st.markdown("### ⚪ CNN Fear & Greed Index: 데이터 없음")
    
    st.markdown("---")
    
    # 사이드바
    with st.sidebar:
        st.header("⚙️ 설정")
        
        # 시장 상태 요약 (캐싱됨)
        st.subheader("📊 시장 현황")
        market_df = get_cached_market_data()
        if market_df is not None and not market_df.empty:
            latest_market = market_df.iloc[-1]
            st.metric("코스피", f"{latest_market.get('코스피', 'N/A')}")
            st.metric("나스닥", f"{latest_market.get('나스닥', 'N/A')}")
            st.metric("원/달러", f"{latest_market.get('원달러환율', 'N/A')}")
        else:
            st.write("시장 데이터를 불러올 수 없습니다.")
        
        st.markdown("---")
        
        # YouTube 데이터 수집 섹션
        st.subheader("📥 YouTube 데이터 수집")
        
        # 날짜 범위 선택
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "시작일",
                value=None,
                key="yt_start_date",
                help="수집할 영상의 시작 날짜"
            )
        with col2:
            end_date = st.date_input(
                "종료일",
                value=None,
                key="yt_end_date",
                help="수집할 영상의 종료 날짜"
            )
        
        # 채널 버튼들 (향후 확장 가능)
        st.caption("수집할 채널 선택:")
        
        # 올랜도킴 버튼
        if st.button("🎬 올랜도킴 영상 수집", use_container_width=True, disabled=(start_date is None or end_date is None)):
            # 진행 상황 표시 영역
            progress_container = st.empty()
            status_container = st.empty()
            
            with st.spinner("영상 수집 중..."):
                try:
                    import datetime
                    from main import YouTubeManager, SheetLogger
                    from modules.stock_extractor import StockExtractor
                    import time
                    
                    # 환경 변수 로드
                    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
                    GOOGLE_SHEETS_CREDENTIALS_JSON = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
                    SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
                    ORLANDO_CHANNEL_ID = os.getenv("TARGET_CHANNEL_ID_LIST", "").split(",")[0].strip()
                    
                    if not all([YOUTUBE_API_KEY, GOOGLE_SHEETS_CREDENTIALS_JSON, SPREADSHEET_URL, ORLANDO_CHANNEL_ID]):
                        st.error("환경 변수가 설정되지 않았습니다. .env 파일을 확인하세요.")
                        st.stop()
                    
                    # 초기화
                    yt_manager = YouTubeManager(YOUTUBE_API_KEY)
                    stock_extractor = StockExtractor()
                    logger = SheetLogger(GOOGLE_SHEETS_CREDENTIALS_JSON, SPREADSHEET_URL)
                    
                    # 날짜 형식 변환
                    start_date_str = start_date.strftime("%Y-%m-%d")
                    end_date_str = end_date.strftime("%Y-%m-%d")
                    
                    status_container.info(f"📅 기간: {start_date_str} ~ {end_date_str}")
                    
                    # 영상 목록 가져오기
                    videos = yt_manager.get_videos_in_range(
                        ORLANDO_CHANNEL_ID,
                        start_date_str,
                        end_date_str,
                        max_results=50
                    )
                    
                    if not videos:
                        st.warning("해당 기간에 영상이 없습니다.")
                        st.stop()
                    
                    # 기존 데이터 확인 (중복 방지)
                    worksheet = logger.get_worksheet("Youtube_Log")
                    existing_data = worksheet.get_all_values()
                    existing_urls = {row[4] for row in existing_data if len(row) > 4 and row[4]}
                    
                    # 데이터 수집
                    data_to_log = []
                    stock_mentions_to_log = []
                    success_count = 0
                    fail_count = 0
                    skip_count = 0
                    
                    total_videos = len(videos)
                    
                    for idx, video in enumerate(videos, 1):
                        # 진행률 표시
                        progress_container.progress(idx / total_videos, text=f"진행: {idx}/{total_videos}")
                        
                        # 중복 체크
                        if video['url'] in existing_urls:
                            skip_count += 1
                            status_container.info(f"⏭️ 건너뜀: {video['title'][:30]}... (이미 존재)")
                            continue
                        
                        # 현재 처리 중인 영상 표시
                        status_container.info(f"🎬 처리 중 ({idx}/{total_videos}): {video['title'][:40]}...")
                        
                        # 자막 추출
                        time.sleep(2)  # API 제한 방지
                        transcript_result = yt_manager.get_transcript(video['video_id'])
                        
                        if transcript_result and transcript_result[0]:
                            transcript_text, timestamps_json = transcript_result
                            
                            # 50,000자 제한
                            if len(transcript_text) > 50000:
                                transcript_text = transcript_text[:50000]
                            
                            # 종목 추출
                            stocks = stock_extractor.extract_stocks_from_transcript(transcript_text, video['title'])
                            
                            if stocks:
                                for stock in stocks:
                                    stock_row = [
                                        video['title'],
                                        video['channel_title'],
                                        video['publish_time'].split('T')[0],
                                        stock['종목명'],
                                        stock['ticker'],
                                        stock['market'],
                                        video['url']
                                    ]
                                    stock_mentions_to_log.append(stock_row)
                            
                            success_count += 1
                        else:
                            transcript_text = "자막 없음 (자동 자막 미지원)"
                            fail_count += 1
                        
                        # 데이터 준비
                        upload_date = video['publish_time'].split('T')[0]
                        collect_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        row = [
                            upload_date,
                            video['channel_title'],
                            video['title'],
                            transcript_text,
                            video['url'],
                            collect_time
                        ]
                        data_to_log.append(row)
                        existing_urls.add(video['url'])
                    
                    # Google Sheets에 저장
                    if data_to_log:
                        status_container.info("💾 Google Sheets에 저장 중...")
                        logger.log_youtube_data(data_to_log)
                    
                    if stock_mentions_to_log:
                        logger.log_stock_mentions(stock_mentions_to_log)
                    
                    # ChromaDB에 자동 청킹 및 임베딩 (🆕 JSON 기반)
                    if success_count > 0:
                        status_container.info("🤖 LLM 전처리 및 ChromaDB 임베딩 중...")
                        try:
                            from modules.transcript_processor import TranscriptProcessor
                            from utils.vector_store import VectorStore
                            
                            processor = TranscriptProcessor()
                            vector_store = VectorStore()
                            
                            # 새로 수집된 데이터만 임베딩
                            new_data_for_embedding = [
                                row for row in data_to_log 
                                if row[3] != "자막 없음 (자동 자막 미지원)"
                            ]
                            
                            if new_data_for_embedding:
                                json_data_list = []
                                metadatas = []
                                
                                for row in new_data_for_embedding:
                                    # LLM 전처리
                                    json_data = processor.process(
                                        transcript=row[3],
                                        video_title=row[2],
                                        video_url=row[4]
                                    )
                                    
                                    # 메타데이터 구성
                                    metadata = {
                                        '업로드일자': row[0],
                                        '채널명': row[1],
                                        '영상제목': row[2],
                                        '영상링크': row[4]
                                    }
                                    
                                    json_data_list.append(json_data)
                                    metadatas.append(metadata)
                                
                                # JSON 기반 청킹 및 임베딩
                                vector_store.add_json_documents(json_data_list, metadatas)
                                status_container.success(f"✅ ChromaDB에 {len(json_data_list)}개 영상 임베딩 완료!")
                            else:
                                status_container.info("ℹ️ 임베딩할 새 데이터가 없습니다.")
                        except Exception as embed_error:
                            status_container.warning(f"⚠️ ChromaDB 임베딩 실패: {str(embed_error)}")
                    
                    # 완료 메시지
                    progress_container.empty()
                    status_container.success(f"""
                    ✅ 수집 완료!
                    - 총 영상: {total_videos}개
                    - 성공: {success_count}개
                    - 실패: {fail_count}개
                    - 건너뜀: {skip_count}개
                    - 종목 추출: {len(stock_mentions_to_log)}개
                    """)
                    
                except Exception as e:
                    st.error(f"❌ 오류 발생: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())
        
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
        
        if "rag_engine" not in st.session_state:
            with st.spinner("RAG 엔진 초기화 중..."):
                try:
                    from modules.rag_engine import RAGEngine
                    st.session_state.rag_engine = RAGEngine()
                except Exception as e:
                    st.error(f"RAG 엔진 초기화 실패: {e}")
                    st.stop()
        
        # 사용자 입력 (상단에 배치)
        st.markdown("---")
        prompt = st.chat_input("질문을 입력하세요 (예: 삼성전자 전망은?)", key="rag_input")
        
        if prompt:
            # 사용자 메시지 추가
            st.session_state.rag_messages.append({"role": "user", "content": prompt})
            
            # AI 답변 생성
            with st.spinner("답변 생성 중..."):
                try:
                    result = st.session_state.rag_engine.chat(
                        prompt, 
                        top_k=top_k, 
                        temperature=temperature
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
                        with st.expander("📚 참고 영상"):
                            for i, source in enumerate(message["sources"]):
                                st.markdown(f"""
                                **[{i+1}] {source['영상제목']}**  
                                - 채널: {source['채널명']}  
                                - 업로드: {source['업로드일자']}  
                                - 유사도: {source['유사도']}  
                                - [영상 보기]({source['영상링크']})
                                """)
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
                    from modules.quant_analyst import QuantAnalyst
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
        
        # 방법별 동적 입력 필드
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
