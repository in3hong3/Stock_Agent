"""
collect_market_data.py — 시장 데이터 사전 수집 하네스 (로드맵 #2)

새벽 cron이 1회 실행. 모든 사용자의 보유/관심/추적 종목 + 시장지표를
yfinance로 한 번에 긁어 data/cache/ 에 저장한다.

이후 페이지/시그널은 market_cache.get_history/get_info 로 캐시를 즉시 읽어
yfinance 라이브 호출(느림·차단 위험)을 피한다.

cron (KST 06:30 = UTC 21:30, 평일 — 미 증시 마감 후):
  30 21 * * 1-5 cd ~/stock-agent && .venv/bin/python scripts/collect_market_data.py >> logs/collect_market.log 2>&1
"""
import os
import sys
import csv
import glob
import json
import time
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yfinance as yf
from core.services import market_cache

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_USERS_DIR = os.path.join(_BASE, "data", "users")

# 시장 국면 판단에 항상 필요한 지표/환율
MARKET_TICKERS = ["^VIX", "^GSPC", "KRW=X"]


def _read_portfolio_tickers(path: str) -> set:
    out = set()
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                t = (row.get("ticker") or "").strip().upper()
                if t and t != "USD":
                    out.add(t)
    except Exception as e:
        print(f"  ⚠️ {path} 읽기 실패: {e}")
    return out


def _read_json_tickers(path: str) -> set:
    out = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            items = json.load(f)
        for it in items if isinstance(items, list) else []:
            t = (it.get("ticker") or "").strip().upper()
            if t and t != "USD":
                out.add(t)
    except Exception as e:
        print(f"  ⚠️ {path} 읽기 실패: {e}")
    return out


def gather_universe() -> list:
    """모든 사용자의 보유/관심/추적 종목 + 시장지표를 모은 티커 집합."""
    tickers = set(MARKET_TICKERS)

    for udir in glob.glob(os.path.join(_USERS_DIR, "*")):
        if not os.path.isdir(udir):
            continue
        pf = os.path.join(udir, "portfolio.csv")
        if os.path.exists(pf):
            tickers |= _read_portfolio_tickers(pf)
        for name in ("watchlist.json", "tracked_tickers.json"):
            jf = os.path.join(udir, name)
            if os.path.exists(jf):
                tickers |= _read_json_tickers(jf)

    return sorted(tickers)


def collect(delay: float = 0.4):
    start = datetime.datetime.now()
    print("=" * 56)
    print(f"  📦 시장 데이터 수집 시작 — {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 56)

    universe = gather_universe()
    print(f"  대상 종목: {len(universe)}개")
    print(f"  {', '.join(universe)}\n")

    ok_hist = ok_info = ok_news = ok_insider = fail = 0
    for i, ticker in enumerate(universe, 1):
        try:
            tk = yf.Ticker(ticker)
            df = tk.history(period=market_cache.COLLECT_PERIOD)
            if df is not None and not df.empty and market_cache.save_history(ticker, df):
                ok_hist += 1
                tag = "📈"
            else:
                tag = "∅ "

            # 지수/환율은 .info/뉴스가 비거나 무의미 → 히스토리만 캐시
            info_tag = news_tag = insider_tag = ""
            if not (ticker.startswith("^") or ticker.endswith("=X")):
                info = tk.info
                if info and market_cache.save_info(ticker, info):
                    ok_info += 1
                    info_tag = "💼"
                    market_cache.record_ownership(ticker, info)  # 기관/내부자 보유율 스냅샷 누적

                # 뉴스: 누적 더미에 새 기사만 합침 (덮어쓰지 않음)
                news = market_cache._fetch_news_live(ticker)
                if news:
                    merged = market_cache.save_news(ticker, news)
                    ok_news += 1
                    news_tag = f"📰{len(merged)}"

                # 내부자 거래(SEC Form 4): EDGAR 라이브 수집 → 캐시 (느려서 cron에서만)
                try:
                    from modules.insider_tracker import get_insider_activity
                    act = get_insider_activity(ticker, allow_live=True)
                    if act.get("available"):
                        ok_insider += 1
                        net = act.get("net_value", 0)
                        insider_tag = f"👤{'+' if net > 0 else ''}{net/1e6:.0f}M"
                except Exception as ie:
                    print(f"      내부자 수집 오류 {ticker}: {ie}")

            print(f"  [{i:>2}/{len(universe)}] {tag}{info_tag}{news_tag}{insider_tag} {ticker}")
        except Exception as e:
            fail += 1
            print(f"  [{i:>2}/{len(universe)}] ❌ {ticker}: {e}")

        if i < len(universe):
            time.sleep(delay)

    elapsed = (datetime.datetime.now() - start).seconds
    print("\n" + "=" * 56)
    print(f"  ✅ 완료 — history {ok_hist} · info {ok_info} · news {ok_news} · "
          f"insider {ok_insider} · 실패 {fail} ({elapsed // 60}분 {elapsed % 60}초)")
    print(f"  캐시 현황: {market_cache.cache_status()}")
    print("=" * 56)
    return {"history": ok_hist, "info": ok_info, "news": ok_news,
            "insider": ok_insider, "fail": fail, "total": len(universe)}


if __name__ == "__main__":
    collect()
