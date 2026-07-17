"""가격 알림 탭 서비스 — ui/pages/alerts.py를 FastAPI용으로 (CRUD).

price_alert(전역 알림)·watchlist(관심종목)·meta 토글(사용자별) 재사용.
run_alert_check는 실제 이메일/카카오 발송 → 사용자 버튼 클릭 시에만.
"""
from web.services.meta import load_meta, save_meta


def _email_ok() -> bool:
    import os
    return bool(os.getenv("BRIEFING_TO_EMAIL"))


def _kakao_ok() -> bool:
    try:
        from modules.kakao_notify import is_configured
        return is_configured()
    except Exception:
        return False


def get_context() -> dict:
    from modules.price_alert import load_alerts, CONDITION_TYPES
    from modules.watchlist import load_watchlist

    meta = load_meta()
    alerts = [{
        "id": a["id"], "ticker": a["ticker"],
        "condition": CONDITION_TYPES.get(a["condition"], a["condition"]),
        "value": a["value"], "enabled": a.get("enabled", True),
        "last_triggered": a.get("last_triggered"),
    } for a in load_alerts()]

    return {
        "email_ok": _email_ok(), "kakao_ok": _kakao_ok(),
        "kakao_briefing_enabled": bool(meta.get("kakao_briefing_enabled", False)),
        "watchlist_alert_enabled": bool(meta.get("watchlist_alert_enabled", True)),
        "watchlist": load_watchlist(),
        "alerts": alerts,
        "condition_types": [{"key": k, "label": v} for k, v in CONDITION_TYPES.items()],
    }


# ── 토글 (meta) ──
def toggle_briefing(on: bool) -> str:
    save_meta(kakao_briefing_enabled=on)
    return "📩 데일리 브리핑 받기 " + ("켜짐" if on else "꺼짐")


def toggle_watchlist_alert(on: bool) -> str:
    save_meta(watchlist_alert_enabled=on)
    return "🎯 매수 타이밍 알림 " + ("켜짐" if on else "꺼짐")


# ── 관심종목 CRUD ──
def add_watch(user_input: str) -> str:
    from modules.watchlist import add_to_watchlist
    if not (user_input or "").strip():
        return "⚠️ 종목을 입력하세요."
    r = add_to_watchlist(user_input.strip())
    if r.get("success"):
        return f"✅ {r['name']} ({r['ticker']}) 관심종목 추가"
    return f"⚠️ {r.get('error', '추가 실패')}"


def remove_watch(ticker: str) -> str:
    from modules.watchlist import remove_from_watchlist
    remove_from_watchlist(ticker)
    return f"🗑️ {ticker} 관심종목 삭제"


# ── 수동 알림 CRUD ──
def add_manual(ticker: str, condition: str, value: float) -> str:
    from modules.price_alert import add_alert, CONDITION_TYPES
    if not (ticker or "").strip():
        return "⚠️ 티커를 입력하세요."
    if condition not in CONDITION_TYPES:
        return "⚠️ 조건이 올바르지 않습니다."
    add_alert(ticker.strip(), condition, value)
    return f"✅ {ticker.strip().upper()} 알림이 추가되었습니다."


def reenable(alert_id: int) -> str:
    from modules.price_alert import load_alerts, save_alerts
    alerts = load_alerts()
    for a in alerts:
        if a["id"] == alert_id:
            a["enabled"] = True
    save_alerts(alerts)
    return "🔄 알림을 재활성화했습니다."


def remove(alert_id: int) -> str:
    from modules.price_alert import remove_alert
    remove_alert(alert_id)
    return "🗑️ 알림을 삭제했습니다."


# ── 조회/실행 (HTMX fragment) ──
def buy_timings() -> dict:
    """관심+보유종목 매수 타이밍 (읽기 전용 계산)."""
    from modules.watchlist import detect_buy_timings
    buys = detect_buy_timings(stance="aggressive", update_state=False).get("all_buys", [])
    rows = [{
        "kind": s.get("alert_kind", "매수"), "ticker": s["ticker"], "action": s["action"],
        "setup": s.get("setup", ""),
        "plan": (f"진입 {s['entry']:,.2f} / 손절 {s['stop']:,.2f} / 목표 {s['target']:,.2f}"
                 if s.get("entry") else ""),
    } for s in buys]
    return {"buys": rows}


def check_now() -> dict:
    """조건 체크 + 이메일/카카오 발송 (실제 발송!). 버튼 클릭 시에만."""
    from modules.price_alert import run_alert_check
    result = run_alert_check()
    triggered = [{"ticker": t["ticker"], "current_value": t["current_value"], "value": t["value"]}
                 for t in result.get("triggered", [])]
    return {
        "count": result.get("triggered_count", 0),
        "email_sent": result.get("email_sent"), "kakao_sent": result.get("kakao_sent"),
        "triggered": triggered,
    }
