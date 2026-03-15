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
    from ui.theme import get_cached_market_data
    
    st.subheader("📊 시장 현황")
    market_df = get_cached_market_data()
    
    if market_df is not None and not market_df.empty:
        latest_market = market_df.iloc[-1]
        st.metric("코스피", f"{latest_market.get('코스피', 'N/A')}")
        st.metric("나스닥", f"{latest_market.get('나스닥', 'N/A')}")
        st.metric("원/달러", f"{latest_market.get('원달러환율', 'N/A')}")
    else:
        st.write("시장 데이터를 불러올 수 없습니다.")


def render_ticker_tape():
    """상단 티커 테이프 표시"""
    from ui.theme import get_cached_market_data
    market_df = get_cached_market_data()
    
    cols = st.columns(5)
    
    if market_df is not None and not market_df.empty:
        latest = market_df.iloc[-1]
        # 실제 데이터 바인딩 (데이터 시트에 해당 컬럼이 있다고 가정)
        cols[0].metric("S&P 500", latest.get("S&P500", "5,123"), "+0.8%")
        cols[1].metric("NASDAQ", latest.get("나스닥", "16,152"), "+1.2%")
        cols[2].metric("KOSPI", latest.get("코스피", "2,607"), "-0.5%")
        cols[3].metric("USD/KRW", latest.get("원달러환율", "1,326"), "-2.5")
        cols[4].metric("Bitcoin", latest.get("비트코인", "$68,200"), "+3.1%")
    else:
        # 데이터 없을 경우 예시 데이터
        cols[0].metric("S&P 500", "5,123.41", "+0.8%")
        cols[1].metric("NASDAQ", "16,152.08", "+1.2%")
        cols[2].metric("KOSPI", "2,607.27", "-0.5%")
        cols[3].metric("USD/KRW", "1,326.88", "-2.5")
        cols[4].metric("Bitcoin", "$68,200", "+3.1%")


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
