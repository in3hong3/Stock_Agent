"""
UI 테마 관련 함수
Investment Platform 전문 UI (토스 증권 스타일) 적용
"""
import streamlit as st
from utils.sheet_loader import SheetDataLoader


def get_cached_fear_greed_index():
    """Fear & Greed Index 실시간 조회"""
    from main import CNNScraper
    
    try:
        index_value, status = CNNScraper.get_fear_and_greed_index()
        if index_value != -1:
            return index_value, status
    except Exception as e:
        print(f"API 실시간 조회 실패: {e}")

    try:
        loader = SheetDataLoader()
        return loader.get_latest_fear_greed_index()
    except Exception as e:
        st.warning(f"Fear & Greed Index 로드 실패 (모든 시도 실패): {e}")
        return None, "오류"


@st.cache_data(ttl=300)
def get_cached_market_data():
    """시장 데이터 캐싱 (5분)"""
    try:
        loader = SheetDataLoader()
        return loader.load_market_data()
    except Exception as e:
        st.warning(f"시장 데이터 로드 실패: {e}")
        return None


def get_heatmap_color(index_value):
    """지수 값에 따른 히트맵 컬러 (Dark UI에 최적화된 채도 조절)"""
    if index_value is None:
        return "#1A1C24", "#FFFFFF", "⚪", "데이터 없음"
    
    try:
        idx = float(index_value)
    except:
        return "#1A1C24", "#FFFFFF", "⚪", "데이터 오류"
    
    if idx <= 25:
        emoji = "💚"
        status = "극공포 (매수 기회)"
    elif idx <= 45:
        emoji = "🟢"
        status = "공포 (매수 고려)"
    elif idx <= 55:
        emoji = "⚪"
        status = "중립 (관망)"
    elif idx <= 75:
        emoji = "🟠"
        status = "탐욕 (주의)"
    else:
        emoji = "🔴"
        status = "극탐욕 (과열 경고)"
    
    return "#1A1C24", "#FFFFFF", emoji, status


def get_point_color(index_value):
    """시장 심리에 따른 악센트 컬러 (피로도 낮은 파스텔톤/선명한 톤 조합)"""
    if index_value is None:
        return "#6E7175", "#FFFFFF" # Gray for Neutral
    
    try:
        idx = float(index_value)
    except:
        return "#6E7175", "#FFFFFF"
        
    if idx < 30:
        return "#FF4B4B", "#FFFFFF"  # Fear: Red
    elif idx <= 70:
        return "#FFA500", "#000000"  # Neutral: Orange
    else:
        return "#00FFA3", "#000000"  # Greed: Emerald Green


def apply_theme(bg_color=None, text_color=None, point_color=None):
    """
    Investment Platform (토스 증권 스타일) 전문 UI 적용
    - 다크 모드 (#0E1117)
    - 카드 디자인 (#1A1C24)
    - Pretendard/Inter 폰트
    - Streamlit UI 숨김
    """
    
    # 폰트 및 기본 스타일 주입
    st.markdown("""
    <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
        
        * {
            font-family: 'Pretendard', 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
        }

        /* 1. 배경 및 대지 설정 */
        .stApp {
            background-color: #0E1117;
            color: #FFFFFF;
        }
        
        /* 2. 카드 및 위젯 공통 스타일 (Glassmorphism 기초) */
        div[data-testid="stVerticalBlock"] > div > div[data-testid="stVerticalBlock"] {
            background-color: transparent;
        }
        
        /* 위젯 카드 스타일링 */
        .stButton button, .stDownloadButton button, .stSelectbox, .stTextInput, .stTextArea, .stMultiSelect {
            border-radius: 12px !important;
        }

        /* 3. Metric 커스텀 (큼직하고 시원한 스타일) */
        [data-testid="stMetric"] {
            background-color: #1A1C24;
            padding: 20px !important;
            border-radius: 16px !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2) !important;
            border: 1px solid rgba(255,255,255,0.05) !important;
        }
        
        [data-testid="stMetricLabel"] {
            font-size: 14px !important;
            color: #94A3B8 !important;
            font-weight: 500 !important;
        }
        
        [data-testid="stMetricValue"] {
            font-size: 32px !important;
            font-weight: 700 !important;
            color: #FFFFFF !important;
        }

        /* 4. 탭(st.tabs) 스타일 커스텀 */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            background-color: transparent !important;
        }

        .stTabs [data-baseweb="tab"] {
            height: 44px;
            white-space: pre;
            background-color: #1A1C24 !important;
            border-radius: 10px !important;
            color: #94A3B8 !important;
            border: none !important;
            padding: 0 20px !important;
            font-weight: 500 !important;
            transition: all 0.2s ease;
        }

        .stTabs [aria-selected="true"] {
            background-color: #31343F !important;
            color: #FFFFFF !important;
            font-weight: 700 !important;
        }

        /* 5. 사이드바 스타일 */
        [data-testid="stSidebar"] {
            background-color: #0E1117 !important;
            border-right: 1px solid rgba(255,255,255,0.05);
        }
        
        [data-testid="stSidebarNav"] {
            background-color: transparent !important;
        }

        /* 6. 스트림릿 UI 요소 숨기기 */
        header[data-testid="stHeader"] {
            background: rgba(14, 17, 23, 0.8) !important;
            backdrop-filter: blur(10px);
        }
        
        #MainMenu, footer, header {
            visibility: hidden;
        }
        
        .stDeployButton {
            display: none;
        }

        /* 7. 채팅 메시지 카드 스타일 */
        [data-testid="stChatMessage"] {
            background-color: #1A1C24 !important;
            border-radius: 16px !important;
            padding: 15px !important;
            margin-bottom: 10px !important;
            border: 1px solid rgba(255,255,255,0.05) !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1) !important;
        }

        /* 텍스트 줄 간격 및 색상 */
        p, li, span, div {
            line-height: 1.6;
            color: #E2E8F0;
        }

        h1, h2, h3 {
            color: #FFFFFF !important;
            font-weight: 700 !important;
        }

        /* 8. 버튼 및 알림 박스 내 텍스트 검은색 (가독성 개선) */
        .stButton button p, .stButton button span, .stButton button div {
            color: #000000 !important;
        }
        
        /* 알림/정보 박스 내 텍스트도 검은색으로 (배경색 대비) */
        [data-testid="stNotification"] p, [data-testid="stNotification"] span, [data-testid="stNotification"] div {
            color: #000000 !important;
        }

        /* 입력 폼 스타일링 */
        .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
            background-color: #1A1C24 !important;
            color: #FFFFFF !important;
            border: 1px solid rgba(255,255,255,0.1) !important;
        }

    </style>
    """, unsafe_allow_html=True)
