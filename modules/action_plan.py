"""현금 기준 실행 지시 — 보유/시그널/현금으로 '팔 것·살 것 N주'를 산출 (규칙 기반, LLM 없음).
⚠️ 투자 권유가 아니라 참고용. 주문 체결은 사용자가 직접 한다."""
from typing import List, Dict, Any

_BUY = ("적극 매수", "분할 매수")
_BUY_WEIGHT = {"적극 매수": 2.0, "분할 매수": 1.0}


def build_action_plan(signals: List[Dict[str, Any]], cash_usd: float,
                      deploy_pct: float = 100.0, trim_pct: float = 50.0) -> Dict[str, Any]:
    """
    signals: trade_signal.generate_signals()의 signals (ticker, action, price, quantity, entry, target ...)
    cash_usd: 투입 가능 달러 현금
    deploy_pct: 현금 중 이번에 투입할 비율(%)
    trim_pct: 매도 신호 종목을 보유분의 몇 % 줄일지
    Returns: {sells, buys, available, spent, leftover, proceeds}
    """
    # 1) 매도 지시 — 보유 + 매도성 신호(축소/익절)면 보유분의 trim_pct% 매도
    sells: List[Dict[str, Any]] = []
    proceeds = 0.0
    for s in signals:
        qty = float(s.get("quantity") or 0)
        price = float(s.get("price") or 0)
        act = s.get("action", "")
        if qty <= 0 or price <= 0:
            continue
        if ("축소" in act) or ("익절" in act):
            sell_qty = max(1, int(round(qty * trim_pct / 100.0)))
            amt = sell_qty * price
            sells.append({"ticker": s["ticker"], "qty": sell_qty, "price": price,
                          "amount": amt, "action": act})
            proceeds += amt

    # 2) 매수 지시 — (현금×투입비율 + 매도대금)을 신호 강도로 가중 분배
    available = max(0.0, cash_usd * deploy_pct / 100.0) + proceeds
    cands = [s for s in signals if s.get("action") in _BUY and float(s.get("price") or 0) > 0]
    tot_w = sum(_BUY_WEIGHT[s["action"]] for s in cands)
    buys: List[Dict[str, Any]] = []
    spent = 0.0
    order = sorted(cands, key=lambda x: -_BUY_WEIGHT[x["action"]])  # 강한 신호 우선
    by_ticker: Dict[str, Dict[str, Any]] = {}
    if available > 0 and tot_w > 0:
        # 1차: 신호 강도 가중 분배
        for s in order:
            alloc = available * (_BUY_WEIGHT[s["action"]] / tot_w)
            price = float(s["price"])
            qty = int(alloc // price)
            if qty <= 0:
                continue
            b = {"ticker": s["ticker"], "qty": qty, "price": price, "amount": qty * price,
                 "action": s["action"], "entry": s.get("entry"),
                 "target": s.get("target"), "setup": s.get("setup", "")}
            buys.append(b)
            by_ticker[s["ticker"]] = b
            spent += qty * price

        # 2차: 잔여 현금을 강한 신호부터 1주씩 추가해 거의 다 투입 (정수 주식 한계 보완)
        remaining = available - spent
        changed = True
        while changed:
            changed = False
            for s in order:
                price = float(s["price"])
                if price <= remaining + 1e-9:
                    b = by_ticker.get(s["ticker"])
                    if b is None:
                        b = {"ticker": s["ticker"], "qty": 0, "price": price, "amount": 0.0,
                             "action": s["action"], "entry": s.get("entry"),
                             "target": s.get("target"), "setup": s.get("setup", "")}
                        by_ticker[s["ticker"]] = b
                        buys.append(b)
                    b["qty"] += 1
                    b["amount"] = b["qty"] * price
                    remaining -= price
                    changed = True
        spent = sum(b["amount"] for b in buys)

    return {"sells": sells, "buys": buys, "available": round(available, 2),
            "spent": round(spent, 2), "leftover": round(available - spent, 2),
            "proceeds": round(proceeds, 2)}
