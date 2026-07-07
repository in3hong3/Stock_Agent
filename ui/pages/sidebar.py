"""사이드 패널 (사용자 정보, 시장 심리, 일정, 자산, 오늘 할 일, 유튜버 알림)."""
import datetime
import pandas as pd
import streamlit as st

from ui.components import render_fear_greed_bar


def _render_todo_video(holdings, fx):
    """오늘 할 일 + 유튜버 타이밍 알림 (사이드 세로 배치, 컴팩트)."""
    from ui.pages._meta import resolve_stance, get_cached_signals, load_meta

    if not holdings:
        return

    tickers = [h["ticker"] for h in holdings]
    holdings_key = tuple(
        (h["ticker"], h.get("quantity", 0), h.get("avg_price", 0), h.get("current_price", 0))
        for h in holdings
    )
    stance = resolve_stance()
    meta = load_meta()
    seed = float(meta.get("trading_seed", 0) or 0)
    risk = float(meta.get("risk_pct", 1.0) or 1.0)

    # ── 오늘 할 일 ──
    try:
        from modules.daily_actions import build_actions
        from modules.portfolio_advisor import PERSONAS

        signal_result = get_cached_signals(holdings_key, stance, seed, risk)
        st.session_state["_signal_result"] = signal_result  # 트래커가 재사용

        # 예측 기록 + 채점 (하루 1회)
        try:
            from modules.signal_tracker import record_predictions, grade_predictions
            _today_key = f"{datetime.date.today()}|{stance}"
            if st.session_state.get("_pred_recorded") != _today_key:
                record_predictions(signal_result["signals"], stance)
                grade_predictions(horizon_days=10)
                st.session_state["_pred_recorded"] = _today_key
        except Exception as e:
            print(f"예측 기록 실패: {e}")

        # 관심종목(미보유) 매수 후보도 '오늘 할 일'에 포함 (매수 신호만, 관망 제외)
        combined_signals = list(signal_result["signals"])
        try:
            from ui.pages._meta import get_cached_watchlist_signals
            from modules.watchlist import load_watchlist
            wl_key = tuple(it.get("ticker") for it in load_watchlist())
            if wl_key:
                wl_sigs = get_cached_watchlist_signals(wl_key, stance, seed, risk).get("signals", [])
                combined_signals += [
                    {**s, "watchlist": True}
                    for s in wl_sigs if s.get("action") in ("적극 매수", "분할 매수")
                ]
        except Exception as e:
            print(f"관심종목 액션 실패: {e}")

        from ui.pages._meta import load_cash
        _cash_usd = float(load_cash().get("usd", 0) or 0)
        actions = build_actions(pd.DataFrame(), tickers, stance,
                                signals=combined_signals, fx=fx, cash_usd=_cash_usd)
        if actions:
            badge = PERSONAS[stance]["label"]

            def _fmt_action(a):
                if a.get("kind") == "stock":
                    # 종목 카드: 제목(종목→액션 · 보유/수익률) + 들여쓴 세부 라인들
                    meta = a.get("meta", "")
                    meta_html = (f"<span style='color:#94A3B8; font-size:0.7rem; font-weight:400;'>"
                                 f"  {meta}</span>") if meta else ""
                    head = f"<div style='word-break:keep-all;'>{a['icon']} <b>{a['title']}</b>{meta_html}</div>"
                    sub = "".join(
                        f"<div style='color:#94A3B8; font-size:0.7rem; padding-left:16px; "
                        f"margin-top:1px; word-break:keep-all;'>{em} {tx}</div>"
                        for em, tx in a.get("lines", [])
                    )
                    body = head + sub
                else:
                    # 일반 항목(시장 이벤트·알림·발행물·홀드): '—' 기준 2줄 분리
                    txt = a["text"].replace("**", "<b>", 1).replace("**", "</b>", 1)
                    if " — " in txt:
                        head, detail = txt.split(" — ", 1)
                        body = (
                            f"<div style='word-break:keep-all;'>{a['icon']} {head}</div>"
                            f"<div style='color:#94A3B8; font-size:0.7rem; padding-left:16px; "
                            f"margin-top:1px; word-break:keep-all;'>↳ {detail}</div>"
                        )
                    else:
                        body = f"<div style='word-break:keep-all;'>{a['icon']} {txt}</div>"
                return (
                    f"<div style='padding:6px 0; font-size:0.78rem; line-height:1.5; "
                    f"border-top:1px solid rgba(255,255,255,0.05);'>{body}</div>"
                )

            rows = "".join(_fmt_action(a) for a in actions[:12])
            st.markdown(
                f"<div style='background:linear-gradient(160deg,#1A2340,#16181F); "
                f"border:1px solid #3b82f655; border-radius:12px; padding:12px 14px; margin-bottom:10px;'>"
                f"<div style='font-weight:700; font-size:0.9rem; margin-bottom:6px;'>"
                f"✅ 오늘 할 일 <span style='font-size:0.68rem; color:#94A3B8;'>"
                f"({badge} · {datetime.date.today().strftime('%m/%d')})</span></div>"
                f"{rows}</div>",
                unsafe_allow_html=True,
            )
    except Exception as e:
        print(f"사이드 오늘 할 일 실패: {e}")

    # ── 유튜버 타이밍 알림 ──
    try:
        from modules.video_timing import (
            get_active_alerts, load_alerts, refresh_alerts as _refresh_alerts,
            needs_refresh as _needs_refresh,
        )

        if _needs_refresh(stale_hours=48) and not st.session_state.get("_video_refresh_attempted"):
            st.session_state["_video_refresh_attempted"] = True
            from utils.loading import ProgressBanner
            try:
                with ProgressBanner(title="유튜버 영상 알림 자동 갱신 중", total=2, icon="🎤") as banner:
                    banner.step("📺 최근 90일 영상 수집 중...")
                    banner.step("🤖 AI가 시점 알림 추출 중... (15~30초)")
                    _refresh_alerts(holdings, days=90)
                    banner.done("✅ 갱신 완료!")
            except Exception as ve:
                print(f"자동 갱신 실패: {ve}")

        alerts_data = load_alerts()
        active_alerts = get_active_alerts()
        if active_alerts:
            gen_at = alerts_data.get("generated_at", "")
            gen_label = gen_at[:10] if gen_at else "—"
            cards = ""
            for a in active_alerts[:5]:
                tb = (f"<span style='background:#3b82f655; color:#60a5fa; padding:1px 5px; "
                      f"border-radius:3px; font-size:0.68rem; font-weight:700;'>{a['ticker']}</span> "
                      if a.get("ticker") else "")
                link = (f"<a href='{a['video_link']}' target='_blank' style='color:#94A3B8; text-decoration:none;'>↗</a>"
                        if a.get("video_link") else "")
                cards += (
                    f"<div style='padding:6px 0; border-top:1px solid rgba(255,255,255,0.06);'>"
                    f"<div style='font-weight:600; font-size:0.78rem;'>{a.get('level','')} {tb}{a.get('title','')}</div>"
                    f"<div style='color:#94A3B8; font-size:0.72rem; margin-top:2px;'>💬 {a.get('message','')}</div>"
                    f"<div style='color:#64748B; font-size:0.66rem; margin-top:2px;'>"
                    f"📺 {a.get('source_video','')[:30]} {link}</div></div>"
                )
            st.markdown(
                f"<div style='background:linear-gradient(160deg,#2A1845,#16181F); "
                f"border:1px solid #a855f755; border-radius:12px; padding:12px 14px; margin-bottom:10px;'>"
                f"<div style='font-weight:700; font-size:0.9rem; margin-bottom:2px;'>"
                f"🎤 유튜버 타이밍 <span style='font-size:0.66rem; color:#94A3B8;'>({gen_label})</span></div>"
                f"{cards}</div>",
                unsafe_allow_html=True,
            )
    except Exception as e:
        print(f"사이드 유튜버 알림 실패: {e}")


def render_mobile_nav(selected_tab: str = None):
    """Simple mobile top navigation bar. Returns the selected tab name."""
    tabs = ["트래커", "데일리 신문", "포트폴리오", "AI 평가", "매매일지"]
    icons = ["📌", "📰", "💼", "🤖", "📒"]
    col1, col2 = st.columns([1, 8])
    with col1:
        st.markdown("<div class='mobile-nav'>", unsafe_allow_html=True)
    with col2:
        selected = st.selectbox("", options=[f"{icons[i]} {tabs[i]}" for i in range(len(tabs))], index=0, key="mobile_tab_selector")
    st.markdown("</div>", unsafe_allow_html=True)
    return selected.split(' ', 1)[1]


def render_side_panel(fg_index, fg_status, status_text, point_color):
    # 현재 사용자 + 로그아웃
    uid = st.session_state.get("user_id", "?")
    uc1, uc2 = st.columns([3, 1])
    uc1.markdown(f"👤 **{uid}**님 로그인 중")
    if uc2.button("로그아웃", key="logout_btn", use_container_width=True):
        # 계정별 데이터/캐시를 모두 비워 다음 로그인 계정과 섞이지 않게
        for k in ("authenticated", "user_id", "_migrated", "df_portfolio",
                  "portfolio_data", "tracker_briefing", "portfolio_eval",
                  "personalized_rag_engine", "personalized_rag_messages",
                  "_signal_result", "_pred_recorded", "reload_csv",
                  "_auto_price_fill_done", "_auto_price_fill_done_portfolio"):
            st.session_state.pop(k, None)
        st.query_params.clear()  # URL 로그인 토큰 제거 → 새로고침해도 로그인 유지 안 됨
        st.cache_data.clear()  # 시그널/스냅샷 등 가격 의존 캐시 무효화
        st.rerun()
    st.divider()

    # ── 🌋 시장 심리 (컴팩트 막대) ──
    render_fear_greed_bar(fg_index, status_text)
    st.divider()

    # ── 📅 일정 (다가오는 일정 전면, 월별 달력은 expander로 접음) ──
    from modules.event_calendar import (
        get_all_events, build_calendar_html, get_upcoming_events,
        add_custom_event, load_custom_events, remove_custom_event,
    )
    from modules.issue_tracker import get_portfolio_holdings

    @st.cache_data(ttl=21600)
    def cached_events(ticker_tuple, custom_ver):
        return get_all_events(list(ticker_tuple))

    holdings = get_portfolio_holdings()
    tickers = tuple(h["ticker"] for h in holdings)
    custom_ver = len(load_custom_events())

    with st.spinner("일정 로딩 중..."):
        events = cached_events(tickers, custom_ver)

    today = datetime.date.today()

    st.markdown("**📅 다가오는 일정**")
    upcoming = get_upcoming_events(events, days=21)
    if upcoming:
        for ev in upcoming[:8]:
            d_day = f"D-{ev['d_day']}" if ev["d_day"] > 0 else "오늘"
            st.markdown(
                f"<div style='font-size:0.85rem; padding:2px 0; display:flex; gap:8px;'>"
                f"<span style='color:{point_color}; font-weight:700; min-width:38px;'>{d_day}</span>"
                f"<span style='color:#94A3B8; min-width:38px;'>{ev['date'].strftime('%m/%d')}</span>"
                f"<span>{ev['title']}</span></div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("3주 이내 일정이 없습니다.")

    # 월별 달력 (기본 접힘)
    with st.expander("🗓️ 월별 달력 보기"):
        cal_month = st.session_state.get("cal_month", today.month)
        cal_year = st.session_state.get("cal_year", today.year)

        nav1, nav2, nav3 = st.columns([1, 3, 1])
        with nav1:
            if st.button("◀", key="cal_prev", use_container_width=True):
                cal_month -= 1
                if cal_month == 0:
                    cal_month, cal_year = 12, cal_year - 1
                st.session_state.cal_month, st.session_state.cal_year = cal_month, cal_year
                st.rerun()
        with nav3:
            if st.button("▶", key="cal_next", use_container_width=True):
                cal_month += 1
                if cal_month == 13:
                    cal_month, cal_year = 1, cal_year + 1
                st.session_state.cal_month, st.session_state.cal_year = cal_month, cal_year
                st.rerun()

        st.markdown(build_calendar_html(cal_year, cal_month, events, accent=point_color), unsafe_allow_html=True)
        st.caption("점 표시된 날짜에 마우스를 올리면 일정이 보입니다.")

    # 일정 직접 추가 (기본 접힘)
    with st.expander("📝 일정 직접 추가"):
        with st.form("add_event_form", clear_on_submit=True):
            ev_date = st.date_input("날짜", value=today, key="ev_date")
            ev_title = st.text_input("일정 내용", placeholder="예: 테슬라 로보택시 발표")
            if st.form_submit_button("➕ 추가", use_container_width=True):
                if ev_title.strip():
                    add_custom_event(ev_date.strftime("%Y-%m-%d"), ev_title.strip())
                    st.cache_data.clear()
                    st.rerun()

        customs = load_custom_events()
        if customs:
            st.markdown("**등록한 일정:**")
            for i, ev in enumerate(customs):
                ec1, ec2 = st.columns([5, 1])
                ec1.markdown(f"<span style='font-size:0.85rem;'>{ev['date']} — {ev['title']}</span>", unsafe_allow_html=True)
                if ec2.button("🗑️", key=f"del_ev_{i}"):
                    remove_custom_event(i)
                    st.cache_data.clear()
                    st.rerun()

    # ── 💰 총 자산 미니 요약 (어느 탭에서든 항상 보임) ──
    st.divider()
    try:
        from modules.issue_tracker import get_usdkrw_rate
        from ui.pages._meta import compute_total_assets
        from utils.portfolio_utils import record_asset_snapshot

        @st.cache_data(ttl=600)
        def _side_fx():
            return get_usdkrw_rate()

        fx = _side_fx() or 1400.0
        a = compute_total_assets(holdings, fx)
        if a["total"] > 0:
            # 자산 추이 기록 (하루치 누적 — 트래커 자산추이 차트가 이 데이터를 읽음)
            record_asset_snapshot(a["total"], a["stock_eval"], a["cash_total"])

            pnl_color = "#FF4B4B" if a["pnl"] >= 0 else "#4B7BFF"
            usd_total = a["total"] / fx if fx else 0

            # 종목별 평가액(달러) + 수익률 리스트 (평가액 큰 순)
            items = []
            for h in holdings:
                try:
                    qty = float(h.get("quantity", 0) or 0)
                    cur = float(h.get("current_price", 0) or 0)
                    avg = float(h.get("avg_price", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if qty <= 0 or cur <= 0:
                    continue
                is_kr = str(h.get("ticker", "")).endswith((".KS", ".KQ"))
                eval_usd = (cur * qty / fx) if (is_kr and fx) else (cur * qty)
                pr = (cur / avg - 1) * 100 if avg > 0 else None
                items.append((str(h.get("ticker", "")), eval_usd, pr))
            items.sort(key=lambda x: -x[1])

            rows_html = ""
            for ticker, ev, pr in items:
                if isinstance(pr, (int, float)):
                    pc = "#FF4B4B" if pr > 0 else "#4B7BFF" if pr < 0 else "#94A3B8"
                    pr_str = f"{pr:+.1f}%"
                else:
                    pc, pr_str = "#94A3B8", "—"
                rows_html += (
                    f"<div style='display:flex; justify-content:space-between; font-size:0.78rem; padding:2px 0;'>"
                    f"<span><b style='color:#E2E8F0;'>{ticker}</b> "
                    f"<span style='color:#94A3B8;'>${ev:,.0f}</span></span>"
                    f"<span style='color:{pc};'>{pr_str}</span></div>"
                )

            holdings_block = ""
            if rows_html:
                holdings_block = (
                    f"<div style='border-top:1px solid #1f2230; margin:8px 0 4px;'></div>"
                    f"<div style='font-size:0.72rem; color:#94A3B8; margin-bottom:2px;'>"
                    f"보유 {len(items)}종목 (평가액 · 수익률)</div>"
                    f"{rows_html}"
                )

            st.markdown(
                f"<div style='background:#16181F; border:1px solid rgba(255,255,255,0.05); "
                f"border-radius:12px; padding:12px 14px;'>"
                f"<div style='font-size:0.85rem; font-weight:700; margin-bottom:8px;'>💰 내 자산</div>"
                f"<div style='font-size:1.35rem; font-weight:700; color:#E2E8F0; line-height:1.1;'>"
                f"₩{a['total']:,.0f}</div>"
                f"<div style='font-size:0.72rem; color:#94A3B8; margin:2px 0 8px;'>≈ ${usd_total:,.0f}</div>"
                f"<div style='display:flex; justify-content:space-between; font-size:0.8rem; padding:2px 0;'>"
                f"<span style='color:#94A3B8;'>주식 평가</span>"
                f"<span style='color:#E2E8F0;'>₩{a['stock_eval']:,.0f}</span></div>"
                f"<div style='display:flex; justify-content:space-between; font-size:0.8rem; padding:2px 0;'>"
                f"<span style='color:#94A3B8;'>평가 손익</span>"
                f"<span style='color:{pnl_color}; font-weight:700;'>{a['pnl']:+,.0f} ({a['pnl_rate']:+.1f}%)</span></div>"
                f"<div style='display:flex; justify-content:space-between; font-size:0.8rem; padding:2px 0;'>"
                f"<span style='color:#94A3B8;'>현금 비중</span>"
                f"<span style='color:#E2E8F0;'>{a['cash_ratio']:.1f}%</span></div>"
                f"{holdings_block}"
                f"</div>",
                unsafe_allow_html=True,
            )
    except Exception as e:
        print(f"사이드 자산 요약 실패: {e}")

    # ── ✅ 오늘 할 일 + 🎤 유튜버 타이밍 알림 ──
    st.divider()
    try:
        from modules.issue_tracker import get_usdkrw_rate

        @st.cache_data(ttl=600)
        def _todo_fx():
            return get_usdkrw_rate()

        _render_todo_video(holdings, _todo_fx() or 1400.0)
    except Exception as e:
        print(f"사이드 오늘할일/유튜버 실패: {e}")
