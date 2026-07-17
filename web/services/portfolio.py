"""포트폴리오 탭 서비스 (핵심 관리) — ui/pages/portfolio.py를 FastAPI용으로.

핵심: 조회·추가·편집·삭제·저장(+매도감지→매매일지)·가격업데이트·현금/시드·총자산.
data_editor(인라인 표) → 행별 input 폼(웹 표준, 더 나은 UX)으로 대체.
보류(스코프): 5개 분석 서브탭(시각화 plotly·리밸런싱/챗봇/분석 LLM)·현금기준 실행지시.
"""
import os

import pandas as pd

from web.services.meta import load_meta, save_meta

_CORE = ["ticker", "name", "quantity", "avg_price", "current_price"]


def _pf_path() -> str:
    from utils.user_data import portfolio_path
    return portfolio_path()


def _load_df() -> pd.DataFrame:
    df = pd.read_csv(_pf_path())
    for c in ("quantity", "avg_price", "current_price"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return df


def _save_df(df: pd.DataFrame) -> None:
    os.makedirs(os.path.dirname(_pf_path()), exist_ok=True)
    df[_CORE].to_csv(_pf_path(), index=False)


def _cash() -> dict:
    m = load_meta()
    return {"krw": float(m.get("cash_krw", 0) or 0), "usd": float(m.get("cash_usd", 0) or 0)}


def _fx() -> float:
    try:
        from modules.issue_tracker import get_usdkrw_rate
        return get_usdkrw_rate() or 1400.0
    except Exception:
        return 1400.0


def _totals(df: pd.DataFrame, cash: dict, fx: float) -> dict:
    stock_eval = stock_cost = 0.0
    for _, r in df.iterrows():
        try:
            qty, cur, avg = float(r["quantity"]), float(r["current_price"]), float(r["avg_price"])
        except (TypeError, ValueError):
            continue
        factor = 1.0 if str(r["ticker"]).endswith((".KS", ".KQ")) else fx
        stock_eval += qty * cur * factor
        stock_cost += qty * avg * factor
    pnl = stock_eval - stock_cost
    cash_total = cash["krw"] + cash["usd"] * fx
    total = stock_eval + cash_total
    return {
        "stock_eval": stock_eval, "pnl": pnl,
        "pnl_rate": (pnl / stock_cost * 100) if stock_cost > 0 else 0,
        "cash_total": cash_total, "total": total, "total_cost": stock_cost,
        "cash_ratio": (cash_total / total * 100) if total > 0 else 0,
        "usd_total": total / fx if fx else 0,
    }


def get_context() -> dict:
    m = load_meta()
    ctx = {
        "has_file": os.path.exists(_pf_path()),
        "cash": _cash(), "seed": float(m.get("trading_seed", 0) or 0),
        "risk": float(m.get("risk_pct", 1.0) or 1.0),
        "price_ts": m.get("price_updated_at", "기록 없음"),
        "pending_sells": m.get("_pending_sells") or [],
    }
    if not ctx["has_file"]:
        return ctx

    df = _load_df()
    fx = _fx()
    rows = []
    missing = 0
    for _, r in df.iterrows():
        tk = str(r["ticker"]).strip()
        if not tk or tk.lower() in ("nan", "none"):
            continue
        cur = float(r["current_price"])
        if cur <= 0:
            missing += 1
        rows.append({"ticker": tk, "name": str(r.get("name") or tk),
                     "quantity": float(r["quantity"]), "avg_price": float(r["avg_price"]),
                     "current_price": cur, "eval": float(r["quantity"]) * cur})
    ctx.update({"rows": rows, "fx": fx, "missing": missing,
                "totals": _totals(df, ctx["cash"], fx)})
    return ctx


# ── 쓰기 동작 ──
def create_sample() -> str:
    os.makedirs(os.path.dirname(_pf_path()), exist_ok=True)
    with open(_pf_path(), "w", encoding="utf-8") as f:
        f.write("ticker,name,quantity,avg_price,current_price\n")
        f.write("TSLA,테슬라,10,200,250\nNVDA,엔비디아,2,400,600\n")
    return "✅ 샘플 포트폴리오를 생성했습니다."


def add_holding(name_input: str, qty_raw: str, avg_raw: str) -> str:
    from modules.issue_tracker import resolve_ticker
    import yfinance as yf
    if not (name_input or "").strip():
        return "⚠️ 종목을 입력하세요."
    try:
        qty = float((qty_raw or "").replace(",", "")) if qty_raw else 1.0
        avg = float((avg_raw or "").replace(",", "")) if avg_raw else 0.0
    except ValueError:
        return "⚠️ 수량/평단가는 숫자여야 합니다."

    df = _load_df() if os.path.exists(_pf_path()) else pd.DataFrame(columns=_CORE)
    try:
        ticker = resolve_ticker(name_input.strip())
        if ticker in df["ticker"].astype(str).values:
            return f"⚠️ {ticker}는 이미 포트폴리오에 있습니다."
        hist = yf.Ticker(ticker).history(period="5d")
        if hist.empty:
            return f"⚠️ '{ticker}' 데이터를 찾을 수 없습니다."
        current = float(hist["Close"].iloc[-1])
        name = yf.Ticker(ticker).info.get("shortName") or name_input.strip()
        df = pd.concat([df, pd.DataFrame([{
            "ticker": ticker, "name": name, "quantity": qty if qty > 0 else 1.0,
            "avg_price": avg if avg > 0 else current, "current_price": current}])],
            ignore_index=True)
        _save_df(df)
        save_meta(price_updated_at=_now())
        return f"✅ {name} ({ticker}) 추가"
    except Exception as e:
        return f"⚠️ 추가 실패: {e}"


def save_edits(tickers, names, quantities, avgs) -> str:
    """행별 편집 저장 + 매도(수량 감소) 감지 → 매매일지 유도(meta에 _pending_sells)."""
    if not os.path.exists(_pf_path()):
        return "⚠️ 포트폴리오가 없습니다."
    old = _load_df()
    old_by_tk = {str(r["ticker"]).strip(): r for _, r in old.iterrows()}

    new_rows, sells = [], []
    for tk, nm, q, a in zip(tickers, names, quantities, avgs):
        tk = (tk or "").strip()
        if not tk or tk.lower() in ("nan", "none"):
            continue
        try:
            q = float(q or 0); a = float(a or 0)
        except ValueError:
            q, a = 0.0, 0.0
        orow = old_by_tk.get(tk)
        cur = float(orow["current_price"]) if orow is not None else 0.0
        new_rows.append({"ticker": tk, "name": (nm or tk).strip(),
                         "quantity": q, "avg_price": a, "current_price": cur})
        if orow is not None and q < float(orow["quantity"]):
            sells.append({"ticker": tk, "name": str(orow.get("name") or tk),
                          "qty": float(orow["quantity"]) - q, "avg_price": float(orow["avg_price"]),
                          "current_price": cur})

    _save_df(pd.DataFrame(new_rows, columns=_CORE))
    if sells:
        save_meta(_pending_sells=sells)
        return "💾 저장 완료 — 매도가 감지됐어요. 아래에서 체결가를 넣고 매매일지에 기록하세요."
    return "💾 저장 완료 — '📌 내 종목' 탭에 반영됩니다."


def delete_holdings(del_tickers: list[str]) -> str:
    if not os.path.exists(_pf_path()) or not del_tickers:
        return "⚠️ 삭제할 종목을 선택하세요."
    df = _load_df()
    sells = []
    for _, r in df[df["ticker"].astype(str).isin(del_tickers)].iterrows():
        if float(r["quantity"]) > 0:
            sells.append({"ticker": str(r["ticker"]), "name": str(r.get("name") or r["ticker"]),
                          "qty": float(r["quantity"]), "avg_price": float(r["avg_price"]),
                          "current_price": float(r["current_price"])})
    kept = df[~df["ticker"].astype(str).isin(del_tickers)]
    _save_df(kept)
    if sells:
        save_meta(_pending_sells=sells)
    return f"🗑️ {len(del_tickers)}개 종목 삭제 완료"


def update_prices() -> str:
    if not os.path.exists(_pf_path()):
        return "⚠️ 포트폴리오가 없습니다."
    from utils.price_updater import PriceUpdater
    updater = PriceUpdater()
    df = updater.update_portfolio_prices(_load_df(), delay_seconds=0.3)
    updater.save_portfolio(df, _pf_path())
    save_meta(price_updated_at=_now())
    return "📡 가격 업데이트 완료"


def save_cash(krw_raw: str, usd_raw: str) -> str:
    try:
        krw = float((krw_raw or "0").replace(",", "") or 0)
        usd = float((usd_raw or "0").replace(",", "") or 0)
    except ValueError:
        return "⚠️ 숫자만 입력하세요."
    save_meta(cash_krw=krw, cash_usd=usd)
    return "💾 현금 저장됨"


def save_seed(seed_raw: str, risk_raw: str) -> str:
    try:
        seed = float((seed_raw or "0").replace(",", "") or 0)
        risk = float(risk_raw or 1.0)
    except ValueError:
        return "⚠️ 숫자만 입력하세요."
    save_meta(trading_seed=seed, risk_pct=risk)
    return f"💾 시드 ${seed:,.0f} · 리스크 {risk}% 저장"


def record_sells(prices: dict) -> str:
    """대기 중 매도를 매매일지에 기록 (체결가 dict: ticker→price)."""
    from modules.trade_journal import add_trade
    from modules.daily_paper import now_kst
    pending = load_meta().get("_pending_sells") or []
    n = 0
    for s in pending:
        p = prices.get(s["ticker"], 0)
        if p and p > 0:
            add_trade(now_kst().strftime("%Y-%m-%d"), s["ticker"], s["name"], "sell",
                      s["qty"], p, memo="포트폴리오 편집에서 매도 감지", avg_price=s["avg_price"])
            n += 1
    save_meta(_pending_sells=[])
    return f"📒 {n}건 매매일지 기록 완료 (실현손익 반영)"


def skip_sells() -> str:
    save_meta(_pending_sells=[])
    return "매도 기록을 건너뛰었습니다."


def _now() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
