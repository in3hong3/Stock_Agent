"""
관심종목(watchlist) + 스마트 매수 타이밍 알림.

- watchlist.json: 보유와 별개의 '관심만 있는' 종목 (per-user)
- trade_signal 재사용해 매수 타이밍 판정 (적극/분할 매수)
- 대상 = 관심종목(신규매수) + 보유종목(추가매수)
- 상태 전환(비매수→매수, 분할→적극)일 때만 카카오 1회 발송 (스팸 방지)
"""
import os
import json
from typing import List, Dict, Any

from utils.user_data import user_file
from modules.daily_paper import now_kst  # KST 기준 날짜

_BUY_ACTIONS = ("적극 매수", "분할 매수")
LINK = "http://161.33.6.231/"


def _wl_file() -> str:
    return user_file("watchlist.json")


def _state_file() -> str:
    return user_file("watchlist_alert_state.json")


def _load_json(path: str, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return default
    return default


def _save_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── 관심종목 CRUD ──
def load_watchlist() -> List[Dict[str, str]]:
    return _load_json(_wl_file(), [])


def save_watchlist(items: List[Dict[str, str]]):
    _save_json(_wl_file(), items)


def add_to_watchlist(user_input: str) -> Dict[str, Any]:
    """관심종목 추가 (한글명/티커 모두 허용, yfinance 유효성 검증)."""
    from modules.issue_tracker import resolve_ticker
    import yfinance as yf

    ticker = resolve_ticker(user_input)
    items = load_watchlist()
    if any(it["ticker"] == ticker for it in items):
        return {"success": False, "error": f"{ticker}는 이미 관심종목에 있습니다."}
    try:
        tk = yf.Ticker(ticker)
        if tk.history(period="5d").empty:
            return {"success": False, "error": f"'{user_input}' → '{ticker}' 데이터를 찾을 수 없습니다."}
        name = tk.info.get("shortName") or user_input
    except Exception:
        return {"success": False, "error": f"'{ticker}' 조회 실패. 티커를 확인하세요."}
    items.append({"ticker": ticker, "name": name, "added": now_kst().strftime("%Y-%m-%d")})
    save_watchlist(items)
    return {"success": True, "ticker": ticker, "name": name}


def remove_from_watchlist(ticker: str):
    save_watchlist([it for it in load_watchlist() if it["ticker"] != ticker])


# ── 매수 타이밍 판정 ──
def detect_buy_timings(stance: str = "aggressive", update_state: bool = True) -> Dict[str, Any]:
    """관심종목+보유종목을 분석해 매수 타이밍 판정.
    Returns {newly: [...상태 전환된 매수 시그널], all_buys: [...현재 매수 전체]}.
    update_state=True면 상태 파일을 갱신(cron용). False면 읽기 전용(UI '지금 보기'용)."""
    from modules.issue_tracker import get_portfolio_holdings
    from modules.trade_signal import generate_signals

    holdings = get_portfolio_holdings()
    held = {h["ticker"] for h in holdings}
    wl = load_watchlist()

    targets = list(holdings)  # 보유종목 (qty/avg 포함)
    for it in wl:
        if it["ticker"] not in held:  # 관심종목 (미보유 → qty 0)
            targets.append({"ticker": it["ticker"], "name": it.get("name", it["ticker"]),
                            "quantity": 0, "avg_price": 0})
    if not targets:
        return {"newly": [], "all_buys": []}

    signals = generate_signals(targets, stance=stance, seed=0)["signals"]
    state = _load_json(_state_file(), {})
    newly, all_buys = [], []
    for s in signals:
        tk, action = s["ticker"], s["action"]
        if action in _BUY_ACTIONS:
            tagged = {**s, "alert_kind": "추가매수" if tk in held else "신규매수"}
            all_buys.append(tagged)
            if state.get(tk) != action:  # 신규 진입 또는 등급 변화(분할→적극)
                newly.append(tagged)
                state[tk] = action
        else:
            state.pop(tk, None)  # 비매수로 빠지면 리셋 → 다음 재진입 시 재알림
    if update_state:
        _save_json(_state_file(), state)
    return {"newly": newly, "all_buys": all_buys}


def format_alert(signals: List[Dict[str, Any]]) -> str:
    """매수 타이밍 시그널들을 카카오 메시지 텍스트로.
    현재가 vs 진입가 괴리를 함께 표기 — 이미 진입가 위로 벌어졌으면 '추격 금지·눌림 대기'."""
    from modules.daily_actions import _BUY_NEAR_PCT  # 진입가 근접 기준(오늘 할 일과 동일)

    lines = ["🎯 매수 타이밍 포착"]
    for s in signals:
        block = f"\n[{s.get('alert_kind', '매수')}] {s['ticker']} → {s['action']} · {s.get('setup', '')}"
        entry = s.get("entry")
        price = float(s.get("price") or 0)
        if entry:
            gap = (price / float(entry) - 1) * 100 if price > 0 else 0
            if gap > _BUY_NEAR_PCT:
                tag = f"⚠️ 이미 +{gap:.1f}% — 추격 금지, {entry:,.2f} 눌림 대기"
            elif gap < -1:
                tag = f"🟢 진입가 아래({gap:+.1f}%) — 매수 유리"
            else:
                tag = f"🟢 진입가 근접({gap:+.1f}%) — 분할매수 가능"
            block += f"\n   현재 {price:,.2f} · 진입목표 {entry:,.2f} · {tag}"
            block += f"\n   손절 {s['stop']:,.2f} · 목표 {s['target']:,.2f} (1:{s['rr']})"
        v = s.get("valuation", {})
        if v.get("verdict"):
            block += f"\n   밸류 {v['verdict']}"
        lines.append(block)
    lines.append(f"\n📲 상세 → {LINK}")
    return "\n".join(lines)


def run_watchlist_check() -> Dict[str, Any]:
    """cron 진입점: 관심+보유종목 매수 타이밍 → 신규 전환분만 카카오 발송."""
    os.environ.setdefault("STOCK_AGENT_USER", "admin")  # 세션 없으므로 대상 고정
    stance = "aggressive"
    try:
        from ui.pages._meta import load_meta, resolve_stance
        if not load_meta().get("watchlist_alert_enabled", True):
            return {"checked": False, "reason": "관심종목 알림 OFF"}
        stance = resolve_stance()
    except Exception as e:
        print(f"메타 로드 실패(기본값 사용): {e}")

    result = detect_buy_timings(stance=stance)
    newly = result["newly"]
    if not newly:
        return {"checked": True, "new_count": 0, "kakao_sent": False}

    sent = False
    try:
        from modules.kakao_notify import send_kakao_memo, is_configured
        if is_configured():
            sent = send_kakao_memo(format_alert(newly))
    except Exception as e:
        print(f"관심종목 알림 발송 실패: {e}")
    return {"checked": True, "new_count": len(newly), "kakao_sent": sent,
            "tickers": [s["ticker"] for s in newly]}
