"""
재사용 가능한 UI 컴포넌트
"""
import streamlit as st
from config.settings import AGENT_REGISTRY
from typing import List, Dict, Any
import plotly.graph_objects as go


def render_agent_selector() -> List[str]:
    """
    에이전트 선택 UI (복수 선택 가능)
    
    Returns:
        list: 선택된 에이전트 ID 리스트
    """
    # 활성화된 에이전트만 필터링
    enabled_agents = {
        agent_id: info 
        for agent_id, info in AGENT_REGISTRY.items() 
        if info.get('enabled', True)
    }
    
    if not enabled_agents:
        st.warning("사용 가능한 에이전트가 없습니다.")
        return []
    
    # 에이전트 선택 UI
    st.subheader("🤖 에이전트 선택")
    st.caption("RAG 검색에 사용할 에이전트를 선택하세요 (복수 선택 가능)")
    
    # Multiselect 위젯
    agent_options = {
        f"{info['name']} - {info['description']}": agent_id
        for agent_id, info in enabled_agents.items()
    }
    
    selected_labels = st.multiselect(
        "에이전트 선택",
        options=list(agent_options.keys()),
        default=list(agent_options.keys()),  # 기본적으로 모두 선택
        key="agent_selector",
        label_visibility="collapsed"
    )
    
    # 선택된 에이전트 ID 리스트 반환
    selected_ids = [agent_options[label] for label in selected_labels]
    
    # 선택된 에이전트 표시
    if selected_ids:
        st.success(f"✅ {len(selected_ids)}개 에이전트 선택됨")
    else:
        st.warning("⚠️ 에이전트를 선택하지 않으면 모든 에이전트에서 검색합니다")
    
    return selected_ids if selected_ids else None


def render_market_summary():
    """시장 현황 요약 표시"""
    from ui.theme import get_realtime_market_summary
    
    st.subheader("📊 시장 현황")
    market_df = get_realtime_market_summary()
    
    if market_df is not None and not market_df.empty:
        # 주요 지수 필터링
        indices = ["코스피", "나스닥", "S&P 500", "원달러환율"]
        
        for idx_name in indices:
            row = market_df[market_df['종목'] == idx_name]
            if not row.empty:
                val = row.iloc[0]['현재가']
                change = row.iloc[0]['등락']
                label = idx_name
                if idx_name == "원달러환율":
                    val_str = f"₩{val:,.1f}"
                else:
                    val_str = f"{val:,.2f}"
                st.metric(label, val_str, change)
    else:
        st.write("시장 데이터를 불러올 수 없습니다.")


def render_ticker_tape():
    """상단 티커 테이프 표시"""
    from ui.theme import get_realtime_market_summary
    market_df = get_realtime_market_summary()
    
    # 7개 지수 표시 (공포탐욕, 다우, S&P500, 나스닥, 코스피, 환율, 비트코인)
    cols = st.columns(7)
    
    indices = ["공포/탐욕", "다우존스", "S&P 500", "나스닥", "코스피", "원달러환율", "비트코인"]
    labels = ["Fear & Greed", "DOW", "S&P 500", "NASDAQ", "KOSPI", "USD/KRW", "Bitcoin"]
    
    if market_df is not None and not market_df.empty:
        for i, (idx_name, label) in enumerate(zip(indices, labels)):
            row = market_df[market_df['종목'] == idx_name]
            if not row.empty:
                val = row.iloc[0]['현재가']
                change = row.iloc[0]['등락']
                
                # 포맷팅
                if idx_name == "공포/탐욕":
                    val_str = f"{val:.0f}"
                elif idx_name == "원달러환율":
                    val_str = f"{val:,.1f}"
                elif idx_name == "비트코인":
                    val_str = f"${val:,.0f}"
                else:
                    val_str = f"{val:,.0f}" if val > 1000 else f"{val:,.2f}"
                
                cols[i].metric(label, val_str, change)
            else:
                cols[i].metric(label, "N/A", "0.00%")
    else:
        for i, label in enumerate(labels):
            cols[i].metric(label, "N/A", "0.00%")


def render_fear_greed_gauge(fg_value):
    """Fear & Greed 게이지 차트 (Plotly)"""
    if fg_value is None:
        st.warning("지수 데이터가 없습니다.")
        return

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=fg_value,
        domain={'x': [0, 1], 'y': [0, 1]},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "white"},
            'bar': {'color': "white", 'thickness': 0.2},
            'bgcolor': "rgba(0,0,0,0)",
            'borderwidth': 0,
            'steps': [
                {'range': [0, 25], 'color': "#FF4B4B"},   # Extreme Fear
                {'range': [25, 45], 'color': "#FFA500"},  # Fear
                {'range': [45, 55], 'color': "#FFFF00"},  # Neutral
                {'range': [55, 75], 'color': "#90EE90"},  # Greed
                {'range': [75, 100], 'color': "#00FFA3"}  # Extreme Greed
            ],
            'threshold': {
                'line': {'color': "white", 'width': 4},
                'thickness': 0.75,
                'value': fg_value
            }
        }
    ))
    
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': "white", 'family': "Pretendard"},
        height=250,
        margin=dict(l=20, r=20, t=30, b=20)
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_chat_sources(sources: List[Dict[str, Any]]):
    """
    채팅 소스 정보 표시
    
    Args:
        sources: 참고 소스 리스트
    """
    if not sources:
        return
    
    with st.expander("📚 참고 영상"):
        for i, source in enumerate(sources):
            st.markdown(f"""
            **[{i+1}] {source['영상제목']}**  
            - 채널: {source['채널명']}  
            - 업로드: {source['업로드일자']}  
            - 유사도: {source['유사도']}  
            - [영상 보기]({source['영상링크']})
            """)


def render_login_page():
    """전문적인 다크 모드 로그인 페이지 렌더링"""
    st.markdown("""
    <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');

        html, body, [class*="st-"] {
            font-family: 'Pretendard', 'Inter', -apple-system, sans-serif !important;
        }
        .stApp { background-color: #0E1117; }
        #MainMenu, footer { visibility: hidden; }
        header[data-testid="stHeader"] { background: transparent !important; }

        /* 로그인 폼을 카드처럼 */
        [data-testid="stForm"] {
            background: linear-gradient(170deg, #1A1C24 0%, #14161D 100%);
            padding: 36px 32px !important;
            border-radius: 20px !important;
            border: 1px solid rgba(255,255,255,0.07) !important;
            box-shadow: 0 20px 50px rgba(0,0,0,0.5);
        }
        .stTextInput input {
            height: 48px !important;
            border-radius: 12px !important;
            background-color: #0E1117 !important;
            color: #FFFFFF !important;
            border: 1px solid rgba(255,255,255,0.1) !important;
            transition: border-color 0.15s ease;
        }
        .stTextInput input:focus {
            border-color: #00FFA3 !important;
            box-shadow: 0 0 0 1px #00FFA355 !important;
        }
        .stTextInput label { color: #94A3B8 !important; font-size: 13px !important; }
        .stFormSubmitButton button {
            width: 100% !important;
            height: 48px !important;
            border-radius: 12px !important;
            font-weight: 700 !important;
            margin-top: 10px !important;
            background: linear-gradient(90deg, #00FFA3, #00D9F5) !important;
            color: #0E1117 !important;
            border: none !important;
            transition: filter 0.15s ease, transform 0.15s ease;
        }
        .stFormSubmitButton button:hover {
            filter: brightness(1.1);
            transform: translateY(-1px);
        }
        .login-logo {
            text-align: center;
            font-size: 44px;
            margin-bottom: 4px;
        }
        .login-header {
            font-size: 28px;
            font-weight: 800;
            margin-bottom: 8px;
            text-align: center;
            letter-spacing: -0.02em;
            background: linear-gradient(90deg, #FFFFFF 40%, #00FFA3);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .login-subtitle {
            font-size: 14px;
            color: #94A3B8;
            margin-bottom: 28px;
            text-align: center;
        }
    </style>
    """, unsafe_allow_html=True)

    _, col, _ = st.columns([1, 1.2, 1])

    with col:
        st.write("")
        st.write("")
        st.write("")

        st.markdown('<div class="login-logo">📊</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-header">Stock Agent Terminal</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-subtitle">전문 투자 분석을 위한 멀티 에이전트 시스템</div>', unsafe_allow_html=True)

        with st.form("login_form"):
            username = st.text_input("Username", placeholder="아이디를 입력하세요")
            password = st.text_input("Password", type="password", placeholder="비밀번호를 입력하세요")
            submit = st.form_submit_button("Sign In")

            if submit:
                import os
                # 계정 목록: 환경변수 또는 기본값
                accounts = {
                    os.getenv("APP_USERNAME", "admin"): os.getenv("APP_PASSWORD", "admin"),
                    "song": os.getenv("APP_PASSWORD_SONG", "song"),
                }
                if username in accounts and password == accounts[username]:
                    st.session_state.authenticated = True
                    st.session_state.user_id = username  # 사용자 ID 저장
                    st.rerun()
                else:
                    st.error("계정 정보가 일치하지 않습니다.")

        st.markdown("""
        <div style="text-align: center; margin-top: 20px; color: #475569; font-size: 12px;">
            © 2026 Stock Agent Terminal. All rights reserved.
        </div>
        """, unsafe_allow_html=True)
