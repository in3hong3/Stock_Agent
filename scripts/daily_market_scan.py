"""데일리 시장·보유종목 판정 스캔 — 서버 cron용 (매일 미국장 마감 후).

ml/patterns.py의 규칙 탐지기(순수 pandas — torch 불필요)로 지수 + 보유 종목을
스캔하고, 이벤트 스터디 통계에 근거한 판정문을 생성해 data/market_scan.json 저장.
Streamlit 'AI 신호 → 데일리 판정' 서브탭이 이 파일을 읽어 표시한다.

- 데이터: yfinance (서버에 이미 설치됨 — FDR 불필요)
- LLM 호출 없음 (판정은 규칙 기반 — 비용 0)

cron 예: 30 21 * * 1-5  (UTC 21:30 = 미국장 마감 직후, KST 06:30)
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml"))

os.environ.setdefault("STOCK_AGENT_USER", "admin")

import pandas as pd
import yfinance as yf

import patterns
from modules.daily_paper import now_kst

OUT_PATH = ROOT / "data" / "market_scan.json"
INDICES = [("^IXIC", "나스닥 종합"), ("^GSPC", "S&P500")]

# 이벤트 스터디(S&P500 496종목, 2020~2026) 근거 문구 — ml/study 재실행 시 갱신
STAT_DROP_ABOVE200 = ("과거 통계(1,978건): 200일선 위 급락은 3개월 뒤 평균 +10.7%로 기저율(+4.3%)의 "
                      "2.5배 회복 — 패닉셀 근거 약함. 단 생존편향 과대 가능, '매수 근거'까지는 아님.")
STAT_HS = "과거 통계(1,186건): 헤드앤숄더 이탈 후 폭락은 평균적으로 오지 않았음 (오히려 3개월 +우위)."
STAT_HIGH52 = "과거 통계(7,185건): 신고가 돌파 당일 추격 매수는 평균 이하 — 추격 자제."
STAT_DB = "과거 통계(7,716건): 이중바닥 돌파 후 중기(1~3개월)는 시장평균 이하 — 중기 홀드 근거로 쓰지 말 것."


def fetch(symbol: str) -> pd.DataFrame | None:
    try:
        df = yf.Ticker(symbol).history(period="2y", auto_adjust=True)
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        return df if len(df) >= 260 else None
    except Exception as e:
        print(f"  {symbol}: 조회 실패 {e}")
        return None


def scan_one(symbol: str, name: str) -> dict | None:
    df = fetch(symbol)
    if df is None:
        return None
    c = df["Close"]
    n = len(df)
    ma200 = c.rolling(200).mean().iloc[-1]
    ma50 = c.rolling(50).mean().iloc[-1]
    hi52 = c.rolling(252).max().iloc[-1]

    def recent(dates, k):
        return any(df.index.get_loc(d) >= n - k for d in dates)

    flags = []
    if recent(patterns.sharp_drop(df), 10):
        flags.append("급락중")
    if recent(patterns.head_shoulders(df), 20):
        flags.append("H&S이탈")
    if recent(patterns.double_bottom(df), 10):
        flags.append("쌍바닥돌파")
    if recent(patterns.high_52w_breakout(df), 10):
        flags.append("신고가")

    return {
        "ticker": symbol, "name": name,
        "price": round(float(c.iloc[-1]), 2),
        "ret10": round(float(c.iloc[-1] / c.iloc[-11] - 1) * 100, 1),
        "ret21": round(float(c.iloc[-1] / c.iloc[-22] - 1) * 100, 1),
        "off_high": round(float(c.iloc[-1] / hi52 - 1) * 100, 1),
        "above_ma200": bool(c.iloc[-1] > ma200),
        "above_ma50": bool(c.iloc[-1] > ma50),
        "flags": flags,
    }


def classify(h: dict) -> str:
    if not h["above_ma200"]:
        return "weak"           # 200일선 아래 = 정식 하락추세
    if "급락중" in h["flags"]:
        return "dropping"       # 급락 중이지만 추세 위 = 흔들기 후보
    return "healthy"


def build_verdict(market: list, holdings: list) -> list[str]:
    lines = []
    # 시장
    mkt_warn = [m for m in market if not m["above_ma200"] or "H&S이탈" in m["flags"] or "급락중" in m["flags"]]
    if not mkt_warn:
        lines.append("🟢 시장: 지수에 약세 패턴 없음 — 시장발 하락을 예상할 데이터 근거 없음.")
    else:
        names = ", ".join(m["name"] for m in mkt_warn)
        lines.append(f"🔴 시장: {names}에 경고 신호 — 아래 종목 판정도 보수적으로 볼 것.")

    groups = {"healthy": [], "dropping": [], "weak": []}
    for h in holdings:
        groups[classify(h)].append(h["ticker"])

    if groups["dropping"]:
        lines.append(f"🟡 급락 중이지만 추세(200일선) 위: {', '.join(groups['dropping'])} — {STAT_DROP_ABOVE200}")
    if groups["weak"]:
        lines.append(f"🔴 추세 이탈(200일선 아래): {', '.join(groups['weak'])} — "
                     "홀드 지지 근거가 가장 약한 종목. 포지션 점검 대상.")
    if groups["healthy"]:
        lines.append(f"🟢 건강: {', '.join(groups['healthy'])} — 특이 패턴 없음.")

    # 개별 패턴 주석
    for h in holdings:
        if "H&S이탈" in h["flags"]:
            lines.append(f"ℹ️ {h['ticker']}: 헤드앤숄더 이탈 감지 — {STAT_HS}")
        if "신고가" in h["flags"]:
            lines.append(f"ℹ️ {h['ticker']}: 52주 신고가 돌파 — {STAT_HIGH52}")
        if "쌍바닥돌파" in h["flags"]:
            lines.append(f"ℹ️ {h['ticker']}: 이중바닥 돌파 — {STAT_DB}")
    return lines


def main() -> None:
    print(f"=== 데일리 시장 스캔 {now_kst():%Y-%m-%d %H:%M} KST ===")

    market = [r for sym, nm in INDICES if (r := scan_one(sym, nm))]

    from modules.issue_tracker import get_portfolio_holdings
    holdings = []
    for h in get_portfolio_holdings():
        tk = h["ticker"].upper()
        if tk.endswith((".KS", ".KQ")) or (tk.isdigit() and len(tk) == 6):
            continue  # 미국 종목만 (탐지기 통계가 미국 기준)
        r = scan_one(tk, h.get("name", tk))
        if r:
            holdings.append(r)
        print(f"  {tk}: {'OK' if r else 'SKIP'}")

    payload = {
        "generated_at": now_kst().strftime("%Y-%m-%d %H:%M"),
        "market": market,
        "holdings": holdings,
        "verdict": build_verdict(market, holdings),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"저장 → {OUT_PATH} · 지수 {len(market)} · 종목 {len(holdings)}")


if __name__ == "__main__":
    main()
