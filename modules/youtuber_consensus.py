"""유튜버 집단지성 — RAG summary 메타데이터(센티먼트/종목/연관/날짜) 집계. LLM 비용 없음.
영상 단위 집계라 '유튜버 N명'이 아니라 '영상 N개' 기준. 참고용."""
from collections import Counter
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from modules.daily_paper import now_kst

_NS = "stock-summaries"
_EXCLUDE = {"MARKET", "UNKNOWN", ""}


def scan_summary_meta() -> List[Dict[str, Any]]:
    """summary 네임스페이스의 모든 청크 메타데이터 수집 (UI에서 캐시해 사용)."""
    from utils.pinecone_store import PineconeStore
    ps = PineconeStore()
    out: List[Dict[str, Any]] = []
    for page in ps.index.list(namespace=_NS):
        if hasattr(page, "vectors"):
            ids = [it.id for it in page.vectors]
        elif isinstance(page, (list, tuple)):
            ids = list(page)
        else:
            ids = []
        if not ids:
            continue
        res = ps.index.fetch(ids=ids, namespace=_NS)
        vecs = res.get("vectors", {}) if isinstance(res, dict) else getattr(res, "vectors", {})
        for v in (vecs.values() if hasattr(vecs, "values") else vecs):
            m = (v.get("metadata", {}) if isinstance(v, dict) else getattr(v, "metadata", {})) or {}
            out.append({
                "ticker": m.get("ticker", ""),
                "sentiment": m.get("sentiment", "중립"),
                "date": m.get("업로드일자", ""),
                "channel": m.get("채널명", ""),
                "related": m.get("related_stocks", ""),
            })
    return out


def _parse_date(s) -> Optional[datetime.date]:
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(s)[:10], fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _within(rows, days):
    if not days:
        return rows
    cutoff = now_kst().date() - timedelta(days=days)
    keep = []
    for r in rows:
        d = _parse_date(r["date"])
        if d is None or d >= cutoff:  # 날짜 못 읽으면 보수적으로 포함
            keep.append(r)
    return keep


def _score(rows) -> Optional[int]:
    """센티먼트 점수 -100~+100 (매수 우위 - 주의 우위). 표본 없으면 None."""
    if not rows:
        return None
    sc = Counter(r["sentiment"] for r in rows)
    return round((sc.get("매수", 0) - sc.get("주의", 0)) / len(rows) * 100)


def consensus_for(rows, tickers, days: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
    rows = _within(rows, days)
    res = {}
    for tk in tickers:
        sub = [r for r in rows if r["ticker"] == tk]
        sc = Counter(r["sentiment"] for r in sub)
        res[tk] = {"buy": sc.get("매수", 0), "neutral": sc.get("중립", 0),
                   "caution": sc.get("주의", 0), "total": len(sub),
                   "score": _score(sub) or 0}
    return res


def radar(rows, held: set, top_n: int = 8, days: Optional[int] = 90) -> List[Dict[str, Any]]:
    """미보유인데 자주 다뤄진 종목 (지수 제외)."""
    rows = _within(rows, days)
    cnt = Counter(r["ticker"] for r in rows
                  if r["ticker"] not in _EXCLUDE and r["ticker"] not in held
                  and not r["ticker"].startswith("^"))
    out = []
    for tk, c in cnt.most_common(top_n):
        sub = [r for r in rows if r["ticker"] == tk]
        sc = Counter(r["sentiment"] for r in sub)
        out.append({"ticker": tk, "mentions": c, "score": _score(sub) or 0,
                    "buy": sc.get("매수", 0), "neutral": sc.get("중립", 0), "caution": sc.get("주의", 0)})
    return out


def sentiment_shift(rows, tickers, recent_days: int = 14, prior_days: int = 60,
                    min_delta: int = 25) -> List[Dict[str, Any]]:
    """최근 vs 그 이전 구간 센티먼트 점수 변화 → 톤 전환 감지."""
    today = now_kst().date()
    c_recent = today - timedelta(days=recent_days)
    c_prior = today - timedelta(days=prior_days)
    out = []
    for tk in tickers:
        rec, pri = [], []
        for r in rows:
            if r["ticker"] != tk:
                continue
            d = _parse_date(r["date"])
            if d is None:
                continue
            if d >= c_recent:
                rec.append(r)
            elif c_prior <= d < c_recent:
                pri.append(r)
        rs, ps = _score(rec), _score(pri)
        if rs is not None and ps is not None and len(rec) >= 2 and abs(rs - ps) >= min_delta:
            out.append({"ticker": tk, "recent": rs, "prior": ps, "delta": rs - ps,
                        "recent_n": len(rec), "prior_n": len(pri)})
    return out
