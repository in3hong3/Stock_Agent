"""포트폴리오 탭 + 5개 서브탭."""
import os
import traceback
import pandas as pd
import streamlit as st

from ui.components import render_chat_sources
from utils.sector_classifier import SectorClassifier
from utils.portfolio_visualizer import PortfolioVisualizer
from utils.portfolio_utils import calc_portfolio_metrics
from ui.pages._meta import (
    load_meta, save_meta, save_price_timestamp, load_price_timestamp, load_cash,
    auto_fill_missing_prices,
)


def _render_subtab_detail(data):
    st.subheader("📋 보유 종목 상세")
    for analysis in data.get("stock_analyses", []):
        with st.expander(f"**{analysis['name']}** ({analysis['ticker']})", expanded=False):
            info = analysis.get("current_info", {})
            ticker_str = analysis["ticker"]
            if ticker_str.endswith(".KS") or ticker_str.endswith(".KQ"):
                symbol = "₩"
            elif ticker_str.endswith(".T"):
                symbol = "¥"
            else:
                symbol = "$"

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("보유 수량", f"{info.get('quantity', 0):,}주")
                st.metric("평균 매수가 (KRW)", f"₩{info.get('avg_price', 0):,.0f}")
            with col2:
                st.metric("현재가 (Native)", f"{symbol}{info.get('current_price', 0):,.2f}")
                krw_eval = info.get("quantity", 0) * info.get("current_price_krw", info.get("current_price", 0))
                st.metric("평가금액 (KRW)", f"₩{krw_eval:,.0f}")
            with col3:
                st.metric(
                    "평가손익 (KRW)",
                    f"₩{info.get('profit_loss', 0):,.0f}",
                    delta=f"{info.get('profit_rate', 0):.2f}%",
                )

            st.markdown("---")
            st.markdown("### 🤖 AI 투자 피드백")
            feedback = analysis.get("ai_feedback", "")
            if feedback:
                st.markdown(feedback)
            else:
                st.info("AI 피드백을 생성할 수 없습니다.")

            rag_insights = analysis.get("rag_insights", [])
            if rag_insights:
                st.markdown("### 📺 관련 YouTube 분석")
                for idx, insight in enumerate(rag_insights[:3], 1):
                    meta = insight.get("metadata", {})
                    st.markdown(
                        f"**{idx}. {meta.get('영상제목', 'N/A')}**  \n"
                        f"채널: {meta.get('채널명', 'N/A')} | 업로드: {meta.get('업로드일자', 'N/A')}  \n"
                        f"[영상 보기]({meta.get('영상링크', '#')})"
                    )


def _render_subtab_viz(edited_df):
    st.subheader("📊 포트폴리오 시각화 분석")
    with st.spinner("섹터 분류 및 시각화 준비 중..."):
        try:
            classifier = SectorClassifier()
            df_for_viz = calc_portfolio_metrics(edited_df)
            df_classified = classifier.classify_portfolio(df_for_viz, delay_seconds=0.1)
            sector_summary = classifier.get_sector_summary(df_classified)
            visualizer = PortfolioVisualizer()

            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(visualizer.create_sector_pie_chart(df_classified, sector_summary), use_container_width=True)
            with col2:
                st.plotly_chart(visualizer.create_profit_bar_chart(df_classified), use_container_width=True)

            st.markdown("---")
            st.plotly_chart(visualizer.create_treemap(df_classified), use_container_width=True)
            st.markdown("---")

            col3, col4 = st.columns(2)
            with col3:
                st.plotly_chart(visualizer.create_allocation_sunburst(df_classified), use_container_width=True)
            with col4:
                st.plotly_chart(visualizer.create_sector_performance_chart(df_classified, sector_summary), use_container_width=True)
        except Exception as e:
            st.error(f"❌ 시각화 생성 실패: {e}")
            st.code(traceback.format_exc())


def _render_subtab_alerts(edited_df):
    st.subheader("🔔 포트폴리오 알림")
    if st.button("🔍 알림 확인", use_container_width=True):
        with st.spinner("알림 확인 중..."):
            try:
                from modules.portfolio_alert import PortfolioAlert
                from core.rag_engine import RAGEngine
                rag_engine = RAGEngine()
                alert_system = PortfolioAlert(rag_engine)
                alerts = alert_system.check_portfolio_alerts(calc_portfolio_metrics(edited_df), days_back=7)
                st.markdown(alert_system.format_alerts(alerts))
            except Exception as e:
                st.error(f"❌ 알림 확인 실패: {e}")


def _render_subtab_rebalance(edited_df):
    st.subheader("⚖️ 포트폴리오 리밸런싱 제안")
    if st.button("📊 리밸런싱 분석", use_container_width=True):
        with st.spinner("리밸런싱 분석 중..."):
            try:
                from modules.portfolio_rebalancer import PortfolioRebalancer
                from core.rag_engine import RAGEngine
                rag_engine = RAGEngine()
                rebalancer = PortfolioRebalancer(rag_engine)
                result = rebalancer.generate_rebalancing_suggestions(calc_portfolio_metrics(edited_df))

                if result["status"] == "success":
                    rebal_tab1, rebal_tab2, rebal_tab3 = st.tabs(["📊 분석 결과", "📈 효율적 투자선", "💰 비용 시뮬레이션"])
                    balance = result["current_balance"]

                    with rebal_tab1:
                        st.markdown("### 📊 현재 포트폴리오 균형")
                        col1, col2, col3 = st.columns(3)
                        col1.metric("총 평가금액", f"${balance['total_value']:,.0f}")
                        col2.metric("평균 수익률", f"{balance['risk_metrics']['avg_profit_rate']:.2f}%")
                        col3.metric("손실 종목 비율", f"{balance['risk_metrics']['losing_stocks_ratio']:.1f}%")
                        st.markdown("#### 섹터별 비중")
                        sector_data = pd.DataFrame([
                            {"섹터": s, "비중 (%)": w} for s, w in balance["sector_weights"].items()
                        ])
                        st.bar_chart(sector_data.set_index("섹터"))
                        st.markdown("---")
                        st.markdown("### 💡 리밸런싱 제안")
                        st.markdown(result["suggestions"]["full_text"])

                    with rebal_tab2:
                        st.subheader("📈 Efficient Frontier (효율적 투자선)")
                        opt_result = result.get("optimization", {})
                        if opt_result.get("success"):
                            import plotly.graph_objects as go
                            frontier = opt_result["frontier"]
                            curr = opt_result["current_metrics"]
                            fig = go.Figure()
                            fig.add_trace(go.Scatter(
                                x=frontier["Volatility"], y=frontier["Returns"], mode="markers",
                                marker=dict(color=frontier["Sharpe"], colorscale="Viridis",
                                            showscale=True, colorbar=dict(title="Sharpe Ratio"), size=5),
                                name="Simulation",
                            ))
                            fig.add_trace(go.Scatter(
                                x=[opt_result["volatility"]], y=[opt_result["returns"]], mode="markers",
                                marker=dict(color="red", size=15, symbol="star"), name="Max Sharpe",
                            ))
                            fig.add_trace(go.Scatter(
                                x=[curr["volatility"]], y=[curr["returns"]], mode="markers",
                                marker=dict(color="blue", size=15, symbol="diamond"), name="My Portfolio",
                            ))
                            fig.update_layout(title="Risk vs Return Profile",
                                              xaxis_title="Volatility (Risk)",
                                              yaxis_title="Expected Annual Return", height=500)
                            st.plotly_chart(fig, use_container_width=True)
                            st.info(
                                f"**내 포트폴리오**: 수익률 {curr['returns']*100:.1f}%, "
                                f"변동성 {curr['volatility']*100:.1f}%, Sharpe {curr['sharpe_ratio']:.2f}\n\n"
                                f"**최적 포트폴리오**: 수익률 {opt_result['returns']*100:.1f}%, "
                                f"변동성 {opt_result['volatility']*100:.1f}%, Sharpe {opt_result['sharpe_ratio']:.2f}"
                            )
                        else:
                            st.warning("최적화 데이터를 불러올 수 없습니다.")

                    with rebal_tab3:
                        st.subheader("💰 리밸런싱 비용 시뮬레이션")
                        sim_result = result.get("simulation", {})
                        if sim_result:
                            col1, col2 = st.columns(2)
                            col1.metric("예상 총 비용 (수수료+세금)", f"{sim_result['total_cost']:,.0f}원")
                            col2.metric("비용 비율", f"{sim_result['cost_ratio']:.2f}%")
                            st.markdown("#### 📋 상세 거래 내역")
                            details = pd.DataFrame(sim_result["details"])
                            if not details.empty:
                                st.dataframe(
                                    details[["ticker", "action", "diff", "cost"]].style.format(
                                        {"diff": "{:,.0f}", "cost": "{:,.0f}"}
                                    )
                                )
                            else:
                                st.info("리밸런싱이 필요하지 않습니다.")
                        else:
                            st.info("시뮬레이션 결과가 없습니다.")
                else:
                    st.error(f"❌ 리밸런싱 분석 실패: {result.get('message', '알 수 없는 오류')}")
            except Exception as e:
                st.error(f"❌ 리밸런싱 분석 실패: {e}")


def _render_subtab_personal_chat(edited_df):
    st.subheader("💬 개인화 투자 조언 챗봇")
    st.caption("보유 종목 정보를 활용한 맞춤형 투자 조언")

    if "personalized_rag_messages" not in st.session_state:
        st.session_state.personalized_rag_messages = []

    if "personalized_rag_engine" not in st.session_state:
        try:
            from core.personalized_rag import PersonalizedRAG
            from core.rag_engine import RAGEngine
            st.session_state.personalized_rag_engine = PersonalizedRAG(RAGEngine())
        except Exception as e:
            st.error(f"개인화 RAG 초기화 실패: {e}")

    user_query = st.chat_input("질문을 입력하세요 (예: 내가 보유한 AI 종목들 어때?)", key="personalized_rag_input")

    if user_query:
        st.session_state.personalized_rag_messages.append({"role": "user", "content": user_query})
        with st.spinner("답변 생성 중..."):
            try:
                history = st.session_state.personalized_rag_messages[-6:] or None
                result = st.session_state.personalized_rag_engine.chat(
                    query=user_query, top_k=10, temperature=0.7,
                    conversation_history=history, use_portfolio_context=True,
                )
                st.session_state.personalized_rag_messages.append({
                    "role": "assistant",
                    "content": result["answer"],
                    "sources": result.get("sources", []),
                    "related_holdings": result.get("related_holdings", []),
                    "followup_questions": result.get("followup_questions", []),
                })
            except Exception as e:
                st.session_state.personalized_rag_messages.append({
                    "role": "assistant", "content": f"오류 발생: {e}"
                })

    if st.session_state.personalized_rag_messages:
        for message in reversed(st.session_state.personalized_rag_messages):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if message["role"] == "assistant":
                    holdings = message.get("related_holdings", [])
                    if holdings:
                        with st.expander("💼 관련 보유 종목"):
                            for stock in holdings:
                                c1, c2, c3 = st.columns(3)
                                c1.write(f"**{stock['name']}** ({stock['ticker']})")
                                c2.write(f"{stock['quantity']:,}주")
                                c3.write(f"{stock['profit_rate']:.1f}%")
                    if message.get("sources"):
                        render_chat_sources(message["sources"])
    else:
        st.info("👆 위에서 질문을 입력하세요!")


def render_tab_portfolio():
    from utils.user_data import portfolio_path, current_user
    st.header(f"💼 내 포트폴리오 — {current_user()}")
    st.caption("개인 보유 종목 — 로그인한 계정별로 따로 저장됩니다.")

    if "portfolio_data" not in st.session_state:
        st.session_state.portfolio_data = None

    PORTFOLIO_FILE = portfolio_path()
    st.subheader("📊 포트폴리오 관리")

    # 빈 가격 자동 채움 (세션당 1회, 트래커와 별도 키)
    auto_fill_missing_prices(session_key="_auto_price_fill_done_portfolio")

    if not os.path.exists(PORTFOLIO_FILE):
        st.info(f"📁 아직 포트폴리오가 비어있습니다. 종목을 추가하거나 샘플로 시작하세요.")
        if st.button("📁 샘플 파일 생성"):
            os.makedirs(os.path.dirname(PORTFOLIO_FILE), exist_ok=True)
            with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
                f.write("ticker,name,quantity,avg_price,current_price\n")
                f.write("TSLA,테슬라,10,200,250\n")
                f.write("NVDA,엔비디아,2,400,600\n")
            st.success("✅ 샘플 파일이 생성되었습니다!")
            st.rerun()
        return

    if "df_portfolio" not in st.session_state or st.session_state.get("reload_csv", False):
        st.session_state.df_portfolio = pd.read_csv(PORTFOLIO_FILE)
        st.session_state.reload_csv = False

    st.markdown("**➕ 종목 추가** — 행을 추가해 입력하세요. 티커/종목명·현재가는 자동 조회됩니다.")

    if "qa_editor_ver" not in st.session_state:
        st.session_state.qa_editor_ver = 0

    qa_template = pd.DataFrame({
        "종목": pd.Series(dtype="str"),
        "수량": pd.Series(dtype="float"),
        "평단가": pd.Series(dtype="float"),
    })
    qa_df = st.data_editor(
        qa_template,
        num_rows="dynamic",
        use_container_width=True,
        key=f"quick_add_editor_{st.session_state.qa_editor_ver}",
        column_config={
            "종목": st.column_config.TextColumn("종목", help="티커 또는 한글명 (예: 엔비디아, 005930, TSLA)", required=True),
            "수량": st.column_config.NumberColumn("수량", help="비우면 1"),
            "평단가": st.column_config.NumberColumn("평단가", help="비우면 현재가로 설정"),
        },
    )

    if st.button("➕ 일괄 추가", use_container_width=True, key="qa_submit"):
        from modules.issue_tracker import resolve_ticker
        import yfinance as yf

        df_pf = st.session_state.df_portfolio
        added, failed = [], []

        rows = qa_df.dropna(subset=["종목"])
        rows = rows[rows["종목"].astype(str).str.strip() != ""]

        if rows.empty:
            st.warning("추가할 종목을 입력하세요.")
        else:
            with st.spinner("종목 조회 중..."):
                for _, row in rows.iterrows():
                    name_input = str(row["종목"]).strip()
                    qty = float(row["수량"]) if pd.notna(row["수량"]) and row["수량"] > 0 else 1.0
                    avg = float(row["평단가"]) if pd.notna(row["평단가"]) and row["평단가"] > 0 else 0.0

                    try:
                        ticker = resolve_ticker(name_input)
                        if ticker in df_pf["ticker"].astype(str).values:
                            failed.append((name_input, "이미 포트폴리오에 있음"))
                            continue
                        tk = yf.Ticker(ticker)
                        hist = tk.history(period="5d")
                        if hist.empty:
                            failed.append((name_input, f"'{ticker}' 데이터 없음"))
                            continue
                        current = float(hist["Close"].iloc[-1])
                        stock_name = tk.info.get("shortName") or name_input
                        df_pf = pd.concat([df_pf, pd.DataFrame([{
                            "ticker": ticker, "name": stock_name,
                            "quantity": qty,
                            "avg_price": avg if avg > 0 else current,
                            "current_price": current,
                        }])], ignore_index=True)
                        added.append(f"{stock_name} ({ticker})")
                    except Exception as e:
                        failed.append((name_input, str(e)))

            if added:
                st.session_state.df_portfolio = df_pf
                df_pf.to_csv(PORTFOLIO_FILE, index=False)
                save_price_timestamp()
                st.session_state.qa_editor_ver += 1
                st.success(f"✅ {len(added)}개 추가: {', '.join(added)}")
            for name, reason in failed:
                st.warning(f"⚠️ {name}: {reason}")
            if added:
                st.rerun()

    st.markdown("---")
    ic1, ic2 = st.columns([3, 2])
    with ic1:
        st.info("💡 표에서 수정하고 아래 **'💾 변경사항 저장'** 버튼을 눌러주세요. 저장 전까진 CSV에 반영되지 않습니다. 행 삭제는 왼쪽 체크 후 Delete 키.")
    with ic2:
        st.info(f"🕐 **현재가 기준**: {load_price_timestamp()}  \n"
                f"(yfinance 시세 — 장중 약 15분 지연, 장 마감 후엔 종가)")

    _CORE_COLS = ["ticker", "name", "quantity", "avg_price", "current_price"]

    st.caption("✏️ **티커 · 종목명 · 수량 · 평균 매입가** = 직접 입력 | 🔒 **현재가 · 평가금액** = 자동 (가격 업데이트 버튼) | "
               "금액 입력: 미국 주식 **$ 달러** / 한국 주식(.KS) **₩ 원화** 기준")

    editor_input = st.session_state.df_portfolio.copy()
    # Ensure numeric columns have no NaN to prevent UI display issues
    for col in ["quantity", "avg_price", "current_price"]:
        if col in editor_input.columns:
            editor_input[col] = pd.to_numeric(editor_input[col], errors='coerce').fillna(0)
    editor_input["평가금액"] = editor_input["quantity"] * editor_input["current_price"]

    edited_df = st.data_editor(
        editor_input,
        num_rows="dynamic",
        use_container_width=True,
        key="portfolio_editor",
        column_config={
            "ticker": st.column_config.TextColumn("✏️ 티커", help="직접 입력 — 예: AAPL, 005930.KS"),
            "name": st.column_config.TextColumn("✏️ 종목명", help="직접 입력"),
            "quantity": st.column_config.NumberColumn("✏️ 수량", min_value=0, help="직접 입력 — 보유 주식 수"),
            "avg_price": st.column_config.NumberColumn("✏️ 평균 매입가 ($)", min_value=0, format="%.2f",
                                                       help="직접 입력 — 나무 앱의 '매입단가'. 미국 주식은 달러, 한국 주식은 원화로"),
            "current_price": st.column_config.NumberColumn("🔒 현재가 ($)", min_value=0, format="%.2f",
                                                           help="자동 — '📡 가격 업데이트' 버튼으로 갱신"),
            "평가금액": st.column_config.NumberColumn("🔒 평가금액 ($)", format="%.2f", disabled=True,
                                                  help="자동 계산 — 수량 × 현재가"),
        },
    )

    edited_df = edited_df[_CORE_COLS].copy()

    # 변경사항이 있으면 저장 버튼 노출 (자동 저장 X — 사용자 명시 저장 시에만 CSV 반영).
    has_unsaved = not edited_df.equals(st.session_state.df_portfolio[_CORE_COLS])
    sc1, sc2 = st.columns([3, 1])
    with sc1:
        if has_unsaved:
            st.warning("⚠️ 저장되지 않은 변경사항이 있습니다.")
        else:
            st.success("✅ 모든 변경사항이 저장된 상태입니다.")
    with sc2:
        if st.button("💾 변경사항 저장", type="primary", use_container_width=True,
                     disabled=not has_unsaved, key="save_portfolio_btn"):
            edited_df.to_csv(PORTFOLIO_FILE, index=False)
            st.session_state.df_portfolio = edited_df.copy()
            # 트래커의 cached_snapshot / cached_signals 등 가격·수량 의존 캐시 무효화
            st.cache_data.clear()
            # 다음 트래커 진입에 자동 가격 채움이 다시 돌도록 가드 해제
            for key in ("_auto_price_fill_done", "_auto_price_fill_done_portfolio"):
                st.session_state.pop(key, None)
            st.toast("💾 저장 완료 — '📌 내 종목' 탭에 즉시 반영")
            st.rerun()

    # ── 🗑️ 종목 삭제 (드롭다운에서 골라 즉시 삭제) ──
    _df_cur = st.session_state.df_portfolio
    if not _df_cur.empty and "ticker" in _df_cur.columns:
        with st.expander("🗑️ 종목 삭제"):
            _name_by_tk = {
                str(r["ticker"]): str(r.get("name") or r["ticker"])
                for _, r in _df_cur.dropna(subset=["ticker"]).iterrows()
            }
            del_sel = st.multiselect(
                "삭제할 종목 선택 (복수 가능)",
                options=list(_name_by_tk.keys()),
                format_func=lambda t: f"{_name_by_tk.get(t, t)} ({t})",
                key="portfolio_delete_sel",
            )
            if st.button("🗑️ 선택 종목 삭제", disabled=not del_sel, key="portfolio_delete_btn"):
                kept = _df_cur[~_df_cur["ticker"].astype(str).isin(del_sel)].copy()
                kept.to_csv(PORTFOLIO_FILE, index=False)
                st.session_state.df_portfolio = kept
                st.cache_data.clear()
                for key in ("_auto_price_fill_done", "_auto_price_fill_done_portfolio"):
                    st.session_state.pop(key, None)
                st.success(f"🗑️ {len(del_sel)}개 종목 삭제 완료")
                st.rerun()

    try:
        from modules.issue_tracker import get_usdkrw_rate

        @st.cache_data(ttl=600)
        def cached_fx():
            return get_usdkrw_rate()

        fx = cached_fx()
        import numpy as np
        df_t = edited_df.dropna(subset=["ticker"]).copy()
        # 가격/수량/평단이 비어있는 행을 NaN 그대로 두면 sum이 깨지므로 0으로 처리
        for col in ("quantity", "avg_price", "current_price"):
            df_t[col] = pd.to_numeric(df_t[col], errors="coerce").fillna(0)
        missing_price_n = int((df_t["current_price"] <= 0).sum())

        is_kr = df_t["ticker"].astype(str).str.endswith((".KS", ".KQ"))
        fx_factor = np.where(is_kr, 1.0, fx)
        df_t["_eval_krw"] = df_t["quantity"] * df_t["current_price"] * fx_factor
        df_t["_cost_krw"] = df_t["quantity"] * df_t["avg_price"] * fx_factor

        stock_eval = float(df_t["_eval_krw"].sum())
        total_cost = float(df_t["_cost_krw"].sum())
        total_pnl = stock_eval - total_cost
        pnl_rate = (total_pnl / total_cost * 100) if total_cost > 0 else 0

        cash = load_cash()
        cash_krw_total = cash["krw"] + cash["usd"] * fx
        total_asset = stock_eval + cash_krw_total
        cash_ratio = (cash_krw_total / total_asset * 100) if total_asset > 0 else 0

        if missing_price_n:
            st.warning(
                f"⚠️ 현재가가 비어있는 종목이 {missing_price_n}개 있어 평가액이 정확하지 않습니다. "
                f"아래 **'📡 가격 업데이트'** 버튼을 눌러 주세요."
            )

        suffix = " ⚠️" if missing_price_n else ""
        tc1, tc2, tc3, tc4 = st.columns(4)
        tc1.metric("💰 총 자산 (주식+현금)", f"₩{total_asset:,.0f}{suffix}", delta=f"${total_asset / fx:,.0f}")
        tc2.metric("📈 주식 평가액", f"₩{stock_eval:,.0f}{suffix}", delta=f"손익 {pnl_rate:+.2f}%")
        tc3.metric("💵 현금", f"₩{cash_krw_total:,.0f}", delta=f"비중 {cash_ratio:.1f}%")
        tc4.metric("총 매입액", f"₩{total_cost:,.0f}")
        st.caption(f"환율 적용: $1 = ₩{fx:,.1f} (미국 주식·달러 현금은 원화 환산 합산)")

        meta_for_seed = load_meta()
        cur_seed = float(meta_for_seed.get("trading_seed", 0) or 0)
        cur_risk = float(meta_for_seed.get("risk_pct", 1.0) or 1.0)
        with st.expander(f"💰 트레이딩 시드 / 리스크 설정 (현재: ${cur_seed:,.0f} · {cur_risk}% 룰)"):
            st.caption("📌 매매 시그널에서 미너비니식 자동 포지션 사이징(권장 매수 수량)을 계산할 때 사용합니다. "
                       "1회 매매에 시드의 N%만 잃을 수 있게 매수 수량이 자동 조정됩니다.")
            with st.form("seed_form"):
                sd1, sd2, sd3 = st.columns([2, 2, 1])
                with sd1:
                    seed_in = st.text_input("매매 시드 ($)", value=f"{cur_seed:.0f}",
                                            help="실제 매매에 쓸 수 있는 금액")
                with sd2:
                    risk_in = st.text_input("1회 리스크 (%)", value=f"{cur_risk}",
                                            help="기본 1% — 미너비니 추천. 보수: 0.5%, 공격: 2%")
                with sd3:
                    st.write("")
                    if st.form_submit_button("💾 저장", use_container_width=True):
                        try:
                            new_seed = float(seed_in.replace(",", "") or 0)
                            new_risk = float(risk_in or 1.0)
                            save_meta(trading_seed=new_seed, risk_pct=new_risk)
                            st.cache_data.clear()
                            st.toast(f"💾 시드 ${new_seed:,.0f} · 리스크 {new_risk}% 저장")
                            st.rerun()
                        except ValueError:
                            st.error("숫자만 입력하세요")

        with st.expander(f"💵 보유 현금 입력 (현재: ₩{cash['krw']:,.0f} + ${cash['usd']:,.2f})"):
            with st.form("cash_form"):
                cf1, cf2, cf3 = st.columns([2, 2, 1])
                with cf1:
                    cash_krw_in = st.text_input("원화 현금 (₩)", value=f"{cash['krw']:.0f}")
                with cf2:
                    cash_usd_in = st.text_input("달러 현금 ($)", value=f"{cash['usd']:.2f}")
                with cf3:
                    st.write("")
                    cash_submit = st.form_submit_button("💾 저장", use_container_width=True)
            if cash_submit:
                try:
                    new_krw = float(cash_krw_in.replace(",", "") or 0)
                    new_usd = float(cash_usd_in.replace(",", "") or 0)
                    save_meta(cash_krw=new_krw, cash_usd=new_usd)
                    st.toast("💾 현금 저장됨")
                    st.rerun()
                except ValueError:
                    st.error("숫자만 입력하세요. (콤마는 허용)")
    except Exception as e:
        st.warning(f"총 평가액 계산 실패: {e}")

    col3, col4 = st.columns(2)
    with col3:
        if st.button("📡 가격 업데이트", use_container_width=True, help="yfinance로 실시간 가격 업데이트"):
            from utils.loading import ProgressBanner
            try:
                with ProgressBanner(
                    title=f"{len(edited_df)}개 종목 실시간 가격 조회 중",
                    total=2, icon="📡",
                ) as banner:
                    banner.step("yfinance에 시세 요청 중...")
                    from utils.price_updater import PriceUpdater
                    updater = PriceUpdater()
                    updated_df = updater.update_portfolio_prices(edited_df, delay_seconds=0.3)
                    banner.step("CSV에 저장 중...")
                    updater.save_portfolio(updated_df, PORTFOLIO_FILE)
                    banner.done("✅ 가격 업데이트 완료!")
                st.session_state.df_portfolio = updated_df
                st.session_state.reload_csv = True
                save_price_timestamp()
                st.rerun()
            except Exception as e:
                st.error(f"❌ 가격 업데이트 실패: {e}")
    with col4:
        if st.button("🚀 분석 실행", type="secondary", use_container_width=True):
            with st.spinner("포트폴리오 분석 중..."):
                try:
                    from modules.portfolio_analyzer import PortfolioAnalyzer
                    from core.rag_engine import RAGEngine
                    analyzer = PortfolioAnalyzer(RAGEngine())
                    if not edited_df.empty:
                        result = analyzer.analyze_portfolio(calc_portfolio_metrics(edited_df))
                        if result["status"] == "success":
                            st.session_state.portfolio_data = result
                            st.success("✅ 분석 완료!")
                        else:
                            st.error(f"❌ 분석 실패: {result.get('message', '알 수 없는 오류')}")
                    else:
                        st.warning("⚠️ 포트폴리오 데이터가 비어 있습니다.")
                except Exception as e:
                    st.error(f"❌ 오류 발생: {e}")

    st.markdown("---")
    subtab1, subtab2, subtab3, subtab4, subtab5 = st.tabs(
        ["📋 종목 상세", "📊 시각화", "🔔 알림", "⚖️ 리밸런싱", "💬 개인화 챗봇"]
    )

    with subtab1:
        if st.session_state.portfolio_data:
            data = st.session_state.portfolio_data
            summary = data.get("summary", {})
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("보유 종목 수", f"{summary.get('total_stocks', 0)}개")
            col2.metric("총 평가액", f"₩{summary.get('total_evaluation', 0):,.0f}")
            col3.metric("총 평가손익", f"₩{summary.get('total_profit_loss', 0):,.0f}")
            col4.metric("평균 수익률", f"{summary.get('average_profit_rate', 0):.2f}%")
            top = summary.get("top_performer", {})
            worst = summary.get("worst_performer", {})
            c5, c6 = st.columns(2)
            c5.success(f"🏆 최고 수익: {top.get('name', 'N/A')} ({top.get('profit_rate', 0):.2f}%)")
            c6.error(f"📉 최저 수익: {worst.get('name', 'N/A')} ({worst.get('profit_rate', 0):.2f}%)")
            st.markdown("---")
            _render_subtab_detail(data)
        else:
            st.info("🚀 위에서 **분석 실행**을 눌러주세요.")

    with subtab2:
        _render_subtab_viz(edited_df)

    with subtab3:
        _render_subtab_alerts(edited_df)

    with subtab4:
        _render_subtab_rebalance(edited_df)

    with subtab5:
        _render_subtab_personal_chat(edited_df)
