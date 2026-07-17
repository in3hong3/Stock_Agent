"""주간 유튜버 리포트 탭 서비스 — ui/pages/weekly_report.py를 FastAPI용으로.

insights/trackrecord/report/list는 JSON 읽기(무료), publish_weekly_report만 LLM.
report 본문은 발행 후에도 partial(_weekly_report.html)로 재사용.
"""
from web.services.paper import md_to_html


def _held_tickers() -> set:
    try:
        from modules.issue_tracker import get_portfolio_holdings
        return {h["ticker"] for h in get_portfolio_holdings() if h.get("ticker")}
    except Exception:
        return set()


def _score_cls(sc, hi=20, lo=-20) -> str:
    if sc > hi:
        return "c-up"
    if sc < lo:
        return "c-down"
    return "c-muted"


def _bar(buy, neutral, caution):
    total = (buy or 0) + (neutral or 0) + (caution or 0)
    if not total:
        return None
    return {"b": buy / total * 100, "n": neutral / total * 100, "c": caution / total * 100}


# ── 섹터 인사이트 / 시황 관점 ──
def _insights(held: set) -> dict:
    from modules.youtuber_insights import get_insights
    ins = get_insights()
    if not ins:
        return {"available": False}

    sf = ins.get("sector_focus", {})
    sectors = []
    for s in sf.get("sectors", [])[:12]:
        sectors.append({
            "sector": s["sector"], "score": s["score"], "score_cls": _score_cls(s["score"]),
            "delta": s.get("delta", 0), "total": s["total"],
            "buy": s["buy"], "neutral": s["neutral"], "caution": s["caution"],
            "top": ", ".join(s.get("top_tickers", [])[:5]),
            "held": "⭐" if held & set(s.get("top_tickers", [])) else "",
        })

    badge = {"경계": "🔴 경계", "기회": "🟢 기회", "중립": "⚪ 중립"}
    mv = [{"date": v["date"], "badge": badge.get(v["stance"], "⚪"),
           "title": v["title"], "thesis": v.get("thesis", "")}
          for v in ins.get("market_view", [])]
    n_caution = sum(1 for v in ins.get("market_view", []) if v["stance"] == "경계")
    n_opp = sum(1 for v in ins.get("market_view", []) if v["stance"] == "기회")
    tone = "경계 우위" if n_caution > n_opp else "기회 우위" if n_opp > n_caution else "중립"

    return {
        "available": True,
        "sectors": sectors, "sector_days": sf.get("window_days", 30),
        "recent_call_count": ins.get("recent_call_count", 0),
        "computed_at": ins.get("computed_at", ""),
        "market_view": mv, "mv_n": len(mv), "mv_opp": n_opp, "mv_caution": n_caution, "mv_tone": tone,
    }


def _trackrecord() -> dict:
    from modules.youtuber_trackrecord import get_trackrecord
    tr = get_trackrecord()
    if not tr:
        return {"available": False}
    win = tr.get("window", {})
    return {
        "available": True,
        "channel": tr.get("channel", "유튜버"),
        "win_start": win.get("start", ""), "win_end": win.get("end", ""),
        "total_calls": tr.get("total_calls", 0), "computed_at": tr.get("computed_at", ""),
        "buy_stats": tr.get("buy_stats", []), "caution_stats": tr.get("caution_stats", []),
        "ticker_rows": tr.get("ticker_rows", [])[:15],
        "best_calls": tr.get("best_calls", [])[:6], "worst_calls": tr.get("worst_calls", [])[:6],
    }


# ── 리포트 본문 ──
def _report_body(report: dict, held: set) -> dict:
    if not report:
        return {"available": False}
    period = report.get("period", {})

    top = []
    for t in report.get("top_mentions", [])[:15]:
        top.append({
            "name": t["name"], "ticker": t["ticker"],
            "held": "⭐ " if t["ticker"] in held else "",
            "bar": _bar(t["buy"], t["neutral"], t["caution"]),
            "total": t["total"], "score": t["score"], "score_cls": _score_cls(t["score"], 0, 0),
        })

    mine = []
    for v in report.get("videos", []):
        hit = held & set(v.get("tickers", []))
        if not hit:
            continue
        tags = " ".join(f"{tk}·{v.get('sentiments', {}).get(tk, '중립')}" for tk in hit)
        link = v.get("link", "")
        mine.append({
            "title": v.get("title", ""), "link": link if link.startswith("http") else "",
            "channel": v.get("channel", ""), "date": v.get("date", ""), "tags": tags,
        })
    mine = mine[:20]

    return {
        "available": True,
        "start": period.get("start", ""), "end": period.get("end", ""),
        "week_key": report.get("week_key", ""), "published_at": report.get("published_at", ""),
        "video_count": report.get("video_count", 0), "channel_count": report.get("channel_count", 0),
        "stock_count": report.get("stock_count", 0),
        "narrative_html": md_to_html(report.get("narrative", "")),
        "is_fallback": report.get("engine", "").startswith("fallback"),
        "surges": report.get("surges", []),
        "tone_flips": [{"ticker": f["ticker"], "prior": f["prior"], "now": f["now"],
                        "arrow": "🔻" if f["now"] == "주의우위" else "🔺"}
                       for f in report.get("tone_flips", [])],
        "top_mentions": top, "my_comments": mine, "has_held": bool(held),
    }


def get_context(chosen: str | None = None) -> dict:
    from modules.weekly_youtube_report import list_reports, week_key, get_report
    held = _held_tickers()

    keys = list_reports()
    this_key = week_key()
    options = keys if keys else [this_key]
    if this_key not in options:
        options = [this_key] + options
    chosen = chosen if chosen in options else options[0]

    return {
        "insights": _insights(held),
        "trackrecord": _trackrecord(),
        "week_options": [{"key": k, "label": f"{k} (이번 주)" if k == this_key else k,
                          "sel": k == chosen} for k in options],
        "chosen": chosen, "this_key": this_key,
        "report": _report_body(get_report(chosen), held),
    }


def publish() -> dict:
    """이번 주 다시 종합 (LLM). 리포트 본문 컨텍스트 반환."""
    from modules.weekly_youtube_report import publish_weekly_report
    report = publish_weekly_report()
    ctx = {"report": _report_body(report, _held_tickers())}
    ctx["toast"] = "📅 주간 리포트를 새로 종합했습니다"
    return ctx
