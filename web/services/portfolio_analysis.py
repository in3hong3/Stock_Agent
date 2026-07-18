"""포트폴리오 분석 서브탭 서비스 — 종목상세/시각화/알림/리밸런싱/개인화챗봇.

전부 온디맨드(버튼 클릭 시). RAG 엔진은 무거워 지연 싱글턴. 시각화는 plotly 대신 인라인 SVG.
보류: 섹터 분류(SectorClassifier, 네트워크) — 종목 단위 비중/손익으로 대체.
"""
import math

from web.services.paper import md_to_html

_rag = None
_pchat: dict = {}   # uid -> [messages]

_PIE_COLORS = ["#00FFA3", "#4B7BFF", "#FFA500", "#FF4B4B", "#A855F7", "#00D9F5",
               "#FFD700", "#90EE90", "#FF6B9D", "#94A3B8"]


def _rag_engine():
    global _rag
    if _rag is None:
        from core.rag_engine import RAGEngine
        _rag = RAGEngine()
    return _rag


def _df():
    from web.services.portfolio import _load_df, _pf_path
    import os
    if not os.path.exists(_pf_path()):
        return None
    from utils.portfolio_utils import calc_portfolio_metrics
    return calc_portfolio_metrics(_load_df())


# ── 📋 종목상세 (분석 실행) ──
def analyze() -> dict:
    df = _df()
    if df is None or df.empty:
        return {"error": "포트폴리오가 비어 있습니다."}
    from modules.portfolio_analyzer import PortfolioAnalyzer
    result = PortfolioAnalyzer(_rag_engine()).analyze_portfolio(df)
    if result.get("status") != "success":
        return {"error": result.get("message", "분석 실패")}
    s = result.get("summary", {})
    stocks = []
    for a in result.get("stock_analyses", []):
        info = a.get("current_info", {})
        stocks.append({
            "name": a.get("name", ""), "ticker": a.get("ticker", ""),
            "quantity": info.get("quantity", 0), "profit_rate": info.get("profit_rate", 0),
            "feedback_html": md_to_html(a.get("ai_feedback", "")),
            "rag": [{"title": i.get("metadata", {}).get("영상제목", "N/A"),
                     "link": i.get("metadata", {}).get("영상링크", "#")}
                    for i in a.get("rag_insights", [])[:3]],
        })
    return {"summary": s, "stocks": stocks}


# ── 📊 시각화 (인라인 SVG) ──
def viz() -> dict:
    df = _df()
    if df is None or df.empty:
        return {"error": "포트폴리오가 비어 있습니다."}
    rows = [(str(r["ticker"]), float(r["eval_amount"]), float(r["profit_rate"]))
            for _, r in df.iterrows() if float(r["eval_amount"]) > 0]
    rows.sort(key=lambda x: -x[1])
    pie = _pie_svg([(tk, ev) for tk, ev, _ in rows])
    mx = max((abs(pr) for _, _, pr in rows), default=1) or 1
    bars = [{"label": tk, "value": pr, "pct": abs(pr) / mx * 100,
             "cls": "c-up" if pr >= 0 else "c-down"} for tk, _, pr in rows]
    return {"pie_svg": pie, "bars": bars}


def _pie_svg(items: list, size: int = 220) -> str:
    total = sum(v for _, v in items) or 1
    cx = cy = size / 2
    rad = size / 2 - 4
    angle = -math.pi / 2
    paths, legend = [], []
    for i, (label, val) in enumerate(items):
        frac = val / total
        a2 = angle + frac * 2 * math.pi
        x1, y1 = cx + rad * math.cos(angle), cy + rad * math.sin(angle)
        x2, y2 = cx + rad * math.cos(a2), cy + rad * math.sin(a2)
        large = 1 if frac > 0.5 else 0
        color = _PIE_COLORS[i % len(_PIE_COLORS)]
        paths.append(f'<path d="M{cx:.1f},{cy:.1f} L{x1:.1f},{y1:.1f} '
                     f'A{rad:.1f},{rad:.1f} 0 {large} 1 {x2:.1f},{y2:.1f} Z" fill="{color}"/>')
        legend.append(f'<span style="color:{color};">■</span> {label} {frac*100:.0f}%')
        angle = a2
    return (f'<svg viewBox="0 0 {size} {size}" style="width:220px;height:220px;">{"".join(paths)}</svg>'
            f'<div class="muted-sm" style="display:flex;flex-wrap:wrap;gap:8px;">{" ".join(legend)}</div>')


# ── 🔔 알림 ──
def alerts() -> dict:
    df = _df()
    if df is None or df.empty:
        return {"error": "포트폴리오가 비어 있습니다."}
    from modules.portfolio_alert import PortfolioAlert
    alert_sys = PortfolioAlert(_rag_engine())
    found = alert_sys.check_portfolio_alerts(df, days_back=7)
    return {"html": md_to_html(alert_sys.format_alerts(found))}


# ── ⚖️ 리밸런싱 ──
def rebalance() -> dict:
    df = _df()
    if df is None or df.empty:
        return {"error": "포트폴리오가 비어 있습니다."}
    from modules.portfolio_rebalancer import PortfolioRebalancer
    result = PortfolioRebalancer(_rag_engine()).generate_rebalancing_suggestions(df)
    if result.get("status") != "success":
        return {"error": result.get("message", "리밸런싱 분석 실패")}
    bal = result.get("current_balance", {})
    risk = bal.get("risk_metrics", {})
    sim = result.get("simulation", {}) or {}
    return {
        "total_value": bal.get("total_value", 0),
        "avg_profit": risk.get("avg_profit_rate", 0),
        "losing_ratio": risk.get("losing_stocks_ratio", 0),
        "sector_weights": bal.get("sector_weights", {}),
        "suggestions_html": md_to_html(result.get("suggestions", {}).get("full_text", "")),
        "total_cost": sim.get("total_cost"), "cost_ratio": sim.get("cost_ratio"),
    }


# ── 💬 개인화 챗봇 ──
def pchat_history(uid: str) -> list:
    return _pchat.get(uid, [])


def personalized_chat(uid: str, query: str) -> list:
    from web.services.analysts import _esc, _err
    _pchat.setdefault(uid, []).append({"role": "user", "content_html": _esc(query)})
    try:
        from core.personalized_rag import PersonalizedRAG
        engine = PersonalizedRAG(_rag_engine())
        hist = [{"role": m["role"], "content": m.get("content_html", "")}
                for m in _pchat[uid][-6:]]
        result = engine.chat(query=query, top_k=10, temperature=0.7,
                             conversation_history=hist or None, use_portfolio_context=True)
        _pchat[uid].append({
            "role": "assistant", "content_html": md_to_html(result.get("answer", "답변 실패")),
            "sources": result.get("sources", []),
            "followups": result.get("followup_questions", []),
        })
    except Exception as e:
        _pchat[uid].append({"role": "assistant", "content_html": _err(e)})
    return _pchat[uid]
