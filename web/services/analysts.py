"""분석관 탭 서비스 — ui/pages/analysts.py를 FastAPI용으로.

진입점검(규칙기반·무료) + RAG/기술/뉴스/종합(LLM). 기존 Streamlit도 토큰 스트리밍이
아니라 요청/응답이므로 HTMX POST로 충분. 대화 기록은 사용자별 인메모리(세션 유사).
에이전트/라우터는 무거우므로 지연 싱글턴.
"""
import traceback

from web.services.paper import md_to_html

_router = None
_news_agent = None
_chat: dict = {}   # (uid, kind) -> [ {role, content_html, sources, followups} ]


def _get_router():
    global _router
    if _router is None:
        from agents.router import AgenticRouter
        _router = AgenticRouter()
    return _router


def _get_news_agent():
    global _news_agent
    if _news_agent is None:
        from agents.news_agent import NewsAgent
        _news_agent = NewsAgent()
    return _news_agent


def history(uid: str, kind: str) -> list:
    return _chat.get((uid, kind), [])


def _append(uid, kind, msg):
    _chat.setdefault((uid, kind), []).append(msg)


# ── 🎯 진입 점검 (규칙 기반) ──
def entry_check(ticker_input: str, stance: str) -> dict:
    from modules.issue_tracker import resolve_ticker
    from modules.trade_signal import get_market_regime, analyze_stock, decide_action, _PROFILE
    from modules.portfolio_advisor import PERSONAS

    if not (ticker_input or "").strip():
        return {"error": "종목을 입력하세요."}
    if stance not in PERSONAS:
        stance = "expert" if "expert" in PERSONAS else next(iter(PERSONAS))
    tk = resolve_ticker(ticker_input.strip())
    regime = get_market_regime()
    analysis = analyze_stock(tk, 0, 0)
    if "error" in analysis:
        return {"error": f"{tk}: {analysis['error']} — 티커를 확인하세요."}
    decision = decide_action(analysis, stance, regime["score_modifier"])
    r = {"regime": regime, **analysis, **decision}

    buy_th, strong_th, sell_th = _PROFILE.get(stance, _PROFILE.get("neutral"))[:3]
    score = r["adj_score"]
    if score >= strong_th:
        verdict, vcolor, vicon = "지금 진입 가능 (적극)", "#00FFA3", "🟢🟢"
    elif score >= buy_th:
        verdict, vcolor, vicon = "분할 진입 고려", "#1D9E75", "🟢"
    elif score <= sell_th:
        verdict, vcolor, vicon = "진입 비추천 — 지금은 피하기", "#FF4B4B", "🔴"
    else:
        verdict, vcolor, vicon = "관망 — 더 좋은 자리 대기", "#FFD700", "⚪"

    v = r.get("valuation", {})
    return {
        "ticker": tk, "stance_label": PERSONAS[stance]["label"], "regime_label": regime["label"],
        "verdict": verdict, "vcolor": vcolor, "vicon": vicon, "score": score, "setup": r.get("setup", ""),
        "rsi": r.get("rsi"), "macd_hist": r.get("macd_hist"), "adx": r.get("adx"),
        "trend_regime": r.get("trend_regime"), "wk_trend": r.get("wk_trend"),
        "valuation": v, "eps_growth": v.get("eps_growth"),
        "inst_pct": v.get("inst_pct"), "inst_change_pp": v.get("inst_change_pp"),
        "insider_buying": v.get("insider_buying"),
        "entry": r.get("entry"), "stop": r.get("stop"), "target": r.get("target"), "rr": r.get("rr"),
        "plan": r.get("plan"), "reasons": r.get("reasons", []), "extra": r.get("extra", []),
        "support": r.get("support"), "resistance": r.get("resistance"),
        "ma50": r.get("ma50"), "ma200": r.get("ma200"), "price": r.get("price"),
    }


# ── 💬 RAG 채팅 ──
def rag_chat(uid: str, query: str) -> list:
    _append(uid, "rag", {"role": "user", "content_html": _esc(query)})
    try:
        hist = [{"role": m["role"], "content": m.get("content_html", "")}
                for m in history(uid, "rag")[-6:]]
        result = _get_router().rag_agent.process(query=query, conversation_history=hist or None)
        _append(uid, "rag", {
            "role": "assistant", "content_html": md_to_html(result.get("answer", "답변 생성 실패")),
            "sources": result.get("sources", []), "followups": result.get("followup_questions", []),
        })
    except Exception as e:
        _append(uid, "rag", {"role": "assistant", "content_html": _err(e)})
    return history(uid, "rag")


# ── 💬 기술분석 채팅 ──
def tech_chat(uid: str, query: str) -> list:
    _append(uid, "tech", {"role": "user", "content_html": _esc(query)})
    try:
        result = _get_router().tech_agent.process(query=query)
        ind = result.get("indicators") or {}
        if ind and "error" not in ind:
            body = result.get("analysis", "") + _fmt_indicators(ind)
        else:
            body = f"⚠️ 분석 실패: {ind.get('error', '알 수 없는 오류')}"
        _append(uid, "tech", {"role": "assistant", "content_html": md_to_html(body)})
    except Exception as e:
        _append(uid, "tech", {"role": "assistant", "content_html": _err(e)})
    return history(uid, "tech")


# ── 💬 종합분석 채팅 ──
def comprehensive_chat(uid: str, query: str, agents: list) -> list:
    _append(uid, "comp", {"role": "user", "content_html": _esc(query)})
    try:
        result = _get_router().route(query=query, force_agents=agents)
        tags = {"rag": "🎥영상분석", "quant": "📊가치평가", "tech": "📈기술적분석"}
        used = " + ".join(tags[a] for a in agents if a in tags)
        body = result.get("answer", "답변 생성 실패") + f"\n\n---\n*⚙️ 참여: {used}*"
        _append(uid, "comp", {"role": "assistant", "content_html": md_to_html(body),
                              "sources": result.get("sources", [])})
    except Exception as e:
        _append(uid, "comp", {"role": "assistant", "content_html": _err(e)})
    return history(uid, "comp")


# ── 📰 뉴스분석 ──
def news_analyze(ticker: str, max_news: int) -> dict:
    if not (ticker or "").strip():
        return {"error": "티커를 입력하세요."}
    tk = ticker.strip().upper()
    try:
        result = _get_news_agent().process(f"{tk} 뉴스", ticker=tk, max_news=max_news)
    except Exception as e:
        return {"error": str(e)}
    a = result.get("analysis", {})
    score = a.get("sentiment_score", 50)
    return {
        "ticker": tk, "score": score, "sentiment": a.get("sentiment", "중립"),
        "bar_color": "#FF4B4B" if score < 40 else "#FFD700" if score < 60 else "#00FFA3",
        "news_count": a.get("news_count", len(result.get("news", []))),
        "topics": [t for t in a.get("key_topics", []) if t],
        "summary_html": md_to_html(a.get("summary", "분석 결과 없음")),
        "news": result.get("news", []),
    }


def clear(uid: str, kind: str):
    _chat.pop((uid, kind), None)


# ── helpers ──
def _fmt_indicators(ind: dict) -> str:
    return (f"\n\n---\n**[{ind.get('ticker', '?')}] 주요 지표**\n"
            f"- 현재가: ${ind.get('current_price')} ({ind.get('price_change_1d')}%)\n"
            f"- 추세: {ind.get('trend')} (MA20 ${ind.get('ma20')} / MA50 ${ind.get('ma50')})\n"
            f"- RSI: {ind.get('rsi')} → {ind.get('rsi_signal')}\n"
            f"- MACD: {ind.get('macd')} → {ind.get('macd_trend')}\n"
            f"- 볼린저 위치: {ind.get('bb_position')}% · 지지/저항 ${ind.get('support')}/${ind.get('resistance')}\n"
            f"- 52주: 고 ${ind.get('high_52w')} / 저 ${ind.get('low_52w')} · POC ${ind.get('poc')}\n")


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _err(e) -> str:
    return f"<div class='muted-sm' style='color:#FF6B6B;'>오류 발생: {_esc(str(e))}</div>"
