"""시장 지수 시세 + 공포/탐욕 지수 — Streamlit 의존 없는 순수 버전.

ui/theme.get_realtime_market_summary의 로직을 그대로 옮기되, @st.cache_data 대신
간단한 프로세스 TTL 캐시를 쓴다. 티커테이프·F&G 바·테마 색이 이 한 소스를 공유.
"""
import math
import time

# 상단 티커테이프 순서·라벨 (ui/components.render_ticker_tape와 동일)
_INDICES = ["공포/탐욕", "다우존스", "S&P 500", "나스닥 100", "코스피", "원달러환율", "비트코인"]
_LABELS = ["F&G", "DOW", "S&P 500", "NASDAQ 100", "KOSPI", "USD/KRW", "BTC"]
_YF_MAP = {
    "^DJI": "다우존스", "^GSPC": "S&P 500", "^NDX": "나스닥 100",
    "^KS11": "코스피", "KRW=X": "원달러환율", "BTC-USD": "비트코인",
}

_cache: dict = {"ts": 0.0, "rows": None}
_TTL = 60  # 초


def _fetch_rows() -> list[dict]:
    """yfinance + CNN에서 원시 시세 행 리스트를 만든다. 실패 항목은 N/A."""
    import yfinance as yf
    import requests

    rows: list[dict] = []

    # CNN 공포/탐욕
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://edition.cnn.com",
            "Referer": "https://edition.cnn.com/markets/fear-and-greed",
        }
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            score = data["fear_and_greed"]["score"]
            rating = data["fear_and_greed"]["rating"].title()
            rows.append({"종목": "공포/탐욕", "현재가": float(score), "등락": rating, "등락값": 0.0})
    except Exception:
        pass

    for ticker_id, name in _YF_MAP.items():
        try:
            fi = yf.Ticker(ticker_id).fast_info
            last = fi.get("lastPrice")
            prev = fi.get("previousClose")
            val = float(last) if last is not None else 0.0
            change_str, change_value = "0.00%", 0.0
            if (last is not None and prev is not None
                    and not math.isnan(float(last)) and not math.isnan(float(prev))
                    and float(prev) != 0):
                diff = float(last) - float(prev)
                change_str = f"{diff / float(prev) * 100:+.2f}%"
                change_value = diff
            if math.isnan(val):
                val = 0.0
            rows.append({"종목": name, "현재가": val, "등락": change_str, "등락값": change_value})
        except Exception as e:
            print(f"[market] {ticker_id} 조회 실패: {e}")
            rows.append({"종목": name, "현재가": 0.0, "등락": "0.00%", "등락값": 0.0})

    return rows


def _rows() -> list[dict]:
    now = time.time()
    if _cache["rows"] is None or now - _cache["ts"] > _TTL:
        _cache["rows"] = _fetch_rows()
        _cache["ts"] = now
    return _cache["rows"]


def _fmt_price(name: str, val) -> str:
    if val is None:
        return "N/A"
    if name == "공포/탐욕":
        return f"{val:.0f}"
    if name == "원달러환율":
        return f"₩{val:,.1f}"
    if name == "비트코인":
        return f"${val:,.0f}"
    return f"{val:,.2f}" if val < 1000 else f"{val:,.0f}"


def _fmt_diff(name: str, diff) -> str:
    if name == "공포/탐욕" or diff is None:
        return ""
    if name in ("코스피", "원달러환율", "비트코인"):
        return f"{diff:+,.0f}" if name == "비트코인" else f"{diff:+,.2f}"
    return f"{diff:+,.2f}"


def get_ticker_tape() -> list[dict]:
    """티커테이프 카드용 구조 — 템플릿이 그대로 순회.

    각 카드: {label, price, sub, color} (color: up/down/flat/muted)
    """
    rows = {r["종목"]: r for r in _rows()}
    cards = []
    for name, label in zip(_INDICES, _LABELS):
        r = rows.get(name)
        if not r:
            cards.append({"label": label, "price": "N/A", "sub": "—", "color": "muted"})
            continue
        val = float(r.get("현재가") or 0)
        change_str = str(r.get("등락", "0.00%"))
        diff = float(r.get("등락값", 0) or 0)
        if name == "공포/탐욕":
            cards.append({"label": label, "price": _fmt_price(name, val),
                          "sub": change_str, "color": "muted"})
            continue
        if diff > 0:
            color, arrow = "up", "▲"
        elif diff < 0:
            color, arrow = "down", "▼"
        else:
            color, arrow = "flat", "—"
        diff_str = _fmt_diff(name, diff)
        sub = f"{arrow} {diff_str} ({change_str})" if diff_str else f"{arrow} {change_str}"
        cards.append({"label": label, "price": _fmt_price(name, val), "sub": sub, "color": color})
    return cards


def get_fear_greed() -> dict:
    """F&G 바/테마용 — {value:float|None, status:str, point_color:str, text_color:str}."""
    rows = {r["종목"]: r for r in _rows()}
    fg = rows.get("공포/탐욕")
    val = float(fg["현재가"]) if fg else None
    return {
        "value": val,
        "status": _fg_status(val),
        "point_color": _point_color(val),
        "bar_color": _bar_color(val),
    }


def _fg_status(v) -> str:
    if v is None:
        return "데이터 없음"
    if v <= 25:
        return "극공포 (매수 기회)"
    if v <= 45:
        return "공포 (매수 고려)"
    if v <= 55:
        return "중립 (관망)"
    if v <= 75:
        return "탐욕 (주의)"
    return "극탐욕 (과열 경고)"


def _point_color(v) -> str:
    """악센트 색 (ui/theme.get_point_color와 동일 경계)."""
    if v is None:
        return "#6E7175"
    if v < 30:
        return "#FF4B4B"
    if v <= 70:
        return "#FFA500"
    return "#00FFA3"


def _bar_color(v) -> str:
    if v is None:
        return "#94A3B8"
    if v <= 25:
        return "#FF4B4B"
    if v <= 45:
        return "#FFA500"
    if v <= 55:
        return "#FFD700"
    if v <= 75:
        return "#90EE90"
    return "#00FFA3"
