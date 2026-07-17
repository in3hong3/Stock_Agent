"""핫 섹터 탭 서비스 — Streamlit ui/pages/hot_sectors.py의 기능을 FastAPI용으로.

섹터 스캔(scan_sectors)·AI 해설(explain_sector)·종목 스코어링(score_stocks)은
modules/sector_scanner를 그대로 재사용. @st.cache_data는 프로세스 TTL 캐시로 대체.
AI 해설·스코어링은 LLM 비용이라 버튼(HTMX POST)으로만 실행한다.
"""
import time

from web.services.paper import md_to_html  # 마크다운→HTML 재사용

_scan_cache: dict = {}   # include_themes(bool) -> (ts, scan)
_SCAN_TTL = 1800


def _scan(include_themes: bool, refresh: bool = False) -> dict:
    from modules.sector_scanner import scan_sectors
    key = bool(include_themes)
    now = time.time()
    hit = _scan_cache.get(key)
    if refresh or not hit or now - hit[0] > _SCAN_TTL:
        scan = scan_sectors(include_themes=include_themes)
        _scan_cache[key] = (now, scan)
        return scan
    return hit[1]


def _cls(v) -> str:
    if isinstance(v, (int, float)):
        return "c-up" if v > 0 else "c-down" if v < 0 else "c-flat"
    return "c-muted"


def _fmt(v, spec="%+.1f") -> str:
    return (spec % v) if isinstance(v, (int, float)) else "-"


def get_context(include_themes: bool = True, refresh: bool = False) -> dict:
    scan = _scan(include_themes, refresh=refresh)
    if scan.get("error"):
        return {"include_themes": include_themes, "error": scan["error"],
                "hot_cards": [], "table_rows": [], "hot_options": []}

    rows = scan.get("rows", [])
    hot = [r for r in rows if r.get("hot")]

    hot_cards = [{
        "name": r["name"], "ticker": r["ticker"], "kind": r["kind"],
        "r_1m": _fmt(r["r_1m"]), "r_1m_cls": _cls(r["r_1m"]),
        "rs_1m": _fmt(r["rs_1m"]), "rs_1m_cls": _cls(r["rs_1m"]),
    } for r in hot]

    table_rows = [{
        "ticker": r["ticker"], "name": r["name"], "kind": r["kind"],
        "cells": [
            {"s": _fmt(r["r_1w"]), "cls": _cls(r["r_1w"])},
            {"s": _fmt(r["r_1m"]), "cls": _cls(r["r_1m"])},
            {"s": _fmt(r["r_3m"]), "cls": _cls(r["r_3m"])},
            {"s": _fmt(r["rs_1m"]), "cls": _cls(r["rs_1m"])},
        ],
        "score": _fmt(r["momentum_score"], "%.1f"),
    } for r in rows]

    hot_options = [{
        "ticker": r["ticker"],
        "label": f"{r['name']} · 1개월 {_fmt(r['r_1m'])}% (벤치대비 {_fmt(r['rs_1m'])}%p)",
    } for r in hot]

    return {
        "include_themes": include_themes,
        "error": None,
        "generated": scan.get("generated", ""),
        "benchmark_1m": scan.get("benchmark_1m"),
        "hot_cards": hot_cards,
        "table_rows": table_rows,
        "hot_options": hot_options,
        "hot_names": " · ".join(r["name"].split(" (")[0] for r in hot[:5]),
    }


def explain(include_themes: bool, ticker: str) -> dict:
    """AI 섹터 해설 (LLM 웹검색). {html, for_name}."""
    from modules.sector_scanner import explain_sector
    from modules.issue_tracker import get_portfolio_holdings

    scan = _scan(include_themes)
    row = next((r for r in scan.get("rows", []) if r["ticker"] == ticker), None)
    if not row:
        return {"html": "<div class='muted-sm'>선택한 섹터 데이터를 찾을 수 없습니다.</div>", "for_name": ""}
    text = explain_sector(scan, ticker, holdings=get_portfolio_holdings())
    return {"html": md_to_html(text), "for_name": row["name"]}


def score(query: str) -> dict:
    """종목 스코어링 (LLM 웹검색). {html}."""
    from modules.sector_scanner import score_stocks
    from modules.issue_tracker import get_portfolio_holdings

    if not (query or "").strip():
        return {"html": "<div class='muted-sm'>섹터명 또는 티커를 입력하세요.</div>"}
    text = score_stocks(query.strip(), holdings=get_portfolio_holdings())
    return {"html": md_to_html(text)}
