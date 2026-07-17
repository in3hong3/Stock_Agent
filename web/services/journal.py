"""매매일지 탭 서비스 — ui/pages/journal.py를 FastAPI용으로 (CRUD).

modules.trade_journal 재사용. 사용자별 trade_journal.csv에 기록/삭제.
쓰기 동작은 라우트에서 PRG(POST→redirect→GET)로 처리, 여기선 순수 로직만.
"""


def _series_to_bars(series) -> list[dict]:
    """pandas Series(라벨→값) → 막대 표시용 [{label, value, pct, cls}] (|값| 비율)."""
    try:
        items = [(str(k), float(v)) for k, v in series.items()]
    except Exception:
        return []
    if not items:
        return []
    mx = max((abs(v) for _, v in items), default=0) or 1
    return [{"label": k, "value": v, "pct": abs(v) / mx * 100,
             "cls": "c-up" if v >= 0 else "c-down"} for k, v in items]


def get_context(flash: str = "") -> dict:
    from modules.trade_journal import load_journal, get_stats
    stats = get_stats()
    df = load_journal()

    rows = []
    side_map = {"buy": "🟢 매수", "sell": "🔴 매도"}
    for orig_idx, (_, r) in enumerate(df.iterrows()):
        rows.append({
            "idx": orig_idx,  # 입력 순서 인덱스 (삭제 기준)
            "date": r["date"], "ticker": r["ticker"], "name": r.get("name", ""),
            "side": side_map.get(r["side"], r["side"]),
            "quantity": r["quantity"], "price": r["price"],
            "avg_at_sale": r.get("avg_price_at_sale"),
            "realized": r.get("realized_pnl"), "memo": r.get("memo", ""),
        })
    rows.reverse()  # 최신 먼저

    ctx = {"flash": flash, "n_trades": stats.get("n_trades", 0), "stats": stats,
           "rows": rows, "delete_options": [
               {"idx": rr["idx"], "label": f"#{rr['idx']} · {rr['date']} {rr['ticker']} "
                f"{rr['side']} {rr['quantity']:g}주 @ {rr['price']}"} for rr in rows]}
    if stats.get("n_trades", 0) > 0:
        ctx["monthly"] = _series_to_bars(stats.get("monthly"))
        ctx["by_ticker"] = _series_to_bars(stats.get("by_ticker"))
    return ctx


def add_entry(date_str: str, ticker_input: str, side_kr: str, qty_raw: str,
              price_raw: str, memo: str, apply_pf: bool) -> str:
    """거래 추가. 성공/실패 메시지(flash) 반환. 입력 오류 시 ValueError."""
    from modules.trade_journal import add_trade, apply_to_portfolio
    from modules.issue_tracker import resolve_ticker

    try:
        qty = float((qty_raw or "").replace(",", ""))
        price = float((price_raw or "").replace(",", ""))
    except ValueError:
        raise ValueError("종목/수량/체결가를 올바르게 입력하세요.")
    if not (ticker_input or "").strip() or qty <= 0 or price <= 0:
        raise ValueError("종목/수량/체결가를 올바르게 입력하세요.")

    ticker = resolve_ticker(ticker_input.strip())
    side = "buy" if side_kr == "매수" else "sell"
    avg_price = None

    if apply_pf:
        result = apply_to_portfolio(ticker, side, qty, price)
        if not result["success"]:
            raise ValueError(result["message"])
        avg_price = result.get("avg_price")

    row = add_trade(date_str, ticker, ticker_input.strip(), side, qty, price,
                    memo=(memo or "").strip(), avg_price=avg_price)
    pnl = row.get("realized_pnl")
    if pnl is not None:
        emoji = "🎉" if pnl >= 0 else "📉"
        return f"{emoji} 기록 완료 · 실현손익 {pnl:+,.2f}"
    return "✍️ 기록 완료"


def delete_entry(index: int) -> str:
    from modules.trade_journal import delete_trade
    delete_trade(index)
    return "🗑️ 기록을 삭제했습니다"
