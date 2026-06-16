"""매매일지 탭."""
import datetime
import streamlit as st


def render_tab_journal():
    from modules.trade_journal import (
        load_journal, add_trade, delete_trade, get_stats, apply_to_portfolio,
    )
    from modules.issue_tracker import resolve_ticker

    st.header("📒 매매일지")
    st.caption("매수/매도를 기록하면 실현손익·승률이 자동 집계됩니다. 포트폴리오 반영도 한 번에.")

    with st.form("trade_form", clear_on_submit=True):
        jc1, jc2, jc3, jc4, jc5 = st.columns([2, 2, 1.5, 1.5, 1.5])
        with jc1:
            t_date = st.date_input("날짜", value=datetime.date.today())
        with jc2:
            t_ticker = st.text_input("종목", placeholder="NVDA, 엔비디아, 005930")
        with jc3:
            t_side = st.selectbox("구분", ["매수", "매도"])
        with jc4:
            t_qty = st.text_input("수량", placeholder="10")
        with jc5:
            t_price = st.text_input("체결가", placeholder="450.50")

        t_memo = st.text_input("메모 (매매 이유 — 나중에 복기할 때 가장 중요합니다)",
                               placeholder="예: 실적 서프라이즈 + RSI 35 반등 구간 분할매수 1차")
        t_apply = st.checkbox("포트폴리오에 자동 반영 (수량/평단가 갱신)", value=True)
        t_submit = st.form_submit_button("✍️ 기록", use_container_width=True, type="primary")

    if t_submit:
        try:
            qty = float(t_qty.replace(",", ""))
            price = float(t_price.replace(",", ""))
            if not t_ticker.strip() or qty <= 0 or price <= 0:
                raise ValueError
        except ValueError:
            st.error("종목/수량/체결가를 올바르게 입력하세요.")
        else:
            ticker = resolve_ticker(t_ticker.strip())
            side = "buy" if t_side == "매수" else "sell"
            avg_price = None

            if t_apply:
                result = apply_to_portfolio(ticker, side, qty, price)
                if not result["success"]:
                    st.error(f"❌ {result['message']}")
                    st.stop()
                avg_price = result.get("avg_price")
                st.toast(f"💼 {result['message']}")

            row = add_trade(
                t_date.strftime("%Y-%m-%d"), ticker, t_ticker.strip(),
                side, qty, price, memo=t_memo.strip(), avg_price=avg_price,
            )
            if row.get("realized_pnl") is not None:
                pnl = row["realized_pnl"]
                emoji = "🎉" if pnl >= 0 else "📉"
                st.toast(f"{emoji} 실현손익: {pnl:+,.2f} 기록됨")
            st.cache_data.clear()
            st.rerun()

    stats = get_stats()
    if stats["n_trades"] == 0:
        st.info("👆 첫 거래를 기록해보세요. 매도 기록부터 실현손익이 집계됩니다.")
        return

    st.markdown("---")
    st.subheader("📊 매매 성과")
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    sc1.metric("총 거래", f"{stats['n_trades']}건")
    sc2.metric("실현손익 합계", f"{stats['total_realized']:+,.0f}")
    sc3.metric("승률", f"{stats['win_rate']}%" if stats["n_sells"] else "—",
               help="실현손익이 양수인 매도 비율")
    sc4.metric("평균 수익/손실", f"{stats['avg_win']:+,.0f} / {stats['avg_loss']:+,.0f}")
    sc5.metric("손익비", f"{stats['profit_factor']}" if stats["profit_factor"] else "—",
               help="평균 수익 ÷ 평균 손실. 1.5 이상이면 양호")

    if len(stats["monthly"]) > 0 or len(stats["by_ticker"]) > 0:
        gc1, gc2 = st.columns(2)
        with gc1:
            if len(stats["monthly"]) > 0:
                st.markdown("**월별 실현손익**")
                st.bar_chart(stats["monthly"])
        with gc2:
            if len(stats["by_ticker"]) > 0:
                st.markdown("**종목별 실현손익**")
                st.bar_chart(stats["by_ticker"])

    st.markdown("---")
    st.subheader("📋 거래 내역")
    journal = load_journal()
    display = journal.copy().iloc[::-1]
    display["side"] = display["side"].map({"buy": "🟢 매수", "sell": "🔴 매도"})
    display.columns = ["날짜", "티커", "종목명", "구분", "수량", "체결가", "매도시 평단", "실현손익", "메모"]
    st.dataframe(display, hide_index=True, use_container_width=True)

    with st.expander("🗑️ 기록 삭제"):
        del_idx = st.number_input(
            "삭제할 행 번호 (위 표에서 최신=0번이 아닌, 입력 순서 기준)",
            min_value=0, max_value=max(len(journal) - 1, 0), step=1, key="journal_del_idx",
        )
        old = journal.iloc[int(del_idx)] if len(journal) > 0 else None
        if old is not None:
            st.caption(f"선택됨: {old['date']} {old['ticker']} {old['side']} {old['quantity']}주 @ {old['price']}")
        if st.button("삭제 실행", key="journal_del_btn"):
            delete_trade(int(del_idx))
            st.rerun()
