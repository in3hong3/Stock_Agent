"""
유튜버 콜 트랙레코드 채점 (Track Record)

RAG에 쌓인 영상의 매수/주의 콜을 '업로드 시점 이후 실제 수익률'로 채점한다.
현재 이 프로젝트는 단일 채널(올랜도 킴 미국주식)만 수집하므로 '채널 간 리더보드'가
아니라 '이 애널리스트의 콜이 실제로 맞았나'를 검증·표시하는 용도.

채점 기준 (콜 유형별로 다르게 — 공정성):
  - 매수(buy): 이후 상승했으면 적중. 시장(SPY) 대비 알파도 함께 계산.
  - 주의(caution): 이후 하락했으면(=회피 성공) 적중. (공매도가 아니라 '피하라'는 뜻)
  ※ 검증 결과(2026-07): 매수 콜은 30~90일에서 시장을 이기는 실제 신호. 주의 콜은
    역지표 성향(주의한 종목이 오히려 상승) → '주의=매도'로 쓰면 안 됨. UI에 명시.

무거운 작업(가격 다운로드)이라 주 1회 cron에서만 계산해 JSON 저장. UI는 읽기만.
저장: data/youtuber_trackrecord.json (시장 전체 공용).
"""
import os
import json
import warnings
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from modules.daily_paper import now_kst

warnings.filterwarnings("ignore")

_NS = "stock-summaries"
_EXCLUDE = {"MARKET", "UNKNOWN", "", "보류", "보유"}
# 비상장/채점 불가 (야후 가격 없음)
_UNTRADEABLE = {"SPACEX", "OPENAI", "STRIPE", "BYTEDANCE", "ANTHROPIC", "DATABRICKS"}
_HORIZONS = [10, 30, 90]

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TR_FILE = os.path.join(_BASE_DIR, "data", "youtuber_trackrecord.json")


def _parse_date(s) -> Optional[datetime]:
    for f in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(s)[:10], f)
        except (ValueError, TypeError):
            continue
    return None


def collect_calls() -> List[Dict[str, Any]]:
    """매수/주의 콜 수집 (영상×종목 유니크). 중립·비종목 제외."""
    from utils.pinecone_store import PineconeStore
    ps = PineconeStore()
    seen = set()
    calls = []
    channel = ""
    for page in ps.index.list(namespace=_NS):
        ids = [it.id for it in page.vectors] if hasattr(page, "vectors") else list(page)
        if not ids:
            continue
        res = ps.index.fetch(ids=ids, namespace=_NS)
        vecs = res.get("vectors", {}) if isinstance(res, dict) else getattr(res, "vectors", {})
        for v in (vecs.values() if hasattr(vecs, "values") else vecs):
            m = (v.get("metadata", {}) if isinstance(v, dict) else getattr(v, "metadata", {})) or {}
            tk = str(m.get("ticker", "")).strip()
            sent = str(m.get("sentiment", "중립"))
            if tk in _EXCLUDE or sent not in ("매수", "주의"):
                continue
            d = _parse_date(m.get("업로드일자", ""))
            if not d:
                continue
            link = str(m.get("영상링크", "")) or str(m.get("영상제목", ""))
            key = (link, tk)
            if key in seen:
                continue
            seen.add(key)
            channel = channel or str(m.get("채널명", ""))
            calls.append({
                "ticker": tk, "date": d, "sent": sent,
                "name": str(m.get("stock_name", "")) or tk,
                "title": str(m.get("영상제목", "")), "link": link,
            })
    return calls, channel


def _download_prices(tickers: List[str], start: datetime, end: datetime) -> Dict[str, Any]:
    """야후 배치 다운로드 → {ticker: close Series}. SPY 포함."""
    import pandas as pd
    from utils.yf_quiet import silence_yfinance
    silence_yfinance()
    import yfinance as yf

    prices = {}
    allt = list(dict.fromkeys(tickers + ["SPY"]))
    for i in range(0, len(allt), 100):
        chunk = allt[i:i + 100]
        try:
            df = yf.download(chunk, start=start.strftime("%Y-%m-%d"),
                             end=end.strftime("%Y-%m-%d"), progress=False,
                             auto_adjust=True, threads=True, group_by="ticker")
        except Exception as e:
            print(f"가격 다운로드 청크 실패({i}): {e}")
            continue
        for t in chunk:
            try:
                s = df[t]["Close"].dropna() if len(chunk) > 1 else df["Close"].dropna()
                if len(s) > 3:
                    s.index = pd.to_datetime(s.index).tz_localize(None)
                    prices[t] = s
            except Exception:
                pass
    return prices


def _fwd(s, d, n):
    import pandas as pd
    a = s.loc[s.index >= pd.Timestamp(d)]
    if a.empty:
        return None
    p0 = a.iloc[0]
    b = s.loc[s.index >= pd.Timestamp(d) + pd.Timedelta(days=n)]
    if b.empty:
        return None
    return float(b.iloc[0] / p0 - 1)


def score(calls: List[Dict], prices: Dict) -> Dict[str, Any]:
    """콜을 기간별로 채점 → 집계 + 종목별 + 대표 적중/실패 콜."""
    spy = prices.get("SPY")
    agg = defaultdict(lambda: {"n": 0, "raw_win": 0, "raw_sum": 0.0,
                               "alpha_win": 0, "alpha_sum": 0.0})
    per_ticker = defaultdict(lambda: {"buy_n": 0, "buy_win": 0, "buy_alpha_sum": 0.0,
                                      "name": ""})
    buy_calls_30 = []  # 대표 콜 (30일 알파 기준)
    scored = 0
    skipped = 0

    for c in calls:
        s = prices.get(c["ticker"])
        if s is None:
            skipped += 1
            continue
        for n in _HORIZONS:
            r = _fwd(s, c["date"], n)
            if r is None:
                continue
            sr = _fwd(spy, c["date"], n) if spy is not None else None
            alpha = (r - sr) if sr is not None else None
            a = agg[(c["sent"], n)]
            a["n"] += 1
            a["raw_sum"] += r
            if c["sent"] == "매수":
                a["raw_win"] += (1 if r > 0 else 0)
                if alpha is not None:
                    a["alpha_win"] += (1 if alpha > 0 else 0)
                    a["alpha_sum"] += alpha
                if n == 30:
                    pt = per_ticker[c["ticker"]]
                    pt["buy_n"] += 1
                    pt["buy_win"] += (1 if r > 0 else 0)
                    pt["name"] = c["name"]
                    if alpha is not None:
                        pt["buy_alpha_sum"] += alpha
                        buy_calls_30.append({
                            "ticker": c["ticker"], "name": c["name"],
                            "date": c["date"].strftime("%Y-%m-%d"),
                            "ret": round(r * 100, 1), "alpha": round(alpha * 100, 1),
                            "title": c["title"][:60], "link": c["link"],
                        })
            else:
                a["raw_win"] += (1 if r < 0 else 0)
                if alpha is not None:
                    a["alpha_win"] += (1 if alpha < 0 else 0)
                    a["alpha_sum"] += alpha
            scored += 1

    def pack(sent, n):
        a = agg[(sent, n)]
        if a["n"] == 0:
            return None
        return {
            "horizon": n, "n": a["n"],
            "hit_rate": round(100 * a["raw_win"] / a["n"], 1),
            "avg_ret": round(100 * a["raw_sum"] / a["n"], 2),
            "avg_alpha": round(100 * a["alpha_sum"] / a["n"], 2),
            "alpha_win": round(100 * a["alpha_win"] / a["n"], 1),
        }

    buy_stats = [pack("매수", n) for n in _HORIZONS]
    caution_stats = [pack("주의", n) for n in _HORIZONS]

    # 종목별 (매수 콜 5회+ 인 것만, 30일 기준)
    ticker_rows = []
    for tk, pt in per_ticker.items():
        if pt["buy_n"] >= 5:
            ticker_rows.append({
                "ticker": tk, "name": pt["name"], "buy_n": pt["buy_n"],
                "hit_rate": round(100 * pt["buy_win"] / pt["buy_n"], 1),
                "avg_alpha": round(100 * pt["buy_alpha_sum"] / pt["buy_n"], 2),
            })
    ticker_rows.sort(key=lambda x: x["avg_alpha"], reverse=True)

    buy_calls_30.sort(key=lambda x: x["alpha"], reverse=True)
    best_calls = buy_calls_30[:8]
    worst_calls = buy_calls_30[-8:][::-1]

    return {
        "buy_stats": [b for b in buy_stats if b],
        "caution_stats": [c for c in caution_stats if c],
        "ticker_rows": ticker_rows,
        "best_calls": best_calls,
        "worst_calls": worst_calls,
        "scored": scored, "skipped": skipped,
    }


def publish_trackrecord() -> Dict[str, Any]:
    """전체 콜 채점 → JSON 저장·반환. (무거움 — cron 전용 권장)"""
    calls, channel = collect_calls()
    if not calls:
        raise RuntimeError("채점할 콜이 없습니다.")
    tickers = sorted({c["ticker"] for c in calls if c["ticker"].upper() not in _UNTRADEABLE})
    dmin = min(c["date"] for c in calls) - timedelta(days=5)
    prices = _download_prices(tickers, dmin, datetime.now())
    result = score(calls, prices)

    report = {
        "channel": channel or "유튜버",
        "computed_at": now_kst().strftime("%Y-%m-%d %H:%M"),
        "window": {
            "start": min(c["date"] for c in calls).strftime("%Y-%m-%d"),
            "end": max(c["date"] for c in calls).strftime("%Y-%m-%d"),
        },
        "total_calls": len(calls),
        "priced_tickers": len(prices),
        **result,
    }
    os.makedirs(os.path.dirname(_TR_FILE), exist_ok=True)
    with open(_TR_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def get_trackrecord() -> Dict[str, Any]:
    """저장된 트랙레코드 로드. 없으면 {}."""
    try:
        with open(_TR_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
