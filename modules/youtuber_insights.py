"""
유튜버 인사이트 — 섹터/테마 관심도 + 시황·경계 관점 타임라인

영상 메타데이터에서 '매수/주의' 라벨을 넘어선 두 신호를 뽑는다:
  A. 섹터/테마 관심도 — 최근 유튜버가 매수 쏠린 섹터(산업) + 지난 기간 대비 트렌드.
     ticker→산업 매핑(yfinance)만 있으면 되므로 집계 위주. '어느 섹터 볼까'에 답.
  B. 시황·경계 관점 타임라인 — 영상 제목+핵심논지에서 그가 지금 뭘 경계하고 뭘
     노리는지. 전용 시황(MARKET) 청크는 대부분 깨져 있어 제목이 실질 시황 신호.
     '뭘 조심/알아야'에 답.

무거운 부분(산업 매핑 yfinance)은 최근 언급 종목만 → 가볍다. 주 1회 cron 계산 후
data/youtuber_insights.json 저장, UI는 읽기만.
"""
import os
import re
import json
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from modules.daily_paper import now_kst

_NS = "stock-summaries"
_EXCLUDE = {"MARKET", "UNKNOWN", "", "보류", "보유"}

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INSIGHTS_FILE = os.path.join(_BASE_DIR, "data", "youtuber_insights.json")

# 제목 스탠스 분류 키워드
_CAUTION_KW = re.compile(
    r"하락|조정|주의|경계|위험|리스크|쉬어|급락|폭락|고점|변동성|공포|던지지|두려|불안|약세|하방")
_OPP_KW = re.compile(
    r"기회|매수|반등|상승|신고가|돌파|저점|바닥|강세|주도주|모멘텀|노리|담아|잡자")


def _parse_date(s) -> Optional[datetime]:
    for f in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(s)[:10], f)
        except (ValueError, TypeError):
            continue
    return None


def _scan(days: int):
    """최근 days*2일치 (이번/이전 기간 비교용) 콜 + 영상 스캔."""
    from utils.pinecone_store import PineconeStore
    ps = PineconeStore()
    cutoff = (now_kst() - timedelta(days=days * 2)).date()

    calls = []          # (ticker, date, sentiment)
    videos = {}         # link -> {date,title,thesis}
    seen_pair = set()
    for page in ps.index.list(namespace=_NS):
        ids = [it.id for it in page.vectors] if hasattr(page, "vectors") else list(page)
        if not ids:
            continue
        res = ps.index.fetch(ids=ids, namespace=_NS)
        vecs = res.get("vectors", {}) if isinstance(res, dict) else getattr(res, "vectors", {})
        for v in (vecs.values() if hasattr(vecs, "values") else vecs):
            m = (v.get("metadata", {}) if isinstance(v, dict) else getattr(v, "metadata", {})) or {}
            d = _parse_date(m.get("업로드일자", ""))
            if d is None or d.date() < cutoff:
                continue
            link = str(m.get("영상링크", "")) or str(m.get("영상제목", ""))
            title = str(m.get("영상제목", ""))
            if link not in videos and title:
                # 핵심논지 한 줄 추출 (text의 '핵심 요약:' 첫 bullet)
                txt = str(m.get("text", ""))
                thesis = ""
                mt = re.search(r"핵심 요약:\s*\n?\s*[-•]?\s*(.+)", txt)
                if mt:
                    thesis = mt.group(1).strip()[:80]
                videos[link] = {"date": d, "title": title, "thesis": thesis}
            tk = str(m.get("ticker", "")).strip()
            sent = str(m.get("sentiment", "중립"))
            if tk in _EXCLUDE:
                continue
            key = (link, tk)
            if key in seen_pair:
                continue
            seen_pair.add(key)
            calls.append({"ticker": tk, "date": d, "sent": sent,
                          "name": str(m.get("stock_name", "")) or tk})
    return calls, list(videos.values())


# ──────────────────────────────────────────────
# A. 섹터/테마 관심도
# ──────────────────────────────────────────────
def _map_sectors(tickers: List[str]) -> Dict[str, str]:
    """ticker → 산업(없으면 섹터). 최근 언급 종목만이라 가볍다."""
    from utils.yf_quiet import silence_yfinance
    silence_yfinance()
    import yfinance as yf

    out = {}
    for tk in tickers:
        label = "기타/미분류"
        try:
            if tk.endswith((".KS", ".KQ")):
                label = "한국 주식"
            elif tk.endswith("-USD") or tk in ("BTC-USD", "ETH-USD"):
                label = "암호화폐"
            else:
                info = yf.Ticker(tk).info
                label = info.get("industry") or info.get("sector") or "기타/미분류"
        except Exception:
            pass
        out[tk] = label
    return out


def compute_sector_focus(calls: List[Dict], days: int) -> Dict[str, Any]:
    cutoff_recent = (now_kst() - timedelta(days=days)).date()
    recent = [c for c in calls if c["date"].date() >= cutoff_recent]
    prior = [c for c in calls if c["date"].date() < cutoff_recent]

    sec_map = _map_sectors(sorted({c["ticker"] for c in recent}))
    prior_map = _map_sectors(sorted({c["ticker"] for c in prior
                                     if c["ticker"] not in sec_map}))
    sec_map.update({k: v for k, v in prior_map.items() if k not in sec_map})

    def agg(rows):
        per = defaultdict(lambda: {"buy": 0, "neutral": 0, "caution": 0,
                                   "tickers": Counter()})
        for c in rows:
            sec = sec_map.get(c["ticker"], "기타/미분류")
            p = per[sec]
            if c["sent"] == "매수":
                p["buy"] += 1
            elif c["sent"] == "주의":
                p["caution"] += 1
            else:
                p["neutral"] += 1
            p["tickers"][c["ticker"]] += 1
        return per

    recent_agg = agg(recent)
    prior_agg = agg(prior)

    sectors = []
    for sec, p in recent_agg.items():
        total = p["buy"] + p["neutral"] + p["caution"]
        prior_total = sum(prior_agg[sec][k] for k in ("buy", "neutral", "caution")) \
            if sec in prior_agg else 0
        score = round((p["buy"] - p["caution"]) / total * 100) if total else 0
        sectors.append({
            "sector": sec, "buy": p["buy"], "neutral": p["neutral"],
            "caution": p["caution"], "total": total, "score": score,
            "prior_total": prior_total, "delta": total - prior_total,
            "top_tickers": [t for t, _ in p["tickers"].most_common(5)],
        })
    sectors.sort(key=lambda x: (x["total"], x["score"]), reverse=True)
    return {"window_days": days, "sectors": sectors}


# ──────────────────────────────────────────────
# B. 시황·경계 관점 타임라인
# ──────────────────────────────────────────────
def compute_market_view(videos: List[Dict], limit: int = 20) -> List[Dict]:
    videos = sorted(videos, key=lambda v: v["date"], reverse=True)[:limit]
    out = []
    for v in videos:
        title = v["title"]
        n_caution = len(_CAUTION_KW.findall(title))
        n_opp = len(_OPP_KW.findall(title))
        if n_caution > n_opp:
            stance = "경계"
        elif n_opp > n_caution:
            stance = "기회"
        else:
            stance = "중립"
        out.append({
            "date": v["date"].strftime("%Y-%m-%d"),
            "title": title[:80], "thesis": v.get("thesis", ""),
            "stance": stance,
        })
    return out


# ──────────────────────────────────────────────
# 발행 · 저장 · 조회
# ──────────────────────────────────────────────
def publish_insights(days: int = 30) -> Dict[str, Any]:
    calls, videos = _scan(days)
    if not calls and not videos:
        raise RuntimeError("최근 영상/콜이 없습니다.")
    report = {
        "computed_at": now_kst().strftime("%Y-%m-%d %H:%M"),
        "sector_focus": compute_sector_focus(calls, days),
        "market_view": compute_market_view(videos),
        "recent_call_count": len([c for c in calls
                                  if c["date"].date() >= (now_kst() - timedelta(days=days)).date()]),
    }
    os.makedirs(os.path.dirname(_INSIGHTS_FILE), exist_ok=True)
    with open(_INSIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def get_insights() -> Dict[str, Any]:
    try:
        with open(_INSIGHTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
