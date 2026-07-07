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
    """상단 지수 카드 — 야후 파이낸스 스타일 (한국식 색상: 빨강↑ / 파랑↓)."""
    from ui.theme import get_realtime_market_summary
    market_df = get_realtime_market_summary()

    indices = ["공포/탐욕", "다우존스", "S&P 500", "나스닥 100", "코스피", "원달러환율", "비트코인"]
    labels  = ["F&G", "DOW", "S&P 500", "NASDAQ 100", "KOSPI", "USD/KRW", "BTC"]

    # 한국식 색상 — 상승=빨강, 하락=파랑, 보합=회색
    UP, DOWN, FLAT, MUTED, MAIN = "#FF4B4B", "#4B7BFF", "#94A3B8", "#94A3B8", "#E2E8F0"

    def _format_price(idx_name, val):
        if val is None:
            return "N/A"
        if idx_name == "공포/탐욕":
            return f"{val:.0f}"
        if idx_name == "원달러환율":
            return f"₩{val:,.1f}"
        if idx_name == "비트코인":
            return f"${val:,.0f}"
        return f"{val:,.2f}" if val < 1000 else f"{val:,.0f}"

    def _format_diff(idx_name, diff):
        if idx_name == "공포/탐욕" or diff is None:
            return ""
        if idx_name in ("코스피", "원달러환율"):
            return f"{diff:+,.2f}"
        if idx_name == "비트코인":
            return f"{diff:+,.0f}"
        return f"{diff:+,.2f}"

    cards = []
    if market_df is None or market_df.empty:
        for label in labels:
            cards.append(
                f"<div class='ti-card'><div class='ti-label'>{label}</div>"
                f"<div class='ti-price'>N/A</div>"
                f"<div class='ti-change' style='color:{MUTED};'>—</div></div>"
            )
    else:
        for idx_name, label in zip(indices, labels):
            row = market_df[market_df['종목'] == idx_name]
            if row.empty:
                cards.append(
                    f"<div class='ti-card'><div class='ti-label'>{label}</div>"
                    f"<div class='ti-price'>N/A</div>"
                    f"<div class='ti-change' style='color:{MUTED};'>—</div></div>"
                )
                continue

            val = float(row.iloc[0]['현재가'] or 0)
            change_str = str(row.iloc[0].get('등락', '0.00%'))
            diff = float(row.iloc[0].get('등락값', 0) or 0)

            # F&G는 rating 텍스트("Neutral" 등)가 change_str로 옴 — 색상 회색 고정
            if idx_name == "공포/탐욕":
                color = MUTED
                arrow = ""
                sub = change_str
            else:
                if diff > 0:
                    color, arrow = UP, "▲"
                elif diff < 0:
                    color, arrow = DOWN, "▼"
                else:
                    color, arrow = FLAT, "—"
                diff_str = _format_diff(idx_name, diff)
                sub = f"{arrow} {diff_str} ({change_str})" if diff_str else f"{arrow} {change_str}"

            cards.append(
                f"<div class='ti-card'>"
                f"<div class='ti-label'>{label}</div>"
                f"<div class='ti-price'>{_format_price(idx_name, val)}</div>"
                f"<div class='ti-change' style='color:{color};'>{sub}</div>"
                f"</div>"
            )

    html = (
        f"<style>"
        f".ti-grid {{ display:grid; grid-template-columns: repeat(7, minmax(0,1fr)); gap:8px; margin:4px 0 14px; }}"
        f".ti-card {{ background:#16181F; border:1px solid rgba(255,255,255,0.05); border-radius:10px;"
        f"           padding:10px 12px; min-width:0; }}"
        f".ti-label {{ font-size:11px; color:{MUTED}; letter-spacing:0.02em;"
        f"            white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}"
        f".ti-price {{ font-size:18px; font-weight:600; color:{MAIN}; margin:4px 0 2px; line-height:1.2;"
        f"            white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}"
        f".ti-change {{ font-size:11px; line-height:1.3; white-space:nowrap;"
        f"             overflow:hidden; text-overflow:ellipsis; }}"
        f"@media (max-width:900px) {{ .ti-grid {{ grid-template-columns: repeat(4, minmax(0,1fr)); }} }}"
        f"@media (max-width:560px) {{ .ti-grid {{ grid-template-columns: repeat(2, minmax(0,1fr)); }} }}"
        f"</style>"
        f"<div class='ti-grid'>{''.join(cards)}</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def render_fear_greed_bar(fg_value, status_text=""):
    """Fear & Greed 컴팩트 막대 — 그라데이션 바 위에 현재 위치 마커 (높이 ~60px)."""
    if fg_value is None:
        st.caption("시장 심리 데이터 없음")
        return

    pos = max(0, min(100, float(fg_value)))
    if pos <= 25:
        val_color = "#FF4B4B"
    elif pos <= 45:
        val_color = "#FFA500"
    elif pos <= 55:
        val_color = "#FFD700"
    elif pos <= 75:
        val_color = "#90EE90"
    else:
        val_color = "#00FFA3"

    st.markdown(
        f"<div style='margin:2px 0 6px;'>"
        f"<div style='display:flex; justify-content:space-between; align-items:baseline; margin-bottom:6px;'>"
        f"<span style='font-size:0.95rem; font-weight:700;'>🌋 시장 심리</span>"
        f"<span style='font-size:1.15rem; font-weight:700; color:{val_color};'>{pos:.0f} "
        f"<span style='font-size:0.75rem; color:#94A3B8; font-weight:400;'>{status_text}</span></span></div>"
        f"<div style='position:relative; height:8px; border-radius:4px; "
        f"background:linear-gradient(90deg,#FF4B4B,#FFA500,#FFD700,#90EE90,#00FFA3);'>"
        f"<div style='position:absolute; left:{pos}%; top:-3px; width:3px; height:14px; "
        f"background:#fff; border-radius:2px; transform:translateX(-50%); "
        f"box-shadow:0 0 4px rgba(0,0,0,0.6);'></div></div>"
        f"<div style='display:flex; justify-content:space-between; font-size:0.62rem; color:#5F5E5A; margin-top:3px;'>"
        f"<span>공포</span><span>중립</span><span>탐욕</span></div>"
        f"</div>",
        unsafe_allow_html=True,
    )


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


def _get_accounts() -> dict:
    """계정 목록 (환경변수 또는 기본값)."""
    import os
    return {
        os.getenv("APP_USERNAME", "admin"): os.getenv("APP_PASSWORD", "admin"),
        "song": os.getenv("APP_PASSWORD_SONG", "song"),
    }


def _auth_token(username: str) -> str:
    """비밀번호 기반 서명 토큰 — URL에 담아 새로고침 후 로그인 복원용.
    비밀번호 자체는 노출 안 되고(해시), 비번을 모르면 위조 불가."""
    import hashlib
    pw = _get_accounts().get(username, "")
    return hashlib.sha256(f"{username}:{pw}:stockagent-v1".encode()).hexdigest()[:20]


def try_restore_session():
    """URL 쿼리파라미터의 서명 토큰으로 로그인 상태 복원 (새로고침 재로그인 방지)."""
    if st.session_state.get("authenticated"):
        return
    try:
        u = st.query_params.get("u")
        t = st.query_params.get("t")
    except Exception:
        return
    if u and t and u in _get_accounts() and t == _auth_token(u):
        st.session_state.authenticated = True
        st.session_state.user_id = u


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
                accounts = _get_accounts()
                if username in accounts and password == accounts[username]:
                    st.session_state.authenticated = True
                    st.session_state.user_id = username  # 사용자 ID 저장
                    # 새로고침해도 유지되도록 URL에 서명 토큰 저장 (비번 노출 없음)
                    st.query_params["u"] = username
                    st.query_params["t"] = _auth_token(username)
                    st.rerun()
                else:
                    st.error("계정 정보가 일치하지 않습니다.")

        st.markdown("""
        <div style="text-align: center; margin-top: 20px; color: #475569; font-size: 12px;">
            © 2026 Stock Agent Terminal. All rights reserved.
        </div>
        """, unsafe_allow_html=True)
