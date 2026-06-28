"""내 종목 트래커 탭."""
import datetime
import streamlit as st

from ui.pages._meta import load_meta, auto_fill_missing_prices


@st.cache_data(ttl=300)
def cached_candle_chart(ticker: str, period: str = "6mo"):
    """캔들차트 공용 캐시 (기술분석관과 동일 차트를 다른 탭에서 재사용)"""
    from utils.chart_builder import build_candlestick_chart
    return build_candlestick_chart(ticker, period)


def _render_accuracy_top_card():
    """시그널 적중률을 트래커 최상단 카드로 노출.

    채점 데이터가 0건이면 카드 자체를 숨김 (정보 없는 칸 차지 방지).
    """
    try:
        from modules.signal_tracker import get_accuracy_stats
        acc = get_accuracy_stats()
    except Exception as e:
        print(f"적중률 카드 로드 실패: {e}")
        return

    graded = acc.get("graded", 0)
    if graded == 0:
        return

    wr = acc.get("win_rate")
    br = acc.get("buy_avg_ret")
    total = acc.get("total", 0)
    pending = acc.get("pending", 0)

    setup_stats = acc.get("setup_stats") or {}
    best = worst = None
    if setup_stats:
        ranked = sorted(setup_stats.items(), key=lambda x: -x[1].get("win_rate", 0))
        best = ranked[0]
        if len(ranked) > 1:
            worst = ranked[-1]

    badge = ""
    if best:
        badge = (
            f"<span style='background:#00FFA322; color:#00FFA3; padding:2px 8px; "
            f"border-radius:4px; font-size:0.78rem; font-weight:700;'>"
            f"🏆 {best[0]} {best[1].get('win_rate', 0):.0f}%</span>"
        )
        if worst and worst[0] != best[0]:
            badge += (
                f" <span style='background:#FF4B4B22; color:#FF4B4B; padding:2px 8px; "
                f"border-radius:4px; font-size:0.78rem; font-weight:700;'>"
                f"⚠️ {worst[0]} {worst[1].get('win_rate', 0):.0f}%</span>"
            )

    wr_color = "#00FFA3" if (wr or 0) >= 60 else "#FFD700" if (wr or 0) >= 50 else "#FF4B4B"
    br_color = "#FF4B4B" if (br or 0) >= 0 else "#4B7BFF"
    wr_str = f"{wr:.0f}%" if wr is not None else "—"
    br_str = f"{br:+.1f}%" if br is not None else "—"

    st.markdown(
        f"<div style='background: linear-gradient(160deg, #142028, #16181F); "
        f"border: 1px solid #00FFA355; border-radius: 14px; padding: 14px 18px; margin-bottom: 12px;'>"
        f"<div style='display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px;'>"
        f"<div>"
        f"<div style='font-weight:700; font-size:0.95rem;'>"
        f"📈 내 시그널 적중률 "
        f"<span style='font-size:0.75rem; color:#94A3B8; font-weight:400;'>"
        f"채점 {graded}건 · 대기 {pending}건 · 누적 {total}건</span></div>"
        f"<div style='margin-top:6px; font-size:0.82rem; color:#94A3B8;'>"
        f"종합 적중률 <b style='color:{wr_color}; font-size:1.05rem;'>{wr_str}</b> · "
        f"매수 시그널 평균수익 "
        f"<b style='color:{br_color}; font-size:1.05rem;'>{br_str}</b>"
        f"</div></div>"
        f"<div>{badge}</div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )


def render_tab_tracker():
    from modules.issue_tracker import (
        get_portfolio_holdings,
        fetch_ticker_news, summarize_all_issues,
    )

    st.header("📌 내 종목 트래커")
    st.caption("내 포트폴리오(data/portfolio.csv) 종목을 자동 추적합니다. 종목 추가/수정은 '💼 내 포트폴리오' 탭에서 하세요.")

    # 빈 가격이 있으면 진입 시 1회 자동 채움 (성공하면 rerun 내부 호출)
    auto_fill_missing_prices()

    # 시그널 적중률 카드 (있을 때만)
    _render_accuracy_top_card()

    tracked = get_portfolio_holdings()
    if not tracked:
        st.info("📂 포트폴리오가 비어 있습니다. '💼 내 포트폴리오' 탭에서 종목을 추가하세요.")
        return

    # 자동 채움 후에도 남은 가격 누락 종목 (yfinance 실패 등) — 메트릭에 ⚠️ 표시용
    missing_price = [h for h in tracked if not h.get("current_price") or float(h.get("current_price", 0) or 0) <= 0]

    # 누락 종목이 있으면 사용자가 즉시 재시도 가능한 버튼 + 누락 종목 명시
    if missing_price:
        names = ", ".join(f"**{h.get('name') or h['ticker']}** ({h['ticker']})" for h in missing_price[:6])
        more = f" 외 {len(missing_price) - 6}개" if len(missing_price) > 6 else ""
        mc1, mc2 = st.columns([4, 1])
        with mc1:
            st.warning(
                f"⚠️ 현재가 자동 갱신 실패: {names}{more}. "
                f"일시적 yfinance 응답 누락일 가능성이 큽니다."
            )
        with mc2:
            if st.button("🔄 다시 시도", use_container_width=True, key="retry_price_fill"):
                # 가드 해제 → auto_fill_missing_prices가 다음 사이클에 다시 실행
                for k in ("_auto_price_fill_done", "_auto_price_fill_done_portfolio"):
                    st.session_state.pop(k, None)
                st.cache_data.clear()
                st.rerun()

    tickers = [it["ticker"] for it in tracked]

    holdings_key = tuple(
        (h["ticker"], h["quantity"], h["avg_price"], h.get("current_price", 0))
        for h in tracked
    )

    # ── 매매 시그널 (오늘 할 일/유튜버 알림은 오른쪽 사이드 패널로 이동) ──
    from modules.portfolio_advisor import PERSONAS
    signal_result = None
    trading_seed = 0.0
    risk_pct = 1.0
    try:
        from ui.pages._meta import resolve_stance, get_cached_signals
        stance = resolve_stance()
        meta_now = load_meta()
        trading_seed = float(meta_now.get("trading_seed", 0) or 0)
        risk_pct = float(meta_now.get("risk_pct", 1.0) or 1.0)
        signal_result = st.session_state.get("_signal_result")
        if signal_result is None:
            signal_result = get_cached_signals(holdings_key, stance, trading_seed, risk_pct)
    except Exception as e:
        print(f"시그널 계산 실패: {e}")


    # ── 📖 매수 기법 설명 (상세 시그널·오늘 할 일이 공통으로 쓰는 규칙) ──
    with st.expander("📖 매수 기법 — 이 시그널·오늘 할 일이 쓰는 규칙", expanded=False):
        st.markdown(
            "**매수 셋업** (점수 높을수록 강한 신호)\n"
            "- 🎯 **눌림목 매수** (45+): 주봉 상승추세 + 일봉이 MA20~50로 조정 + RSI 40~58. "
            "MACD 골든크로스면 +10 → *추세 속 조정에서 재진입*\n"
            "- 🚀 **저항 돌파** (38+): 단기 저항 돌파 + 거래량 130%↑ + ADX≥22. 52주 신고가 근접 +8\n"
            "- 🔄 **과매도 반등** (30+): RSI≤32 + 볼린저 하단. 강세 다이버전스 +15 · 200일선 위 +10 "
            "(아래면 '떨어지는 칼날' 감점)\n\n"
            "**매도 / 청산**\n"
            "- 🔴 **과열 익절**: RSI≥72 + 볼린저 상단 — 단 실적 엔진(EPS 성장) 강하면 '강세 모멘텀'으로 보유 (올랜도 킴식)\n"
            "- 📉 **추세 이탈 축소**: MA50 이탈 + MACD 음전\n\n"
            "**위에 얹히는 보정**\n"
            "- 🏷️ **밸류에이션 게이트**: 고평가→신규매수 신중 / 저평가→가산 (가중 큼)\n"
            "- 🌐 **시장 국면**(VIX·S&P 추세)으로 전체 점수 ±\n"
            "- ⚙️ **성향**(공격/중립/보수/전문가)별 매수 임계·손절폭·익절 기준 다름\n"
            "- 📐 **포지션 사이징** 미너비니 1% 리스크 룰 · **계단식 청산** 10/20/50일선 + 평단 −8% 하드스톱\n\n"
            "※ **오늘 할 일·상세 시그널 모두 같은 엔진**(trade_signal)을 씁니다. 참고용이며 투자 권유가 아닙니다."
        )

    # ── 🎯 상세 매매 시그널 ──
    if signal_result:
        regime = signal_result["regime"]
        with st.expander(f"🎯 상세 매매 시그널 — 시장 국면: {regime['label']}", expanded=False):
            st.caption(" · ".join(regime["detail"]) + f" → 전체 점수 보정 {regime['score_modifier']:+d}점")

            for s in signal_result["signals"]:
                profit_str = f"{s['profit_rate']:+.1f}%" if s.get("profit_rate") is not None else "—"
                st.markdown(
                    f"#### {s['icon']} {s['ticker']} — **{s['action']}**  "
                    f"<span style='font-size:0.85rem; color:#00FFA3;'>{s.get('setup', '')}</span>",
                    unsafe_allow_html=True,
                )
                val = s.get("valuation", {})
                vmap = {"저평가": "#00FFA3", "적정": "#94A3B8", "고평가": "#FF4B4B", "평가불가": "#64748B"}
                vcolor = vmap.get(val.get("verdict", "평가불가"), "#64748B")
                st.markdown(
                    f"<span style='font-size:0.85rem;'>🏷️ 밸류에이션: "
                    f"<b style='color:{vcolor};'>{val.get('verdict','?')}</b> "
                    f"<span style='color:#64748B; font-size:0.78rem;'>{val.get('note','')}</span></span>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<span style='font-size:0.8rem; color:#94A3B8;'>"
                    f"현재가 {s['price']:,.2f} · 수익률 {profit_str} · 점수 {s['adj_score']:+.0f} · "
                    f"주봉 {s.get('wk_trend','?')}추세 · {s.get('trend_regime','?')}(ADX {s.get('adx','?')}) · "
                    f"RSI {s.get('rsi','?')} · 변동성(ATR) {s.get('atr_pct','?')}%</span>",
                    unsafe_allow_html=True,
                )

                sg1, sg2 = st.columns([3, 2])
                with sg1:
                    st.markdown("**📋 판단 근거:**")
                    for pts, reason in s["reasons"]:
                        st.markdown(f"- {pts} {reason}")
                    for ex in s.get("extra", []):
                        st.markdown(f"- {ex}")
                with sg2:
                    st.markdown("**🎯 매매 플랜:**")
                    if s.get("entry"):
                        size_html = ""
                        if s.get("size_qty"):
                            size_html = (
                                f"<div style='margin-top:8px; padding-top:8px; "
                                f"border-top:1px dashed rgba(255,255,255,0.1); font-size:0.85rem;'>"
                                f"💰 <b>권장 매수</b>: <b style='color:#00FFA3'>{s['size_qty']:,}주</b> "
                                f"(투입 ${s['size_invest']:,.0f} · 시드 {s['size_weight_pct']}%)<br>"
                                f"<span style='color:#94A3B8; font-size:0.78rem;'>"
                                f"최대 손실 ${s['size_max_loss']:,.0f} ({risk_pct}% 리스크 룰)</span></div>"
                            )
                        st.markdown(
                            f"<div style='font-size:0.9rem; line-height:1.9;'>"
                            f"🟢 <b>진입</b>: {s['entry']:,.2f}<br>"
                            f"🛑 <b>손절</b>: {s['stop']:,.2f} "
                            f"<span style='color:#FF4B4B;'>({(s['stop']/s['entry']-1)*100:+.1f}%)</span><br>"
                            f"🎯 <b>목표</b>: {s['target']:,.2f} "
                            f"<span style='color:#00FFA3;'>({(s['target']/s['entry']-1)*100:+.1f}%)</span><br>"
                            f"⚖️ <b>손익비</b>: 1 : {s['rr']}</div>"
                            f"{size_html}",
                            unsafe_allow_html=True,
                        )
                        if trading_seed == 0:
                            st.caption("💡 포지션 사이징 활성화: 포트폴리오 탭 → '시드머니' 설정")
                    else:
                        st.markdown(f"- {s['plan']}")
                    if s.get("stop_price") and s.get("avg_price", 0) > 0:
                        st.caption(f"보유분 손절가(ATR): {s['stop_price']:,.2f} (평단 {s['avg_price']:,.2f})")

                    ladder = s.get("exit_ladder", {})
                    if ladder and s.get("avg_price", 0) > 0:
                        hard_stop_str = f"{ladder['hard_stop']:,.2f}" if ladder.get("hard_stop") else "—"
                        nxt = ladder.get("next_trigger")
                        nxt_html = ""
                        if nxt:
                            nxt_html = (
                                f"<div style='margin-top:4px; font-size:0.8rem; color:#FFD700;'>"
                                f"▶ 다음 트리거: <b>{nxt['label']} (MA{10 if nxt['label']=='1차' else 20 if nxt['label']=='2차' else 50})</b> "
                                f"{nxt['line']:,.2f} (현재가 {nxt['distance_pct']:+.1f}% 위) → {nxt['pct']}% 청산</div>"
                            )
                        st.markdown(
                            f"<div style='margin-top:8px; padding:8px 10px; background:rgba(168,85,247,0.08); "
                            f"border-left:3px solid #a855f7; border-radius:4px; font-size:0.8rem;'>"
                            f"<b>📊 계단식 청산</b> (미너비니식)<br>"
                            f"1차 {ladder['ladder_1']['line']:,.2f} → 30%<br>"
                            f"2차 {ladder['ladder_2']['line']:,.2f} → 30%<br>"
                            f"3차 {ladder['ladder_3']['line']:,.2f} → 40%<br>"
                            f"하드스톱 {hard_stop_str} (-8%)"
                            f"{nxt_html}"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

                    st.markdown(
                        f"<span style='font-size:0.78rem; color:#64748B;'>"
                        f"지지 {s['support']:,.1f} · 저항 {s['resistance']:,.1f} · "
                        f"MA50 {s['ma50']:,.1f} · MA200 {s.get('ma200','?')}</span>",
                        unsafe_allow_html=True,
                    )

                if st.toggle(f"📈 {s['ticker']} 차트 보기 (캔들+MA+볼린저+RSI+MACD)", key=f"sig_chart_{s['ticker']}"):
                    with st.spinner(f"{s['ticker']} 차트 로딩..."):
                        fig = cached_candle_chart(s["ticker"], "6mo")
                        if fig:
                            st.plotly_chart(fig, use_container_width=True, key=f"sig_fig_{s['ticker']}")
                        else:
                            st.warning("차트 데이터를 가져올 수 없습니다.")
                st.markdown("---")

            st.caption("⚠️ 규칙 기반 기술적 시그널입니다. 펀더멘탈·뉴스는 반영되지 않으니 AI 평가서와 함께 보세요. 투자 권유가 아닙니다.")

    # ── 📈 시그널 정확도 추적 (상세 expander — 카드는 위에 별도 노출) ──
    try:
        from modules.signal_tracker import get_accuracy_stats
        acc = get_accuracy_stats()
        with st.expander(
            f"📈 시그널 정확도 상세 — 기록 {acc.get('total', 0)}건 "
            f"(채점완료 {acc.get('graded', 0)} · 대기 {acc.get('pending', 0)})",
            expanded=False,
        ):
            st.caption("매일 생성된 시그널을 자동 저장하고, 10일 후 실제 가격으로 채점합니다. "
                       "데이터가 쌓이면 어떤 셋업이 잘 맞는지 보이고, 나중에 ML 학습 재료가 됩니다.")
            if acc.get("graded", 0) == 0:
                st.info(f"📝 예측을 기록하는 중입니다. 채점은 예측 10일 후부터 시작돼요. "
                        f"(현재 {acc.get('pending', 0)}건 대기 중)")
            else:
                ac1, ac2, ac3 = st.columns(3)
                wr = acc.get("win_rate")
                ac1.metric("종합 적중률", f"{wr}%" if wr is not None else "—",
                           help="목표 달성/하락 회피 = 적중, 손절/상승 놓침 = 실패")
                br = acc.get("buy_avg_ret")
                ac2.metric("매수 시그널 평균수익", f"{br:+.1f}%" if br is not None else "—")
                ac3.metric("채점 완료", f"{acc['graded']}건")

                if acc.get("setup_stats"):
                    st.markdown("**셋업별 성적:**")
                    for setup, st_ in sorted(acc["setup_stats"].items(), key=lambda x: -x[1]["win_rate"]):
                        st.markdown(f"- {setup} — 적중률 **{st_['win_rate']:.0f}%** "
                                    f"(n={st_['n']}), 평균수익 {st_['avg_ret']:+.1f}%")

                recent = acc.get("recent")
                if recent is not None and not recent.empty:
                    st.markdown("**최근 채점 결과:**")
                    show = recent[["pred_date", "ticker", "action", "setup", "outcome", "ret_pct"]].copy()
                    show.columns = ["예측일", "티커", "액션", "셋업", "결과", "수익률%"]
                    st.dataframe(show, hide_index=True, use_container_width=True)
    except Exception as e:
        print(f"정확도 추적 표시 실패: {e}")

    # ── 📈 자산 추이 차트 (숫자 요약은 오른쪽 사이드 '내 자산'으로 이동) ──
    try:
        from utils.portfolio_utils import load_asset_history

        history = load_asset_history()
        with st.expander(f"📈 자산 추이 ({len(history)}일 기록됨)", expanded=False):
            if len(history) >= 2:
                first, last = history["total"].iloc[0], history["total"].iloc[-1]
                change = (last / first - 1) * 100 if first > 0 else 0
                st.caption(
                    f"기록 시작 {history.index[0].strftime('%Y-%m-%d')} 대비 "
                    f"**{change:+.2f}%** (₩{last - first:+,.0f})"
                )
                st.area_chart(history[["total"]].rename(columns={"total": "총 자산 (₩)"}))
                st.line_chart(history[["stock", "cash"]].rename(
                    columns={"stock": "주식 (₩)", "cash": "현금 (₩)"}))
            else:
                st.info("접속할 때마다 그날의 총자산이 자동 기록됩니다. 이틀째부터 추이 그래프가 그려져요.")

        st.markdown("---")
    except Exception as e:
        st.warning(f"자산 추이 표시 실패: {e}")


    # ── 4. 이슈 브리핑 (원하는 종목만 선택, 복수 가능) ──
    # 종목 토글(st.pills) 시 페이지 전체가 rerun되며 회색 막이 길게 뜨던 것을 막기 위해
    # 이 블록만 @st.fragment로 격리 → 토글/브리핑이 이 박스 안에서만 갱신된다.
    st.markdown("---")

    @st.fragment
    def _issue_briefing():
        st.caption("브리핑할 종목 (탭해서 켜고 끄기 · 기본 전체)")
        sel_tickers = st.pills(
            "브리핑할 종목",
            options=tickers,
            selection_mode="multi",
            default=tickers,
            key="brief_tickers",
            label_visibility="collapsed",
        )
        bc1, bc2 = st.columns([1, 1])
        with bc1:
            brief_clicked = st.button("🤖 선택 종목 이슈 브리핑 생성", type="primary", use_container_width=True)
        with bc2:
            if st.button("🔄 시세/뉴스 새로고침", use_container_width=True):
                st.cache_data.clear()
                st.rerun(scope="app")  # 시세 등 페이지 전체 갱신은 앱 전체 rerun

        @st.cache_data(ttl=600)
        def cached_news(ticker):
            return fetch_ticker_news(ticker, max_news=6)

        if brief_clicked:
            if not sel_tickers:
                st.warning("브리핑할 종목을 1개 이상 선택하세요.")
            else:
                from utils.loading import ProgressBanner
                try:
                    with ProgressBanner(
                        title="이슈 브리핑 생성 중",
                        total=3, icon="🤖",
                    ) as banner:
                        banner.step(f"📰 {len(sel_tickers)}개 종목 뉴스 수집 중...")
                        holdings_news = {t: cached_news(t) for t in sel_tickers}
                        banner.step("✍️ AI가 종목별 이슈 분석 중...")
                        briefing = summarize_all_issues(holdings_news)
                        banner.step("📋 브리핑 정리 중...")
                        banner.done("✅ 브리핑 생성 완료!")
                    st.session_state.tracker_briefing = {
                        "text": briefing,
                        "time": datetime.datetime.now().strftime("%H:%M"),
                    }
                except Exception as e:
                    st.error(f"❌ 브리핑 생성 실패: {e}")

        if st.session_state.get("tracker_briefing"):
            b = st.session_state.tracker_briefing
            st.markdown(f"#### 📋 이슈 브리핑 <span style='font-size:0.8rem;color:#64748B;'>(생성: {b['time']})</span>", unsafe_allow_html=True)
            st.markdown(b["text"])

    _issue_briefing()

    # ── 🎤 유튜버 집단지성 (RAG 대본 데이터 집계, LLM 0) ──
    st.markdown("---")
    with st.expander("🎤 유튜버 집단지성 — 영상들이 내 종목을 어떻게 보나 (RAG 집계)", expanded=False):
        try:
            from modules.youtuber_consensus import (
                scan_summary_meta, consensus_for, radar, sentiment_shift,
            )

            @st.cache_data(ttl=1800)
            def _yt_rows():
                return scan_summary_meta()

            rows = _yt_rows()
            st.caption(f"수집된 유튜브 대본 분석 {len(rows):,}건 기준 · 영상 단위 집계")
            period = st.radio("기간", [30, 90, 0],
                              format_func=lambda d: (f"최근 {d}일" if d else "전체 기간"),
                              horizontal=True, key="yt_period", index=1)
            days = period or None

            st.markdown("**📊 내 종목 컨센서스** (영상들의 매수/중립/주의)")
            con = consensus_for(rows, tickers, days=days)
            for tk in tickers:
                c = con[tk]
                if c["total"] == 0:
                    st.caption(f"• {tk}: 해당 기간 언급 없음")
                    continue
                tone = ("🟢 매수 우위" if c["score"] > 20
                        else "🔴 주의 우위" if c["score"] < -20 else "⚪ 중립")
                st.markdown(f"- **{tk}** {tone} (점수 {c['score']:+d}) — "
                            f"매수 {c['buy']}·중립 {c['neutral']}·주의 {c['caution']} (영상 {c['total']})")

            shifts = sentiment_shift(rows, tickers)
            if shifts:
                st.markdown("**⚠️ 톤 전환 감지** (최근 2주 vs 이전)")
                for s in shifts:
                    arrow = "📈 매수쪽으로" if s["delta"] > 0 else "📉 신중쪽으로"
                    st.markdown(f"- **{s['ticker']}** {arrow}: 이전 {s['prior']:+d} → 최근 {s['recent']:+d}")

            st.markdown("**🔭 신규 종목 레이더** (미보유인데 자주 다뤄짐)")
            for r in radar(rows, set(tickers), top_n=8, days=days):
                tone = ("🟢" if r["score"] > 20 else "🔴" if r["score"] < -20 else "⚪")
                st.markdown(f"- {tone} **{r['ticker']}** — {r['mentions']}회 언급 "
                            f"(매수 {r['buy']}·중립 {r['neutral']}·주의 {r['caution']})")
            st.caption("RAG(유튜브 대본) 메타데이터 집계 · LLM 비용 0 · 투자 권유 아님, 참고용")
        except Exception as e:
            st.warning(f"유튜버 집단지성 생성 실패: {e}")

    # ── AI 보유종목 평가 ──
    st.markdown("---")
    st.subheader("🤖 AI 보유종목 평가")

    from modules.portfolio_advisor import PERSONAS, get_or_create_eval

    stance_labels = {k: f"{v['label']} — {v['description']}" for k, v in PERSONAS.items()}
    selected_label = st.radio(
        "투자 성향을 선택하세요 (성향에 따라 같은 데이터도 다르게 평가합니다)",
        options=list(stance_labels.values()),
        index=0,
        key="advisor_stance",
    )
    stance = next(k for k, v in stance_labels.items() if v == selected_label)

    ec1, ec2 = st.columns([3, 1])
    with ec1:
        eval_clicked = st.button("📋 평가서 생성 (뉴스 검색 + 밸류에이션 + 이벤트 종합)",
                                 type="primary", use_container_width=True, key="eval_btn")
    with ec2:
        force_eval = st.button("🔄 강제 재생성", use_container_width=True, key="eval_force",
                               help="오늘 캐시를 무시하고 새로 검색/평가")

    if eval_clicked or force_eval:
        from utils.web_llm import get_search_provider
        if not get_search_provider():
            st.error("⚠️ 검색 LLM 키가 없습니다. .env에 PERPLEXITY_API_KEY를 설정하세요.")
        else:
            from utils.loading import ProgressBanner
            try:
                with ProgressBanner(
                    title=f"{PERSONAS[stance]['label']} 관점으로 AI 평가서 생성 중",
                    total=4, icon="🤖",
                ) as banner:
                    banner.step("📋 보유 종목 데이터 수집 중...")
                    banner.step("💰 밸류에이션 지표 조회 중 (PER·PEG·목표가)...")
                    banner.step("🔍 뉴스 웹 검색 중 (Perplexity)... (10~30초)")
                    result = get_or_create_eval(tracked, stance, force=bool(force_eval))
                    banner.step("✍️ AI가 평가서 작성 중...")
                    banner.done("✅ 평가서 생성 완료!")
                st.session_state.portfolio_eval = {**result, "stance": stance}
                if result["cached"]:
                    st.toast("📋 오늘 생성된 평가를 불러왔습니다 (API 호출 없음)")
                else:
                    st.toast("✅ 평가서 생성 완료!")
            except Exception as e:
                st.error(f"❌ 평가 생성 실패: {e}")

    ev = st.session_state.get("portfolio_eval")
    if ev:
        badge = PERSONAS[ev["stance"]]["label"]
        st.markdown(
            f"<span style='font-size:0.8rem;color:#64748B;'>"
            f"{badge} 관점 · 생성 {ev['time']}{' · 캐시' if ev.get('cached') else ''}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(ev["text"])

    # ── 5. 종목별 뉴스 ──
    st.markdown("---")
    st.subheader("📰 종목별 최신 이슈")

    for item in tracked:
        ticker = item["ticker"]
        with st.expander(f"**{item['name']}** ({ticker})", expanded=False):
            try:
                news_list = cached_news(ticker)
                if news_list:
                    for n in news_list:
                        st.markdown(
                            f"- [{n['title']}]({n['link']})  \n"
                            f"  <span style='color:#64748B; font-size:0.8rem;'>{n['publisher']} · {n['published']}</span>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.info("최근 뉴스가 없습니다.")
            except Exception as e:
                st.warning(f"뉴스 로드 실패: {e}")

            if st.toggle("📈 차트 보기", key=f"news_chart_{ticker}"):
                with st.spinner(f"{ticker} 차트 로딩..."):
                    fig = cached_candle_chart(ticker, "6mo")
                    if fig:
                        st.plotly_chart(fig, use_container_width=True, key=f"news_fig_{ticker}")
                    else:
                        st.warning("차트 데이터를 가져올 수 없습니다.")
