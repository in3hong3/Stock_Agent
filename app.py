"""
Stock Agent — Streamlit 엔트리포인트.
탭별 구현은 ui/pages/ 모듈로 분리되어 있음.
"""
import streamlit as st
from pathlib import Path

# 모바일 반응형 CSS (가장 먼저)
mobile_css_path = Path(__file__).parent / "ui" / "mobile.css"
if mobile_css_path.exists():
    with open(mobile_css_path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

from config.settings import PAGE_ICON, AGENT_REGISTRY
from ui.theme import get_cached_fear_greed_index, get_heatmap_color, apply_theme, get_point_color
from ui.components import render_ticker_tape, render_login_page

from agents.rag_agent import RAGAgent
from agents.technical_agent import TechnicalAgent
from agents.news_agent import NewsAgent
from agents.router import AgenticRouter

from ui.pages.sidebar import render_side_panel
from ui.pages.tracker import render_tab_tracker
from ui.pages.paper import render_tab_paper
from ui.pages.journal import render_tab_journal
from ui.pages.admin import render_tab_admin
from ui.pages.analysts import (
    render_tab_rag, render_tab_quant, render_tab_tech,
    render_tab_news, render_tab_comprehensive,
)
from ui.pages.portfolio import render_tab_portfolio
from ui.pages.alerts import render_tab_alerts
from ui.pages.backtest import render_tab_backtest
from ui.pages.hot_sectors import render_tab_hot_sectors


def initialize_agents():
    if "agents" not in st.session_state:
        st.session_state.agents = {}
        for agent_id, agent_info in AGENT_REGISTRY.items():
            if not agent_info.get("enabled", True):
                continue
            agent_type = agent_info.get("type", "rag")
            if agent_type == "rag":
                st.session_state.agents[agent_id] = RAGAgent(
                    agent_id=agent_id,
                    name=agent_info["name"],
                    description=agent_info["description"],
                    channel_id=agent_info.get("channel_id"),
                )
            elif agent_type == "technical":
                st.session_state.agents[agent_id] = TechnicalAgent(
                    agent_id=agent_id,
                    name=agent_info["name"],
                    description=agent_info["description"],
                )
            elif agent_type == "news":
                st.session_state.agents[agent_id] = NewsAgent(
                    agent_id=agent_id,
                    name=agent_info["name"],
                    description=agent_info["description"],
                )

    if "agentic_router" not in st.session_state:
        with st.spinner("🔀 Agentic Router 초기화 중..."):
            st.session_state.agentic_router = AgenticRouter()


def main():
    st.set_page_config(
        page_title="Stock Agent Terminal",
        page_icon=PAGE_ICON,
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        render_login_page()
        st.stop()

    # 로그인 후 한 번만: 단일 사용자 데이터를 admin 폴더로 마이그레이션
    if not st.session_state.get("_migrated"):
        from utils.user_data import migrate_legacy_to_user
        moved = migrate_legacy_to_user("admin")
        if moved:
            print(f"마이그레이션 완료: {moved}")
        st.session_state["_migrated"] = True

    if "fg_index" not in st.session_state:
        st.session_state.fg_index, st.session_state.fg_status = get_cached_fear_greed_index()

    fg_index = st.session_state.fg_index
    fg_status = st.session_state.fg_status
    bg_color, text_color, emoji, status_text = get_heatmap_color(fg_index)
    point_color, point_text_color = get_point_color(fg_index)
    apply_theme(bg_color, text_color, point_color)

    st.markdown(f"""
    <style>
        .top-announcement-bar {{
            background-color: {point_color};
            color: {point_text_color} !important;
            padding: 10px 0; text-align: center; font-weight: 700;
            font-size: 14px; width: 100%; position: fixed; top: 0; left: 0;
            z-index: 999991; box-shadow: 0 4px 10px rgba(0,0,0,0.3);
            letter-spacing: -0.02em;
        }}
        [data-testid="stMetric"] {{ border-top: 3px solid {point_color} !important; }}
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {{
            border-left: 5px solid {point_color} !important;
        }}
        [data-testid="stChatMessageAvatarAssistant"] + div div {{ color: {point_color} !important; }}
        .main .block-container {{ padding-top: 4rem !important; }}

        /* ── 로딩(rerun) 인디케이터 강조 — 우상단에 크고 눈에 띄게 ── */
        [data-testid="stStatusWidget"] {{
            background: {point_color} !important;
            border-radius: 999px !important;
            padding: 6px 16px !important;
            box-shadow: 0 4px 14px rgba(0,0,0,0.45) !important;
            transform: scale(1.2);
            transform-origin: top right;
            font-size: 0 !important;            /* 영어 'Running...' 텍스트 숨김 (svg 아이콘은 유지) */
            display: inline-flex !important;
            align-items: center !important;
        }}
        [data-testid="stStatusWidget"]::after {{
            content: "로딩 중...";
            font-size: 13px !important;
            font-weight: 700;
            color: {point_text_color} !important;
            margin-left: 6px;
            white-space: nowrap;
        }}
        [data-testid="stStatusWidget"] svg {{ fill: {point_text_color} !important; }}
    </style>
    """, unsafe_allow_html=True)

    render_ticker_tape()
    st.divider()
    st.title("📊 Stock Agent Terminal")

    initialize_agents()

    col_main, col_side = st.columns([7, 3])

    with col_side:
        render_side_panel(fg_index, fg_status, status_text, point_color)

    with col_main:
        is_admin = st.session_state.get("user_id") == "admin"
        tab_labels = [
            "📌 내 종목",
            "🗞️ 데일리",
            "🔥 핫 섹터",
            "🤖 분석관",
            "💼 내 포트폴리오",
            "📒 매매일지",
            "🔔 가격 알림",
            "🧪 백테스트",
        ]
        if is_admin:
            tab_labels.append("🔧 관리자")

        all_tabs = st.tabs(tab_labels)
        (tab_tracker, tab_paper, tab_hot, tab_analysts, tab_portfolio,
         tab_journal, tab_alerts, tab_backtest) = all_tabs[:8]

        with tab_tracker:
            render_tab_tracker()
        with tab_paper:
            render_tab_paper()
        with tab_hot:
            render_tab_hot_sectors()
        with tab_analysts:
            sub_rag, sub_quant, sub_tech, sub_news, sub_comp = st.tabs([
                "🎥 영상분석 (RAG)",
                "📊 밸류에이션",
                "📈 기술분석 (차트)",
                "📰 뉴스분석",
                "🔀 종합분석",
            ])
            with sub_rag:
                render_tab_rag()
            with sub_quant:
                render_tab_quant()
            with sub_tech:
                render_tab_tech()
            with sub_news:
                render_tab_news()
            with sub_comp:
                render_tab_comprehensive()
        with tab_portfolio:
            render_tab_portfolio()
        with tab_journal:
            render_tab_journal()
        with tab_alerts:
            render_tab_alerts()
        with tab_backtest:
            render_tab_backtest()
        if is_admin:
            with all_tabs[8]:
                render_tab_admin()


if __name__ == "__main__":
    main()
