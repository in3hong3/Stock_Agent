"""백테스트 탭 서비스 — ui/pages/backtest.py를 FastAPI용으로.

modules.backtester(단순 전략) + modules.signal_backtest(실제 시그널) 재사용.
Streamlit st.line_chart/st.area_chart는 서버 생성 인라인 SVG로 대체 (JS 라이브러리 없음).
둘 다 버튼(HTMX POST)으로만 실행 — yfinance 다운로드가 무거움.
"""
MAJORS = ["NVDA", "MSFT", "AAPL", "AMZN", "GOOGL", "META", "TSLA", "AMD", "AVGO", "MU",
          "PLTR", "INTC", "QCOM", "ASML", "ORCL", "CRM", "NFLX", "ARM", "DELL", "SNDK"]


def strategies() -> list[dict]:
    from modules.backtester import STRATEGIES
    return [{"key": k, "label": v} for k, v in STRATEGIES.items()]


# ── SVG 차트 (외부 라이브러리 없이) ──
def _downsample(vals: list, cap: int = 160) -> list:
    if len(vals) <= cap:
        return vals
    step = len(vals) / cap
    return [vals[int(i * step)] for i in range(cap)]


def _line_svg(series: list[dict], w: int = 680, h: int = 220) -> str:
    """series: [{name, color, values}]. 여러 선을 겹쳐 그린다."""
    all_vals = [v for s in series for v in s["values"] if v is not None]
    if not all_vals:
        return "<div class='muted-sm'>차트 데이터 없음</div>"
    lo, hi = min(all_vals), max(all_vals)
    rng = (hi - lo) or 1
    pad = 8
    polylines, legend = [], []
    for s in series:
        vals = _downsample(s["values"])
        n = len(vals)
        pts = " ".join(
            f"{pad + i / (n - 1) * (w - 2 * pad):.1f},{h - pad - (v - lo) / rng * (h - 2 * pad):.1f}"
            for i, v in enumerate(vals) if v is not None
        ) if n > 1 else ""
        polylines.append(f'<polyline fill="none" stroke="{s["color"]}" stroke-width="2" points="{pts}"/>')
        legend.append(f'<span style="color:{s["color"]};">■</span> {s["name"]}')
    return (
        f'<svg viewBox="0 0 {w} {h}" class="chart-svg" preserveAspectRatio="none">{"".join(polylines)}</svg>'
        f'<div class="muted-sm">{" &nbsp; ".join(legend)} · 최고 {hi:,.0f} / 최저 {lo:,.0f}</div>'
    )


def _area_svg(vals: list, color: str = "#FF4B4B", w: int = 680, h: int = 160) -> str:
    vals = [v for v in vals if v is not None]
    if not vals:
        return "<div class='muted-sm'>차트 데이터 없음</div>"
    vals = _downsample(vals)
    lo = min(vals + [0.0])
    rng = (0 - lo) or 1  # 낙폭은 0 이하
    pad = 8
    n = len(vals)
    pts = [(pad + i / (n - 1) * (w - 2 * pad), h - pad - (v - lo) / rng * (h - 2 * pad))
           for i, v in enumerate(vals)] if n > 1 else []
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{pad},{h - pad} {line} {w - pad},{h - pad}" if pts else ""
    return (
        f'<svg viewBox="0 0 {w} {h}" class="chart-svg" preserveAspectRatio="none">'
        f'<polygon fill="{color}22" points="{area}"/>'
        f'<polyline fill="none" stroke="{color}" stroke-width="1.5" points="{line}"/></svg>'
        f'<div class="muted-sm">최대 낙폭 {min(vals):.1f}%</div>'
    )


def run_simple(ticker: str, strategy: str, period: str, capital: int,
               rsi_buy: int = 30, rsi_sell: int = 70) -> dict:
    from modules.backtester import run_backtest
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return {"success": False, "error": "티커를 입력하세요."}
    params = {"rsi_buy": rsi_buy, "rsi_sell": rsi_sell} if strategy == "rsi" else {}
    result = run_backtest(ticker=ticker, strategy=strategy, period=period,
                          initial_capital=capital, params=params)
    if not result.get("success"):
        return {"success": False, "error": result.get("error", "실패")}

    eq = result["equity_curve"]
    equity_svg = _line_svg([
        {"name": "전략", "color": "#00FFA3", "values": eq["전략"].tolist()},
        {"name": "Buy & Hold", "color": "#4B7BFF", "values": eq["Buy & Hold"].tolist()},
    ])
    dd_svg = _area_svg(result["drawdown"].tolist())

    trades = result.get("trades", [])
    trade_cols = list(trades[0].keys()) if trades else []
    m = result["metrics"]
    m["delta_vs_bh"] = round(m["total_return"] - m["bh_return"], 2)
    return {"success": True, "metrics": m, "equity_svg": equity_svg, "dd_svg": dd_svg,
            "trades": trades, "trade_cols": trade_cols, "ticker": ticker, "period": period}


def run_signal(horizon: int = 10) -> dict:
    from modules.signal_backtest import run_backtest as run_sig_bt
    from modules.issue_tracker import get_portfolio_holdings
    held = [h["ticker"] for h in get_portfolio_holdings()]
    universe = sorted(set(held) | set(MAJORS))
    res = run_sig_bt(universe, horizon=horizon)
    if not res or not res.get("n"):
        return {"available": False}
    setup_stats = sorted(
        ({"setup": s, **v} for s, v in res["setup_stats"].items()),
        key=lambda x: -(x["win_rate"] or 0),
    )
    return {
        "available": True, "n": res["n"], "horizon": horizon,
        "overall_win": res["overall_win"], "avg_ret": res["avg_ret"],
        "setup_stats": setup_stats,
    }
