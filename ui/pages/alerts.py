"""가격 알림 탭."""
import streamlit as st


def render_tab_alerts():
    from modules.price_alert import (
        load_alerts, save_alerts, add_alert, remove_alert,
        run_alert_check, CONDITION_TYPES,
    )

    st.header("🔔 가격 알림")
    st.caption("조건 충족 시 이메일로 알려드립니다. 서버 cron이 30분마다 자동 체크합니다.")

    with st.form("add_alert_form"):
        ac1, ac2, ac3, ac4 = st.columns([2, 3, 2, 1])
        with ac1:
            alert_ticker = st.text_input("티커", value="NVDA")
        with ac2:
            cond_label = st.selectbox("조건", list(CONDITION_TYPES.values()))
        with ac3:
            alert_value = st.number_input("기준값", min_value=0.0, value=100.0, step=1.0)
        with ac4:
            st.write("")
            submitted = st.form_submit_button("➕ 추가", use_container_width=True)

        if submitted and alert_ticker.strip():
            cond_key = next(k for k, v in CONDITION_TYPES.items() if v == cond_label)
            add_alert(alert_ticker.strip(), cond_key, alert_value)
            st.success(f"✅ {alert_ticker.upper()} 알림이 추가되었습니다.")
            st.rerun()

    st.markdown("---")
    alerts = load_alerts()
    st.subheader(f"📋 등록된 알림 ({len(alerts)}건)")

    if not alerts:
        st.info("등록된 알림이 없습니다. 위에서 추가하세요.")
    else:
        for alert in alerts:
            lc1, lc2, lc3, lc4, lc5 = st.columns([1.5, 3, 1.5, 1.5, 1])
            status_icon = "🟢" if alert.get("enabled") else "⚪"
            lc1.markdown(f"{status_icon} **{alert['ticker']}**")
            lc2.markdown(CONDITION_TYPES.get(alert["condition"], alert["condition"]))
            lc3.markdown(f"기준: `{alert['value']}`")
            lc4.markdown(
                f"<span style='font-size:0.8rem;color:#94A3B8;'>"
                f"{'발송: ' + alert['last_triggered'] if alert.get('last_triggered') else '대기 중'}</span>",
                unsafe_allow_html=True,
            )
            with lc5:
                bc1, bc2 = st.columns(2)
                if not alert.get("enabled"):
                    if bc1.button("🔄", key=f"reenable_{alert['id']}", help="재활성화"):
                        for a in alerts:
                            if a["id"] == alert["id"]:
                                a["enabled"] = True
                        save_alerts(alerts)
                        st.rerun()
                if bc2.button("🗑️", key=f"del_alert_{alert['id']}", help="삭제"):
                    remove_alert(alert["id"])
                    st.rerun()

    st.markdown("---")
    if st.button("📡 지금 바로 조건 체크 + 이메일 발송", use_container_width=True):
        with st.spinner("조건 체크 중..."):
            result = run_alert_check()
            if result["triggered_count"] > 0:
                st.success(
                    f"✅ {result['triggered_count']}건 조건 충족! "
                    f"이메일 발송: {'성공' if result['email_sent'] else '실패 (환경변수 확인)'}"
                )
                for t in result["triggered"]:
                    st.markdown(f"- **{t['ticker']}**: 현재값 `{t['current_value']}` (기준 `{t['value']}`)")
            else:
                st.info("충족된 조건이 없습니다.")
