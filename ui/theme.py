"""
UI 테마 관련 함수
Investment Platform 전문 UI (토스 증권 스타일) 적용
"""
import streamlit as st
import pandas as pd
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


@st.cache_data(ttl=60)
def get_realtime_market_summary():
    """주요 지수 실시간 시세 조회.

    - 가격은 yfinance fast_info.lastPrice (야후 웹사이트와 동일한 장중 가격)
    - 등락률은 lastPrice vs previousClose
    - 캐시 60초 (그 이상 늘리면 stale)
    - CNN 공포/탐욕은 공식 그래프 API 직접 호출
    """
    try:
        import yfinance as yf
        import requests
        import math

        # 나스닥은 100 지수(^NDX)로 표시 — 야후 메인 카드와 일치
        mapping = {
            "^DJI": "다우존스",
            "^GSPC": "S&P 500",
            "^NDX": "나스닥 100",
            "^KS11": "코스피",
            "KRW=X": "원달러환율",
            "BTC-USD": "비트코인",
        }

        results = []

        # CNN 공포/탐욕 지수 — 실패 시 가짜 50/Neutral 대신 행을 비워 'N/A'로 표시
        # (조용한 폴백이 고장을 가리지 않도록)
        try:
            url = 'https://production.dataviz.cnn.io/index/fearandgreed/graphdata'
            # CNN은 봇 차단(418)이 있어 브라우저 수준 헤더가 모두 필요 (UA만으론 418)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Origin': 'https://edition.cnn.com',
                'Referer': 'https://edition.cnn.com/markets/fear-and-greed',
            }
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                score = data['fear_and_greed']['score']
                rating = data['fear_and_greed']['rating'].title()
                results.append({"종목": "공포/탐욕", "현재가": float(score), "등락": rating})
        except Exception:
            pass

        for ticker_id, name in mapping.items():
            try:
                fi = yf.Ticker(ticker_id).fast_info
                last = fi.get("lastPrice")
                prev = fi.get("previousClose")

                val = float(last) if last is not None else 0.0
                change_str = "0.00%"
                change_value = 0.0
                if (last is not None and prev is not None
                        and not math.isnan(float(last)) and not math.isnan(float(prev))
                        and float(prev) != 0):
                    diff = float(last) - float(prev)
                    pct = diff / float(prev) * 100
                    change_str = f"{pct:+.2f}%"
                    change_value = diff
                if math.isnan(val):
                    val = 0.0
                results.append({
                    "종목": name,
                    "현재가": val,
                    "등락": change_str,
                    "등락값": change_value,
                })
            except Exception as e:
                print(f"Error fetching {ticker_id}: {e}")
                results.append({"종목": name, "현재가": 0.0, "등락": "0.00%", "등락값": 0.0})

        return pd.DataFrame(results)
    except Exception as e:
        print(f"실시간 시장 데이터 조회 실패: {e}")
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
    - 다크 모드 (#0E1117) + 카드 (#1A1C24)
    - 포인트 컬러를 버튼/입력창/슬라이더에 반영
    - 호버/포커스 인터랙션
    """
    accent = point_color or "#FFA500"

    st.markdown(f"""
    <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');

        html, body, [class*="st-"] {{
            font-family: 'Pretendard', 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        }}

        /* Material 아이콘은 전용 폰트 유지 (탭 화살표 등이 텍스트로 깨지는 것 방지) */
        [data-testid="stIconMaterial"],
        .material-symbols-rounded,
        [class*="material-symbols"] {{
            font-family: 'Material Symbols Rounded' !important;
        }}

        /* ── 1. 배경 ───────────────────────── */
        .stApp {{
            background-color: #0E1117;
            color: #E2E8F0;
        }}

        /* 스크롤바 */
        ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
        ::-webkit-scrollbar-track {{ background: #0E1117; }}
        ::-webkit-scrollbar-thumb {{ background: #31343F; border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #475569; }}

        /* ── 2. Metric 카드 ─────────────────── */
        [data-testid="stMetric"] {{
            background: linear-gradient(160deg, #1A1C24 0%, #16181F 100%);
            padding: 18px !important;
            border-radius: 16px !important;
            border: 1px solid rgba(255,255,255,0.06) !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.25) !important;
            transition: transform 0.15s ease, border-color 0.15s ease;
        }}
        [data-testid="stMetric"]:hover {{
            transform: translateY(-2px);
            border-color: rgba(255,255,255,0.14) !important;
        }}
        [data-testid="stMetricLabel"] {{
            font-size: 13px !important;
            color: #94A3B8 !important;
            font-weight: 500 !important;
            letter-spacing: 0.02em;
        }}
        [data-testid="stMetricValue"] {{
            font-size: 28px !important;
            font-weight: 700 !important;
            color: #FFFFFF !important;
            letter-spacing: -0.02em;
        }}

        /* ── 3. 탭 ──────────────────────────── */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 6px;
            background-color: transparent !important;
            flex-wrap: wrap;
        }}
        .stTabs [data-baseweb="tab"] {{
            height: 42px;
            white-space: pre;
            background-color: #1A1C24 !important;
            border-radius: 10px !important;
            color: #94A3B8 !important;
            border: 1px solid transparent !important;
            padding: 0 16px !important;
            font-weight: 500 !important;
            transition: all 0.15s ease;
        }}
        .stTabs [data-baseweb="tab"]:hover {{
            color: #E2E8F0 !important;
            border-color: rgba(255,255,255,0.12) !important;
        }}
        .stTabs [aria-selected="true"] {{
            background-color: #31343F !important;
            color: #FFFFFF !important;
            font-weight: 700 !important;
            border-color: {accent}55 !important;
            box-shadow: 0 0 0 1px {accent}33;
        }}
        .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{
            display: none;
        }}

        /* ── 4. 버튼 ────────────────────────── */
        .stButton button, .stDownloadButton button, .stFormSubmitButton button {{
            border-radius: 12px !important;
            border: 1px solid rgba(255,255,255,0.1) !important;
            background-color: #1A1C24 !important;
            color: #E2E8F0 !important;
            font-weight: 600 !important;
            transition: all 0.15s ease !important;
        }}
        .stButton button:hover, .stDownloadButton button:hover, .stFormSubmitButton button:hover {{
            border-color: {accent} !important;
            color: #FFFFFF !important;
            box-shadow: 0 0 12px {accent}44;
            transform: translateY(-1px);
        }}
        /* Primary 버튼: 포인트 컬러 채움 */
        .stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] {{
            background-color: {accent} !important;
            border-color: {accent} !important;
            color: #0E1117 !important;
        }}
        .stButton button[kind="primary"]:hover {{
            filter: brightness(1.15);
            color: #0E1117 !important;
        }}
        .stButton button p {{ color: inherit !important; }}

        /* ── 5. 입력 폼 ─────────────────────── */
        .stTextInput input, .stNumberInput input, .stTextArea textarea,
        .stSelectbox div[data-baseweb="select"], .stDateInput input {{
            background-color: #1A1C24 !important;
            color: #FFFFFF !important;
            border: 1px solid rgba(255,255,255,0.1) !important;
            border-radius: 10px !important;
            transition: border-color 0.15s ease;
        }}
        .stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {{
            border-color: {accent} !important;
            box-shadow: 0 0 0 1px {accent}55 !important;
        }}

        /* 채팅 입력창 */
        [data-testid="stChatInput"] {{
            background-color: #1A1C24 !important;
            border: 1px solid rgba(255,255,255,0.12) !important;
            border-radius: 14px !important;
        }}
        [data-testid="stChatInput"]:focus-within {{
            border-color: {accent} !important;
            box-shadow: 0 0 0 1px {accent}44;
        }}
        [data-testid="stChatInput"] textarea {{
            color: #FFFFFF !important;
        }}

        /* ── 6. 채팅 메시지 ─────────────────── */
        [data-testid="stChatMessage"] {{
            background-color: #1A1C24 !important;
            border-radius: 16px !important;
            padding: 16px !important;
            margin-bottom: 10px !important;
            border: 1px solid rgba(255,255,255,0.05) !important;
        }}

        /* ── 7. Expander / 데이터프레임 ─────── */
        [data-testid="stExpander"] {{
            background-color: #1A1C24 !important;
            border: 1px solid rgba(255,255,255,0.06) !important;
            border-radius: 12px !important;
            overflow: hidden;
        }}
        [data-testid="stExpander"] summary {{
            font-weight: 600 !important;
        }}
        [data-testid="stExpander"] summary:hover {{
            color: {accent} !important;
        }}
        [data-testid="stDataFrame"] {{
            border-radius: 12px !important;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,0.06);
        }}

        /* ── 8. 알림 박스 (다크 모드 친화) ──── */
        [data-testid="stAlert"] {{
            background-color: #1A1C24 !important;
            border-radius: 12px !important;
            border: 1px solid rgba(255,255,255,0.08) !important;
        }}
        [data-testid="stAlert"] p {{
            color: #E2E8F0 !important;
        }}

        /* ── 9. 사이드바 / 헤더 / 기타 ──────── */
        [data-testid="stSidebar"] {{
            background-color: #0E1117 !important;
            border-right: 1px solid rgba(255,255,255,0.05);
        }}
        header[data-testid="stHeader"] {{
            background: rgba(14, 17, 23, 0.8) !important;
            backdrop-filter: blur(10px);
        }}
        #MainMenu, footer {{ visibility: hidden; }}
        .stDeployButton {{ display: none; }}

        hr {{
            border-color: rgba(255,255,255,0.07) !important;
            margin: 1.2rem 0 !important;
        }}

        /* ── 10. 타이포그래피 ───────────────── */
        h1, h2, h3 {{
            color: #FFFFFF !important;
            font-weight: 700 !important;
            letter-spacing: -0.02em;
        }}
        h1 {{
            background: linear-gradient(90deg, #FFFFFF 30%, {accent});
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .stMarkdown p, .stMarkdown li {{
            line-height: 1.7;
            color: #E2E8F0;
        }}
        [data-testid="stCaptionContainer"] {{
            color: #64748B !important;
        }}

        /* 슬라이더 포인트 컬러 */
        .stSlider [data-baseweb="slider"] [role="slider"] {{
            background-color: {accent} !important;
            border-color: {accent} !important;
        }}
        .stSlider [data-baseweb="slider"] > div > div {{
            background: {accent} !important;
        }}

        /* 체크박스 포인트 컬러 */
        .stCheckbox [data-baseweb="checkbox"] [aria-checked="true"] {{
            background-color: {accent} !important;
            border-color: {accent} !important;
        }}

        /* ── 입력창 대비 보강 ───────────────── */
        /* placeholder: 배경과 구분되되 본문보다 흐리게 */
        input::placeholder, textarea::placeholder {{
            color: #64748B !important;
            opacity: 1 !important;
        }}

        /* 셀렉트박스 드롭다운 메뉴 (포털로 렌더링되어 별도 지정 필요) */
        [data-baseweb="popover"] [data-baseweb="menu"],
        [data-baseweb="popover"] ul[role="listbox"] {{
            background-color: #1A1C24 !important;
            border: 1px solid rgba(255,255,255,0.12) !important;
        }}
        [data-baseweb="menu"] li, ul[role="listbox"] li {{
            color: #E2E8F0 !important;
            background-color: transparent !important;
        }}
        [data-baseweb="menu"] li:hover, ul[role="listbox"] li:hover,
        [data-baseweb="menu"] li[aria-selected="true"] {{
            background-color: #31343F !important;
            color: #FFFFFF !important;
        }}

        /* 달력 팝업 (date_input) */
        [data-baseweb="calendar"] {{
            background-color: #1A1C24 !important;
        }}
        [data-baseweb="calendar"] * {{
            color: #E2E8F0;
        }}

        /* number_input 스피너 버튼 */
        .stNumberInput button {{
            background-color: #1A1C24 !important;
            color: #E2E8F0 !important;
        }}

        /* 라디오 버튼: 항목 글씨 흰색 + 선택 시 포인트 컬러 */
        .stRadio label, .stRadio [data-testid="stMarkdownContainer"] p {{
            color: #FFFFFF !important;
        }}
        .stRadio [data-baseweb="radio"] div:first-child {{
            border-color: #64748B !important;
        }}
        .stRadio [data-baseweb="radio"] [aria-checked="true"] ~ div,
        .stRadio [data-baseweb="radio"] div[style*="background"] {{
            border-color: {accent} !important;
        }}
    </style>
    """, unsafe_allow_html=True)
