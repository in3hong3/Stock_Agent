"""
이벤트 캘린더
보유 종목 실적발표(yfinance) + 주요 경제지표 발표일 + 휴장일 + 사용자 정의 이벤트.
"""
import os
import json
import calendar
from datetime import date, datetime, timedelta
from typing import Dict, List, Any

import yfinance as yf

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_FILE = os.path.join(_BASE_DIR, "data", "events.json")

# ──────────────────────────────────────────────
# 내장 일정 (2026년) — 날짜는 발표 기관 일정 기준, 변경될 수 있음
# ──────────────────────────────────────────────
FOMC_2026 = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]

CPI_2026 = [
    "2026-01-13", "2026-02-11", "2026-03-11", "2026-04-10",
    "2026-05-12", "2026-06-10", "2026-07-14", "2026-08-12",
    "2026-09-11", "2026-10-13", "2026-11-10", "2026-12-10",
]

US_HOLIDAYS_2026 = {
    "2026-01-01": "🇺🇸 신정 휴장",
    "2026-01-19": "🇺🇸 마틴루터킹 데이 휴장",
    "2026-02-16": "🇺🇸 대통령의 날 휴장",
    "2026-04-03": "🇺🇸 성금요일 휴장",
    "2026-05-25": "🇺🇸 메모리얼 데이 휴장",
    "2026-06-19": "🇺🇸 준틴스 휴장",
    "2026-07-03": "🇺🇸 독립기념일 휴장",
    "2026-09-07": "🇺🇸 노동절 휴장",
    "2026-11-26": "🇺🇸 추수감사절 휴장",
    "2026-12-25": "🇺🇸 크리스마스 휴장",
}

KR_HOLIDAYS_2026 = {
    "2026-01-01": "🇰🇷 신정 휴장",
    "2026-02-16": "🇰🇷 설날 연휴 휴장",
    "2026-02-17": "🇰🇷 설날 휴장",
    "2026-02-18": "🇰🇷 설날 연휴 휴장",
    "2026-03-02": "🇰🇷 삼일절 대체휴일 휴장",
    "2026-05-05": "🇰🇷 어린이날 휴장",
    "2026-05-25": "🇰🇷 부처님오신날 대체휴일 휴장",
    "2026-08-17": "🇰🇷 광복절 대체휴일 휴장",
    "2026-09-24": "🇰🇷 추석 연휴 휴장",
    "2026-09-25": "🇰🇷 추석 휴장",
    "2026-10-05": "🇰🇷 개천절 대체휴일 휴장",
    "2026-10-09": "🇰🇷 한글날 휴장",
    "2026-12-25": "🇰🇷 크리스마스 휴장",
}


# ──────────────────────────────────────────────
# 사용자 정의 이벤트
# ──────────────────────────────────────────────
def load_custom_events() -> List[Dict[str, str]]:
    if not os.path.exists(EVENTS_FILE):
        return []
    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_custom_events(events: List[Dict[str, str]]):
    os.makedirs(os.path.dirname(EVENTS_FILE), exist_ok=True)
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


def add_custom_event(event_date: str, title: str):
    events = load_custom_events()
    events.append({"date": event_date, "title": title})
    save_custom_events(events)


def remove_custom_event(index: int):
    events = load_custom_events()
    if 0 <= index < len(events):
        events.pop(index)
        save_custom_events(events)


# ──────────────────────────────────────────────
# 실적 발표일 (yfinance)
# ──────────────────────────────────────────────
def get_earnings_events(tickers: List[str]) -> List[Dict[str, str]]:
    """보유 종목들의 다음 실적발표일 조회"""
    events = []
    today = date.today()
    for ticker in tickers:
        try:
            cal = yf.Ticker(ticker).calendar
            earnings_dates = cal.get("Earnings Date", []) if isinstance(cal, dict) else []
            for ed in earnings_dates:
                if isinstance(ed, (date, datetime)):
                    ed_date = ed if isinstance(ed, date) and not isinstance(ed, datetime) else ed.date()
                    if today <= ed_date <= today + timedelta(days=120):
                        events.append({
                            "date": ed_date.strftime("%Y-%m-%d"),
                            "title": f"💼 {ticker} 실적발표",
                            "type": "earnings",
                        })
                        break  # 가장 가까운 1개만
        except Exception as e:
            print(f"실적일 조회 실패 ({ticker}): {e}")
    return events


# ──────────────────────────────────────────────
# 전체 이벤트 병합
# ──────────────────────────────────────────────
def get_all_events(tickers: List[str] = None) -> Dict[str, List[str]]:
    """
    날짜별 이벤트 dict 반환: {"2026-06-17": ["🏛️ FOMC 금리 결정", ...]}
    """
    events: Dict[str, List[str]] = {}

    def push(d: str, title: str):
        events.setdefault(d, []).append(title)

    for d in FOMC_2026:
        push(d, "🏛️ FOMC 금리 결정")
    for d in CPI_2026:
        push(d, "📊 미국 CPI 발표")
    for d, title in US_HOLIDAYS_2026.items():
        push(d, title)
    for d, title in KR_HOLIDAYS_2026.items():
        push(d, title)
    for ev in load_custom_events():
        push(ev["date"], f"📝 {ev['title']}")
    if tickers:
        for ev in get_earnings_events(tickers):
            push(ev["date"], ev["title"])

    return events


def build_calendar_html(year: int, month: int, events: Dict[str, List[str]], accent: str = "#00FFA3") -> str:
    """이벤트 점이 표시된 미니 달력 HTML 생성"""
    cal = calendar.Calendar(firstweekday=6)  # 일요일 시작
    today = date.today()

    weeks_html = ""
    for week in cal.monthdayscalendar(year, month):
        cells = ""
        for i, day in enumerate(week):
            if day == 0:
                cells += "<td></td>"
                continue
            d_str = f"{year}-{month:02d}-{day:02d}"
            day_events = events.get(d_str, [])
            is_today = (date(year, month, day) == today)
            weekend_color = "#FF6B6B" if i == 0 else ("#6B9BFF" if i == 6 else "#E2E8F0")

            dot = f"<div style='width:5px;height:5px;border-radius:50%;background:{accent};margin:2px auto 0;'></div>" if day_events else "<div style='height:7px;'></div>"
            today_style = f"background:{accent}22;border:1px solid {accent};border-radius:8px;" if is_today else ""
            tooltip = " · ".join(day_events).replace('"', "'")

            cells += f"""<td title="{tooltip}" style="text-align:center;padding:3px 0;{today_style}">
                <span style="font-size:12px;color:{weekend_color};">{day}</span>{dot}</td>"""
        weeks_html += f"<tr>{cells}</tr>"

    return f"""
    <div style="background:#1A1C24;border:1px solid rgba(255,255,255,0.07);border-radius:14px;padding:14px;">
        <div style="text-align:center;font-weight:700;font-size:14px;margin-bottom:8px;color:#FFFFFF;">
            {year}년 {month}월
        </div>
        <table style="width:100%;border-collapse:collapse;">
            <tr>{"".join(f'<th style="font-size:11px;color:#64748B;padding-bottom:4px;">{d}</th>' for d in ["일","월","화","수","목","금","토"])}</tr>
            {weeks_html}
        </table>
    </div>
    """


def get_upcoming_events(events: Dict[str, List[str]], days: int = 21) -> List[Dict[str, Any]]:
    """오늘부터 N일 이내 이벤트를 날짜순 정렬해 반환"""
    today = date.today()
    upcoming = []
    for d_str, titles in events.items():
        try:
            d = datetime.strptime(d_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if today <= d <= today + timedelta(days=days):
            for t in titles:
                upcoming.append({"date": d, "title": t, "d_day": (d - today).days})
    return sorted(upcoming, key=lambda x: x["date"])
