"""내 종목 트래커 탭 서비스 — ui/pages/tracker.py를 FastAPI용으로.

시그널(generate_signals)·적중률·자산추이·유튜버집단지성·뉴스 표시 + 이슈브리핑/AI평가(LLM 버튼).
@st.cache_data는 프로세스 TTL 캐시로 대체. 사용자별 데이터라 current_user 바인딩 필수.
보류: 진입 시 자동 가격채움(auto_fill_missing_prices) — 포트폴리오 탭의 '가격 업데이트'로 대체.
"""
import time

from web.services.meta import load_meta
from web.services.backtest import _line_svg

_sig_cache: dict = {}      # key -> (ts, result)
_news_cache: dict = {}     # ticker -> (ts, list)
_yt_cache: dict = {"ts": 0.0, "rows": None}


def _holdings():
    from modules.issue_tracker import get_portfolio_holdings
    return get_portfolio_holdings()


def _resolve_stance() -> str:
    """web에는 session_state가 없으므로 meta에 저장된 값 또는 기본 aggressive."""
    from modules.portfolio_advisor import PERSONAS
    saved = load_meta().get("advisor_stance", "")
    for k in PERSONAS:
        if k == saved:
            return k
    return "aggressive"


def _signals(holdings, stance, seed, risk):
    from modules.trade_signal import generate_signals
    key = (tuple((h["ticker"], h["quantity"], h["avg_price"], h.get("current_price", 0))
                 for h in holdings), stance, seed, risk)
    now = time.time()
    hit = _sig_cache.get(key)
    if hit and now - hit[0] <= 900:
        return hit[1]
    res = generate_signals(holdings, stance, seed, risk)
    _sig_cache[key] = (now, res)
    return res


def _news(ticker: str):
    from modules.issue_tracker import fetch_ticker_news
    now = time.time()
    hit = _news_cache.get(ticker)
    if hit and now - hit[0] <= 600:
        return hit[1]
    val = fetch_ticker_news(ticker, max_news=6)
    _news_cache[ticker] = (now, val)
    return val


def _yt_rows():
    from modules.youtuber_consensus import scan_summary_meta
    now = time.time()
    if _yt_cache["rows"] is None or now - _yt_cache["ts"] > 1800:
        _yt_cache["rows"] = scan_summary_meta()
        _yt_cache["ts"] = now
    return _yt_cache["rows"]


def get_context() -> dict:
    from modules.portfolio_advisor import PERSONAS
    holdings = _holdings()
    if not holdings:
        return {"empty": True, "personas": _persona_list(PERSONAS)}

    tickers = [h["ticker"] for h in holdings]
    name_by_tk = {h["ticker"]: (h.get("name") or h["ticker"]) for h in holdings}
    meta = load_meta()
    stance = _resolve_stance()
    seed = float(meta.get("trading_seed", 0) or 0)
    risk = float(meta.get("risk_pct", 1.0) or 1.0)

    ctx = {"empty": False, "tickers": tickers, "seed": seed, "risk": risk,
           "personas": _persona_list(PERSONAS), "stance": stance,
           "missing_price": [h for h in holdings
                             if not h.get("current_price") or float(h.get("current_price", 0) or 0) <= 0]}

    # 시그널
    try:
        sig = _signals(holdings, stance, seed, risk)
        ctx["regime"] = sig.get("regime", {})
        ctx["signals"] = sig.get("signals", [])
        ctx["fundamentals"] = sorted(
            (s for s in sig.get("signals", []) if s.get("valuation")),
            key=lambda s: -(s.get("valuation", {}).get("score", 0)))
        ctx["name_by_tk"] = name_by_tk
    except Exception as e:
        print(f"[tracker] 시그널 실패: {e}")
        ctx["signals"] = []
        ctx["fundamentals"] = []

    # 적중률
    try:
        from modules.signal_tracker import get_accuracy_stats
        ctx["accuracy"] = get_accuracy_stats()
    except Exception as e:
        print(f"[tracker] 적중률 실패: {e}")
        ctx["accuracy"] = {}

    # 자산 추이
    try:
        from utils.portfolio_utils import load_asset_history
        hist = load_asset_history()
        if len(hist) >= 2:
            ctx["asset_svg"] = _line_svg([
                {"name": "총자산", "color": "#00FFA3", "values": hist["total"].tolist()},
                {"name": "주식", "color": "#4B7BFF", "values": hist["stock"].tolist()},
                {"name": "현금", "color": "#94A3B8", "values": hist["cash"].tolist()},
            ])
            first, last = hist["total"].iloc[0], hist["total"].iloc[-1]
            ctx["asset_change"] = (last / first - 1) * 100 if first > 0 else 0
            ctx["asset_days"] = len(hist)
    except Exception as e:
        print(f"[tracker] 자산추이 실패: {e}")

    # 유튜버 집단지성
    try:
        from modules.youtuber_consensus import consensus_for, radar, sentiment_shift
        rows = _yt_rows()
        con = consensus_for(rows, tickers, days=90)
        ctx["yt_count"] = len(rows)
        ctx["yt_consensus"] = [{
            "ticker": tk, "total": con[tk]["total"], "score": con[tk]["score"],
            "buy": con[tk]["buy"], "neutral": con[tk]["neutral"], "caution": con[tk]["caution"],
            "tone": ("🟢 매수 우위" if con[tk]["score"] > 20 else
                     "🔴 주의 우위" if con[tk]["score"] < -20 else "⚪ 중립"),
        } for tk in tickers]
        ctx["yt_shifts"] = sentiment_shift(rows, tickers)
        ctx["yt_radar"] = radar(rows, set(tickers), top_n=8, days=90)
    except Exception as e:
        print(f"[tracker] 유튜버집단지성 실패: {e}")
        ctx["yt_consensus"] = []

    # 종목별 뉴스
    news = {}
    for h in holdings:
        try:
            news[h["ticker"]] = {"name": h.get("name") or h["ticker"], "items": _news(h["ticker"])}
        except Exception as e:
            news[h["ticker"]] = {"name": h["ticker"], "items": [], "error": str(e)}
    ctx["news"] = news

    return ctx


def _persona_list(PERSONAS) -> list[dict]:
    return [{"key": k, "label": v["label"], "desc": v["description"]} for k, v in PERSONAS.items()]


# ── LLM 액션 (HTMX) ──
def briefing(sel_tickers: list[str]) -> dict:
    from modules.issue_tracker import summarize_all_issues
    if not sel_tickers:
        return {"error": "브리핑할 종목을 1개 이상 선택하세요."}
    holdings_news = {t: _news(t) for t in sel_tickers}
    text = summarize_all_issues(holdings_news)
    import datetime
    from web.services.paper import md_to_html
    return {"html": md_to_html(text), "time": datetime.datetime.now().strftime("%H:%M")}


def ai_eval(stance: str, force: bool = False) -> dict:
    from modules.portfolio_advisor import get_or_create_eval, PERSONAS
    from utils.web_llm import get_search_provider
    from web.services.paper import md_to_html
    if not get_search_provider():
        return {"error": "검색 LLM 키가 없습니다 (.env PERPLEXITY_API_KEY)."}
    holdings = _holdings()
    if stance not in PERSONAS:
        stance = "aggressive"
    result = get_or_create_eval(holdings, stance, force=force)
    return {"html": md_to_html(result["text"]), "time": result["time"],
            "cached": result.get("cached"), "label": PERSONAS[stance]["label"]}
