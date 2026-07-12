"""주간 유튜버 리포트 탭 — 한 주 영상 종합 + 주차별 보관."""
import streamlit as st


def _sentiment_bar(buy: int, neutral: int, caution: int) -> str:
    total = buy + neutral + caution
    if not total:
        return ""
    b, n, c = (buy / total * 100, neutral / total * 100, caution / total * 100)
    return (
        "<div style='display:flex; height:10px; border-radius:5px; overflow:hidden; "
        "background:#1e293b; min-width:120px;'>"
        f"<div style='width:{b}%; background:#FF4B4B;'></div>"
        f"<div style='width:{n}%; background:#475569;'></div>"
        f"<div style='width:{c}%; background:#4B7BFF;'></div>"
        "</div>"
    )


def _render_report(report: dict, holdings_tickers: set):
    period = report.get("period", {})
    st.markdown(
        f"<div style='text-align:center; border-top:4px double #E2E8F0; "
        f"border-bottom:1px solid #475569; padding:16px 0 10px 0; margin-bottom:14px;'>"
        f"<div style='font-family:\"Noto Serif KR\",serif; font-size:32px; font-weight:900; "
        f"letter-spacing:0.1em; color:#FFF;'>週間 유튜버 리포트</div>"
        f"<div style='font-size:12px; color:#94A3B8; margin-top:6px; letter-spacing:0.15em;'>"
        f"{period.get('start','')} ~ {period.get('end','')} · {report.get('week_key','')} · "
        f"발행 {report.get('published_at','')}</div></div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("📹 이번 주 영상", f"{report.get('video_count', 0)}개")
    c2.metric("📺 채널 수", f"{report.get('channel_count', 0)}개")
    c3.metric("🎯 다뤄진 종목", f"{report.get('stock_count', 0)}개")

    # ③④ 내러티브 (LLM)
    if report.get("narrative"):
        st.markdown("---")
        st.markdown(report["narrative"])
        if report.get("engine", "").startswith("fallback"):
            st.caption("※ LLM 종합 미사용 — 집계 기반 요약본입니다 (OPENAI_API_KEY 미설정).")

    # ② 지난주 대비 변화
    surges, flips = report.get("surges", []), report.get("tone_flips", [])
    if surges or flips:
        st.markdown("---")
        st.markdown("#### 📈 지난주 대비 변화")
        cc1, cc2 = st.columns(2)
        with cc1:
            st.markdown("**🔺 언급 급증**")
            if surges:
                for s in surges:
                    st.markdown(
                        f"- **{s['ticker']}** · {s['prior']}회 → **{s['this_week']}회**"
                    )
            else:
                st.caption("급증 종목 없음")
        with cc2:
            st.markdown("**🔄 톤 반전**")
            if flips:
                for f in flips:
                    arrow = "🔻" if f["now"] == "주의우위" else "🔺"
                    st.markdown(f"- {arrow} **{f['ticker']}** · {f['prior']} → **{f['now']}**")
            else:
                st.caption("반전 종목 없음")

    # ① 언급 TOP 종목
    top = report.get("top_mentions", [])
    if top:
        st.markdown("---")
        st.markdown("#### 🏆 이번 주 언급 TOP 종목")
        st.caption("막대: 🔴 매수 · ⚫ 중립 · 🔵 주의 비중")
        for t in top[:15]:
            held = "⭐ " if t["ticker"] in holdings_tickers else ""
            col_a, col_b, col_c = st.columns([2.2, 2, 1])
            with col_a:
                st.markdown(f"{held}**{t['name']}** `{t['ticker']}`")
            with col_b:
                st.markdown(_sentiment_bar(t["buy"], t["neutral"], t["caution"]),
                            unsafe_allow_html=True)
            with col_c:
                sc = t["score"]
                color = "#FF4B4B" if sc > 0 else "#4B7BFF" if sc < 0 else "#94A3B8"
                st.markdown(
                    f"<span style='font-size:0.8rem;'>{t['total']}회 · "
                    f"<b style='color:{color};'>{sc:+d}</b></span>",
                    unsafe_allow_html=True,
                )

    # ⑤ 내 보유종목 관련 코멘트
    if holdings_tickers:
        st.markdown("---")
        st.markdown("#### 💼 내 보유종목 관련 코멘트")
        mine = [v for v in report.get("videos", [])
                if holdings_tickers & set(v.get("tickers", []))]
        if mine:
            for v in mine[:20]:
                hit = holdings_tickers & set(v["tickers"])
                tags = " ".join(
                    f"`{tk}·{v.get('sentiments', {}).get(tk, '중립')}`" for tk in hit
                )
                title = v.get("title", "")
                link = v.get("link", "")
                title_md = f"[{title}]({link})" if link.startswith("http") else title
                st.markdown(
                    f"- {title_md}  \n"
                    f"  <span style='color:#64748B; font-size:0.78rem;'>"
                    f"{v.get('channel','')} · {v.get('date','')} · {tags}</span>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("이번 주 영상에서 보유종목 언급이 없습니다.")


def render_tab_weekly_report():
    from modules.weekly_youtube_report import (
        get_report, list_reports, publish_weekly_report, week_key,
    )
    from modules.issue_tracker import get_portfolio_holdings

    st.header("📅 주간 유튜버 리포트")
    st.caption("한 주(월~일) 동안 유튜버들이 다룬 종목·톤·테마를 종합합니다. 매주 일요일 저녁 자동 발행.")

    try:
        holdings_tickers = {h["ticker"] for h in get_portfolio_holdings() if h.get("ticker")}
    except Exception:
        holdings_tickers = set()

    keys = list_reports()
    this_key = week_key()

    col_sel, col_btn = st.columns([3, 1])
    with col_sel:
        options = keys if keys else [this_key]
        if this_key not in options:
            options = [this_key] + options
        labels = {k: (f"{k} (이번 주)" if k == this_key else k) for k in options}
        chosen = st.selectbox(
            "주차 선택", options, format_func=lambda k: labels.get(k, k), key="weekly_sel"
        )
    with col_btn:
        st.write("")
        st.write("")
        regen = st.button("🔄 이번 주 다시 종합", use_container_width=True)

    if regen:
        with st.spinner("이번 주 영상 종합 중... (Pinecone 스캔 + AI 종합, 20~40초)"):
            try:
                report = publish_weekly_report()
                st.session_state["_weekly_regen"] = report["week_key"]
                st.toast("📅 주간 리포트를 새로 종합했습니다")
                chosen = report["week_key"]
            except Exception as e:
                st.error(f"종합 실패: {e}")

    report = get_report(chosen)

    if not report:
        if chosen == this_key:
            st.info(
                "이번 주 리포트가 아직 없습니다. 우측 **'이번 주 다시 종합'** 버튼을 누르면 "
                "지금까지 쌓인 이번 주 영상으로 즉시 만들 수 있어요. "
                "(평소엔 매주 일요일 저녁 서버가 자동 발행합니다.)"
            )
        else:
            st.warning("해당 주차 리포트가 없습니다.")
        return

    _render_report(report, holdings_tickers)
