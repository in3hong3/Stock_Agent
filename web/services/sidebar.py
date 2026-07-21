"""오른쪽 사이드 패널 — ui/pages/sidebar.py를 FastAPI용으로.

일정·월별달력·내자산·오늘할일·유튜버알림. HTMX lazy-load(페이지 뜬 뒤 채워짐).
부수효과: 자산 스냅샷 기록(하루1행, 자산추이 소스) + 예측 기록/채점(하루1회, 적중률 소스).
유튜버 알림 자동갱신(LLM 비용)은 끔 — 기존 알림만 표시(관리자 '강제 갱신' 또는 cron으로).
"""
import datetime

from web.services.meta import load_meta

_pred_guard = {"day": None}   # 예측 기록/채점 하루 1회 가드


def _holdings():
    from modules.issue_tracker import get_portfolio_holdings
    return get_portfolio_holdings()


def _fx() -> float:
    try:
        from modules.issue_tracker import get_usdkrw_rate
        return get_usdkrw_rate() or 1400.0
    except Exception:
        return 1400.0


def _resolve_stance() -> str:
    from modules.portfolio_advisor import PERSONAS
    saved = load_meta().get("advisor_stance", "")
    return saved if saved in PERSONAS else "aggressive"


# ── 라이트 컨텍스트 (일정·달력·내자산) ──
def light_context(cal_year: int = None, cal_month: int = None, point_color: str = "#00FFA3") -> dict:
    from modules.event_calendar import get_all_events, get_upcoming_events, build_calendar_html, load_custom_events

    today = datetime.date.today()
    cal_year = cal_year or today.year
    cal_month = cal_month or today.month

    holdings = _holdings()
    tickers = [h["ticker"] for h in holdings]

    # 일정
    try:
        events = get_all_events(tickers)
        upcoming = [{"d_day": e["d_day"], "date": e["date"].strftime("%m/%d"), "title": e["title"],
                     "d_label": (f"D-{e['d_day']}" if e["d_day"] > 0 else "오늘")}
                    for e in get_upcoming_events(events, days=21)[:8]]
        cal_html = build_calendar_html(cal_year, cal_month, events, accent=point_color)
    except Exception as e:
        print(f"[sidebar] 일정 실패: {e}")
        upcoming, cal_html = [], ""

    return {
        "upcoming": upcoming, "cal_html": cal_html,
        "cal_year": cal_year, "cal_month": cal_month,
        "custom_events": load_custom_events(),
        "assets": _assets(holdings),
    }


def _assets(holdings) -> dict:
    from web.services.portfolio import _cash
    from utils.portfolio_utils import record_asset_snapshot
    fx = _fx()
    cash = _cash()
    stock_eval = stock_cost = 0.0
    items = []
    for h in holdings:
        try:
            qty = float(h.get("quantity", 0) or 0)
            cur = float(h.get("current_price", 0) or 0)
            avg = float(h.get("avg_price", 0) or 0)
        except (TypeError, ValueError):
            continue
        is_kr = str(h.get("ticker", "")).endswith((".KS", ".KQ"))
        factor = 1.0 if is_kr else fx
        stock_eval += qty * cur * factor
        stock_cost += qty * avg * factor
        if qty > 0 and cur > 0:
            eval_usd = (cur * qty / fx) if (is_kr and fx) else (cur * qty)
            pr = (cur / avg - 1) * 100 if avg > 0 else None
            items.append({"ticker": str(h.get("ticker", "")), "eval_usd": eval_usd, "pr": pr})
    items.sort(key=lambda x: -x["eval_usd"])

    pnl = stock_eval - stock_cost
    cash_total = cash["krw"] + cash["usd"] * fx
    total = stock_eval + cash_total
    if total > 0:
        try:
            record_asset_snapshot(total, stock_eval, cash_total)  # 하루1행 자산추이 기록
        except Exception as e:
            print(f"[sidebar] 자산 스냅샷 실패: {e}")
    return {
        "total": total, "usd_total": total / fx if fx else 0, "stock_eval": stock_eval,
        "pnl": pnl, "pnl_rate": (pnl / stock_cost * 100) if stock_cost > 0 else 0,
        "cash_ratio": (cash_total / total * 100) if total > 0 else 0,
        "holdings": items, "has_assets": total > 0,
    }


# ── 오늘 할 일 (HTMX lazy, 무거움) ──
def todo() -> dict:
    holdings = _holdings()
    if not holdings:
        return {"actions": []}
    tickers = [h["ticker"] for h in holdings]
    stance = _resolve_stance()
    meta = load_meta()
    seed = float(meta.get("trading_seed", 0) or 0)
    risk = float(meta.get("risk_pct", 1.0) or 1.0)
    try:
        from web.services.tracker import _signals
        from modules.daily_actions import build_actions
        from modules.portfolio_advisor import PERSONAS
        import pandas as pd
        sig = _signals(holdings, stance, seed, risk)

        # 예측 기록/채점 (하루 1회, 적중률 소스) — LLM 아님
        _record_predictions_once(sig.get("signals", []), stance)

        _cash_usd = float(load_meta().get("cash_usd", 0) or 0)
        actions = build_actions(pd.DataFrame(), tickers, stance,
                                signals=sig.get("signals", []), fx=_fx(), cash_usd=_cash_usd)
        return {"actions": actions[:12], "badge": PERSONAS[stance]["label"],
                "date": datetime.date.today().strftime("%m/%d")}
    except Exception as e:
        print(f"[sidebar] 오늘할일 실패: {e}")
        return {"actions": []}


def _record_predictions_once(signals, stance):
    today = f"{datetime.date.today()}|{stance}"
    if _pred_guard["day"] == today:
        return
    try:
        from modules.signal_tracker import record_predictions, grade_predictions
        record_predictions(signals, stance)
        grade_predictions(horizon_days=10)
        _pred_guard["day"] = today
    except Exception as e:
        print(f"[sidebar] 예측 기록/채점 실패: {e}")


# ── 유튜버 타이밍 알림 (HTMX lazy, 자동갱신 없음) ──
def youtuber() -> dict:
    try:
        from modules.video_timing import get_active_alerts, load_alerts
        alerts_data = load_alerts()
        active = get_active_alerts()[:5]
        gen = alerts_data.get("generated_at", "")
        return {"alerts": active, "gen": gen[:10] if gen else "—"}
    except Exception as e:
        print(f"[sidebar] 유튜버 알림 실패: {e}")
        return {"alerts": []}
