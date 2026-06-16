"""전략 백테스트 탭."""
import pandas as pd
import streamlit as st


def render_tab_backtest():
    from modules.backtester import run_backtest, STRATEGIES

    st.header("🧪 전략 백테스트")
    st.caption("과거 데이터로 매매 전략을 시뮬레이션합니다. (일봉 종가 체결, 수수료 0.1% 가정)")

    bc1, bc2, bc3, bc4 = st.columns([2, 3, 2, 2])
    with bc1:
        bt_ticker = st.text_input("티커", value="NVDA", key="bt_ticker").strip().upper()
    with bc2:
        strat_label = st.selectbox("전략", list(STRATEGIES.values()), key="bt_strategy")
    with bc3:
        bt_period = st.selectbox("기간", ["1y", "2y", "5y", "10y"], index=1, key="bt_period")
    with bc4:
        bt_capital = st.number_input("초기 자본 ($)", min_value=100, value=10000, step=1000, key="bt_capital")

    strat_key = next(k for k, v in STRATEGIES.items() if v == strat_label)

    params = {}
    if strat_key == "rsi":
        pc1, pc2 = st.columns(2)
        params["rsi_buy"] = pc1.slider("매수 RSI (이하)", 10, 50, 30, key="bt_rsi_buy")
        params["rsi_sell"] = pc2.slider("매도 RSI (이상)", 50, 90, 70, key="bt_rsi_sell")

    if st.button("🚀 백테스트 실행", type="primary", use_container_width=True, key="bt_run"):
        if not bt_ticker:
            st.warning("티커를 입력하세요.")
            return
        with st.spinner(f"{bt_ticker} {bt_period} 백테스트 중..."):
            result = run_backtest(
                ticker=bt_ticker, strategy=strat_key, period=bt_period,
                initial_capital=bt_capital, params=params,
            )
            st.session_state.bt_result = result

    result = st.session_state.get("bt_result")
    if not result:
        st.info("👆 조건을 설정하고 백테스트를 실행하세요.")
        return
    if not result["success"]:
        st.error(f"❌ {result['error']}")
        return

    m = result["metrics"]
    st.markdown("---")
    st.subheader("📊 성과 요약")

    mc1, mc2, mc3, mc4 = st.columns(4)
    delta_vs_bh = m["total_return"] - m["bh_return"]
    mc1.metric("전략 수익률", f"{m['total_return']}%", delta=f"{delta_vs_bh:+.2f}%p vs B&H")
    mc2.metric("Buy & Hold", f"{m['bh_return']}%")
    mc3.metric("연환산 수익률 (CAGR)", f"{m['cagr']}%")
    mc4.metric("최대 낙폭 (MDD)", f"{m['mdd']}%")

    mc5, mc6, mc7 = st.columns(3)
    mc5.metric("샤프 비율", f"{m['sharpe']}")
    mc6.metric("승률", f"{m['win_rate']}%")
    mc7.metric("거래 횟수", f"{m['n_trades']}회")

    st.markdown("---")
    st.subheader("📈 자산 곡선 (전략 vs Buy & Hold)")
    st.line_chart(result["equity_curve"])

    st.subheader("📉 낙폭 (Drawdown)")
    st.area_chart(result["drawdown"])

    if result["trades"]:
        st.markdown("---")
        st.subheader(f"📋 거래 내역 ({len(result['trades'])}건)")
        trades_df = pd.DataFrame(result["trades"])
        st.dataframe(trades_df, hide_index=True, use_container_width=True)
    else:
        st.info("해당 기간 동안 완결된 거래가 없습니다.")

    st.caption("⚠️ 백테스트는 과거 데이터 기반 시뮬레이션이며 미래 수익을 보장하지 않습니다. "
               "슬리피지, 세금, 배당은 단순화되어 있습니다.")
