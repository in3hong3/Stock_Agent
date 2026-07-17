"""🧠 AI 신호 탭 서비스 — 표시 전용. ml_signals.py 로직을 FastAPI용으로.

로컬 GPU가 만든 JSON 3개만 읽는다 (추론 없음, 서버에 torch 없음):
  data/market_scan.json          → 데일리 판정 (cron 생성)
  ml/signals/latest.json         → 상승확률 (수익률 모델)
  ml/signals/patterns_latest.json→ 패턴 감지 (이중바닥)
thumb는 data:image/png;base64 URI라 <img>에 그대로 사용.
"""
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SIGNALS_DIR = _ROOT / "ml" / "signals"
_SCAN_JSON = _ROOT / "data" / "market_scan.json"
_DETECT_THRESHOLD = 0.5


def _load(path: Path) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _approx_months(trading_days: int) -> str:
    months = round((trading_days or 0) / 21)
    return f"약 {months}개월" if months >= 1 else f"{trading_days}거래일"


def _is_korean(ticker: str) -> bool:
    t = (ticker or "").upper()
    return t.endswith((".KS", ".KQ")) or (t.isdigit() and len(t) == 6)


def _held_map() -> dict:
    try:
        from modules.issue_tracker import get_portfolio_holdings
        return {h["ticker"].upper(): h for h in get_portfolio_holdings()}
    except Exception as e:
        print(f"[ml] 포트폴리오 로드 실패: {e}")
        return {}


# ── 데일리 판정 ──
def _daily() -> dict:
    data = _load(_SCAN_JSON)
    if not data:
        return {"available": False}

    def _verdict_cls(line: str) -> str:
        if line.startswith("🔴"):
            return "v-red"
        if line.startswith("🟡"):
            return "v-yellow"
        if line.startswith("🟢"):
            return "v-green"
        return "v-info"

    def _rows(rows):
        return [{
            "ticker": r["ticker"], "name": r.get("name", ""), "price": f"{r['price']:,}",
            "ret10": r["ret10"], "ret21": r["ret21"], "off_high": r["off_high"],
            "ma200": "위" if r["above_ma200"] else "⚠ 아래",
            "ma50": "위" if r["above_ma50"] else "아래",
            "flags": " ".join(r.get("flags", [])) or "-",
        } for r in rows]

    return {
        "available": True,
        "generated_at": data.get("generated_at", "-"),
        "verdict": [{"cls": _verdict_cls(l), "text": l} for l in data.get("verdict", [])],
        "market_rows": _rows(data.get("market", [])),
        "holdings_rows": _rows(data.get("holdings", [])),
    }


# ── 상승확률 (수익률 모델) ──
def _return_model(held_map: dict) -> dict:
    data = _load(_SIGNALS_DIR / "latest.json")
    if not data:
        return {"available": False}

    hor_txt = _approx_months(data.get("horizon_days", 20))
    win_txt = _approx_months(data.get("window_days", 120))
    signals = {s["ticker"].upper(): s for s in data.get("signals", [])}
    matched = [(t, h) for t, h in held_map.items() if t in signals]
    missing = [t for t in held_map if t not in signals]
    auc = data.get("val_auc")

    def _row(sig: dict, held: dict | None) -> dict:
        prob = float(sig.get("prob_up", 0.0) or 0.0)
        name = (held or {}).get("name") or sig.get("name", sig["ticker"])
        held_txt = ""
        if held:
            cur = held.get("current_price", 0) or 0
            held_txt = f"📦 보유 {held.get('quantity', 0):g}주" + (f" · 현재가 {cur:,.2f}" if cur > 0 else "")
        return {
            "thumb": sig.get("thumb", ""), "name": name, "ticker": sig["ticker"],
            "held_txt": held_txt, "prob": prob, "prob_pct": f"{prob:.1%}",
            "prob_w": max(0.0, min(100.0, prob * 100)), "as_of": sig.get("as_of", "-"),
        }

    if held_map:
        rows_src = sorted(matched, key=lambda x: signals[x[0]].get("prob_up", 0.0), reverse=True)
        rows = [_row(signals[t], h) for t, h in rows_src]
        held_count = f"{len(matched)} / {len(held_map)}"
    else:
        rows_src = sorted(signals.values(), key=lambda s: s.get("prob_up", 0.0), reverse=True)
        rows = [_row(s, None) for s in rows_src]
        held_count = f"{len(signals)}개"

    extras = [signals[t] for t in signals if t not in held_map]
    extras_rows = ([_row(s, None) for s in sorted(extras, key=lambda s: s.get("prob_up", 0.0), reverse=True)]
                   if held_map and extras else [])

    return {
        "available": True,
        "generated_at": data.get("generated_at", "-"),
        "win_txt": win_txt, "hor_txt": hor_txt,
        "auc_str": f"{auc:.3f}" if isinstance(auc, (int, float)) else "N/A",
        "held_count": held_count,
        "ref_missing": [t for t in missing if not _is_korean(t)],
        "kr_missing": [t for t in missing if _is_korean(t)],
        "rows": rows, "extras": extras_rows,
    }


# ── 패턴 감지 ──
def _pattern_model(held_map: dict) -> dict:
    data = _load(_SIGNALS_DIR / "patterns_latest.json")
    if not data:
        return {"available": False}

    stats = data.get("event_stats", {})
    pattern_kr = stats.get("pattern_kr", "이중바닥")
    scans = data.get("scans", [])
    detected = [s for s in scans if s.get("prob_pattern", 0) >= _DETECT_THRESHOLD]
    auc = data.get("val_auc", 0)

    def _card(s: dict) -> dict:
        prob = float(s.get("prob_pattern", 0.0) or 0.0)
        held = held_map.get(s["ticker"].upper())
        name = (held or {}).get("name") or s.get("name", s["ticker"])
        return {
            "thumb": s.get("thumb", ""), "name": name, "ticker": s["ticker"],
            "held_txt": f"📦 보유 {held.get('quantity', 0):g}주" if held else "",
            "prob_pct": f"{prob:.1%}", "prob_w": max(0.0, min(100.0, prob * 100)),
            "rule": " · ✓ 규칙 탐지기도 최근 확정" if s.get("rule_confirmed_recent") else "",
            "as_of": s.get("as_of", "-"),
        }

    return {
        "available": True,
        "generated_at": data.get("generated_at", "-"),
        "pattern_kr": pattern_kr,
        "auc_str": f"{auc:.3f}" if isinstance(auc, (int, float)) else "N/A",
        "win_txt": _approx_months(data.get("window_days", 120)),
        "scan_count": len(scans), "detected_count": len(detected),
        "detected": [_card(s) for s in detected],
        "all_scans": [{
            "ticker": s["ticker"], "name": s.get("name", ""),
            "prob_pct": f"{float(s.get('prob_pattern', 0.0) or 0.0):.1%}",
            "prob_w": max(0.0, min(100.0, float(s.get("prob_pattern", 0.0) or 0.0) * 100)),
        } for s in scans],
        "stats_summary": stats.get("summary", ""),
        "n_events": stats.get("n_events", "-"),
    }


def get_context() -> dict:
    held_map = _held_map()
    return {
        "daily": _daily(),
        "ret": _return_model(held_map),
        "pattern": _pattern_model(held_map),
    }
