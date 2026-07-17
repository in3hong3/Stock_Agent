"""데일리 신문 탭 서비스 — Streamlit ui/pages/paper.py의 기능을 FastAPI용으로.

발행(publish_daily_paper)·저장(get_saved_paper) 등 로직은 modules/daily_paper를 그대로
재사용한다. Streamlit @st.cache_data는 여기서 간단한 프로세스 TTL 캐시로 대체.
사용자별 포트폴리오에 의존하므로 반드시 요청에서 current_user가 바인딩된 상태로 호출한다.
"""
import time

import markdown as _md

_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

# (키 -> (ts, value)) 형태의 아주 단순한 TTL 캐시
_cache: dict = {}


def _cached(key: str, ttl: int, fn):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] <= ttl:
        return hit[1]
    val = fn()
    _cache[key] = (now, val)
    return val


def md_to_html(text: str) -> str:
    """신문 본문 마크다운 → HTML (제목/굵게/목록/표)."""
    if not text:
        return ""
    return _md.markdown(text, extensions=["extra", "sane_lists", "nl2br"])


def _holdings():
    from modules.issue_tracker import get_portfolio_holdings
    return get_portfolio_holdings()


def _macro():
    from modules.market_overview import get_macro_data
    return _cached("macro", 300, get_macro_data)


def _news(tickers: tuple):
    from modules.daily_paper import fetch_holdings_news
    return _cached(f"news:{tickers}", 900,
                   lambda: fetch_holdings_news([{"ticker": t, "name": t} for t in tickers]))


def _filings(tickers: tuple):
    from modules.daily_paper import get_sec_filings
    return _cached(f"filings:{tickers}", 3600, lambda: get_sec_filings(list(tickers)))


def get_context() -> dict:
    """GET /t/paper 용 — 저장된 신문 + 시세판 + 일정 + 종목별 뉴스 (LLM 호출 없음)."""
    from modules.daily_paper import now_kst, get_saved_paper
    from modules.event_calendar import get_all_events, get_upcoming_events

    today = now_kst()
    holdings = _holdings()
    tickers = tuple(h["ticker"] for h in holdings)

    # 시세판 (변동률 있는 것만)
    try:
        macro = [m for m in _macro() if m.get("change_pct") is not None]
    except Exception as e:
        print(f"[paper] macro 실패: {e}")
        macro = []

    # 이번 주 일정 (7일)
    try:
        upcoming = get_upcoming_events(get_all_events(list(tickers)), days=7)[:6]
    except Exception as e:
        print(f"[paper] events 실패: {e}")
        upcoming = []

    # 종목별 뉴스
    try:
        news = _news(tickers) if tickers else {}
    except Exception as e:
        print(f"[paper] news 실패: {e}")
        news = {}

    saved = get_saved_paper()

    return {
        "date_str": today.strftime("%Y년 %m월 %d일"),
        "weekday": _WEEKDAYS[today.weekday()],
        "today_dot": today.strftime("%Y.%m.%d"),
        "paper_front_html": md_to_html(saved["front"]) if saved else "",
        "paper_time": saved.get("time") if saved else "",
        "macro": macro,
        "upcoming": upcoming,
        "news": news,
        "has_tickers": bool(tickers),
    }


def publish() -> dict:
    """발행 버튼 — 매크로+뉴스+공시 종합해 1면 발행. {front_html, time, status, engine}."""
    from modules.daily_paper import publish_daily_paper, now_kst

    holdings = _holdings()
    tickers = tuple(h["ticker"] for h in holdings)
    macro = _macro()
    news = _news(tickers) if tickers else {}
    filings = _filings(tickers) if tickers else []

    result = publish_daily_paper(macro, news, filings, holdings=holdings)
    engine = result.get("engine", "")
    engine_label = ""
    if engine.endswith("websearch"):
        engine_label = f" ({engine.split('-')[0].title()} 웹검색 🔍)"
    status_msg = {
        "unchanged": "새 소식이 없어 기존 신문을 유지합니다 (토큰 절약)",
        "updated": f"개정판 발행{engine_label}",
        "new": f"오늘의 신문이 발행되었습니다{engine_label}",
    }.get(result.get("status"), "발행 완료")

    return {
        "front_html": md_to_html(result["front"]),
        "time": result["time"],
        "status": result.get("status"),
        "status_msg": status_msg,
        "today_dot": now_kst().strftime("%Y.%m.%d"),
    }
