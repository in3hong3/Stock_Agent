"""
가격/지표 알림 시스템
data/alerts.json에 저장된 조건을 체크하고 충족 시 이메일 발송.
UI(app.py)와 cron 스크립트(check_alerts.py) 양쪽에서 사용한다.
"""
import os
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import Dict, List, Any

import yfinance as yf

ALERTS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "alerts.json")

# 지원 조건 타입
CONDITION_TYPES = {
    "price_above": "가격이 목표가 이상",
    "price_below": "가격이 목표가 이하",
    "rsi_above": "RSI가 기준값 이상 (과매수)",
    "rsi_below": "RSI가 기준값 이하 (과매도)",
}


def load_alerts() -> List[Dict[str, Any]]:
    if not os.path.exists(ALERTS_FILE):
        return []
    try:
        with open(ALERTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_alerts(alerts: List[Dict[str, Any]]):
    os.makedirs(os.path.dirname(ALERTS_FILE), exist_ok=True)
    with open(ALERTS_FILE, "w", encoding="utf-8") as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)


def add_alert(ticker: str, condition: str, value: float) -> Dict[str, Any]:
    alerts = load_alerts()
    alert = {
        "id": max((a["id"] for a in alerts), default=0) + 1,
        "ticker": ticker.upper(),
        "condition": condition,
        "value": value,
        "enabled": True,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_triggered": None,
    }
    alerts.append(alert)
    save_alerts(alerts)
    return alert


def remove_alert(alert_id: int):
    alerts = [a for a in load_alerts() if a["id"] != alert_id]
    save_alerts(alerts)


def _get_rsi(ticker: str) -> float:
    df = yf.Ticker(ticker).history(period="3mo")
    if df.empty:
        return None
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain / loss))
    return float(rsi.iloc[-1])


def check_alerts() -> List[Dict[str, Any]]:
    """
    모든 활성 알림 조건을 체크하고 충족된 알림 리스트 반환.
    충족된 알림은 last_triggered가 갱신되며 비활성화된다 (중복 발송 방지).
    """
    alerts = load_alerts()
    triggered = []
    # 티커별로 데이터 1회만 조회
    price_cache, rsi_cache = {}, {}

    for alert in alerts:
        if not alert.get("enabled", True):
            continue
        ticker = alert["ticker"]
        cond = alert["condition"]
        target = alert["value"]

        try:
            if cond.startswith("price"):
                if ticker not in price_cache:
                    hist = yf.Ticker(ticker).history(period="1d")
                    price_cache[ticker] = float(hist["Close"].iloc[-1]) if not hist.empty else None
                current = price_cache[ticker]
            else:  # rsi
                if ticker not in rsi_cache:
                    rsi_cache[ticker] = _get_rsi(ticker)
                current = rsi_cache[ticker]

            if current is None:
                continue

            hit = (
                (cond in ("price_above", "rsi_above") and current >= target)
                or (cond in ("price_below", "rsi_below") and current <= target)
            )
            if hit:
                alert["last_triggered"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                alert["enabled"] = False  # 1회 발송 후 비활성화
                triggered.append({**alert, "current_value": round(current, 2)})
        except Exception as e:
            print(f"알림 체크 실패 ({ticker}): {e}")

    if triggered:
        save_alerts(alerts)
    return triggered


def send_alert_email(triggered: List[Dict[str, Any]]) -> bool:
    """충족된 알림들을 하나의 이메일로 발송 (네이버 SMTP)"""
    from_email = os.getenv("BRIEFING_FROM_EMAIL")
    app_password = os.getenv("BRIEFING_APP_PASSWORD")
    to_email = os.getenv("BRIEFING_TO_EMAIL")
    if not all([from_email, app_password, to_email]):
        print("⚠️ 이메일 환경변수 미설정 (BRIEFING_FROM_EMAIL 등)")
        return False

    rows = ""
    for t in triggered:
        cond_label = CONDITION_TYPES.get(t["condition"], t["condition"])
        rows += (
            f"<tr>"
            f"<td style='padding:8px; border-bottom:1px solid #eee;'><b>{t['ticker']}</b></td>"
            f"<td style='padding:8px; border-bottom:1px solid #eee;'>{cond_label}</td>"
            f"<td style='padding:8px; border-bottom:1px solid #eee;'>{t['value']}</td>"
            f"<td style='padding:8px; border-bottom:1px solid #eee; color:#e11;'><b>{t['current_value']}</b></td>"
            f"</tr>"
        )

    html = f"""
    <html><body style="font-family: sans-serif;">
    <h2>🔔 Stock Agent 가격 알림</h2>
    <p>{datetime.now().strftime('%Y-%m-%d %H:%M')} 기준, 설정한 조건이 충족됐습니다.</p>
    <table style="border-collapse: collapse; width: 100%;">
        <tr style="background:#f5f5f5;">
            <th style="padding:8px; text-align:left;">종목</th>
            <th style="padding:8px; text-align:left;">조건</th>
            <th style="padding:8px; text-align:left;">기준값</th>
            <th style="padding:8px; text-align:left;">현재값</th>
        </tr>
        {rows}
    </table>
    <p style="color:#888; font-size:12px;">알림은 1회 발송 후 자동 비활성화됩니다. 앱에서 다시 활성화할 수 있습니다.</p>
    </body></html>
    """
    text = "\n".join(
        f"[{t['ticker']}] {CONDITION_TYPES.get(t['condition'], t['condition'])} "
        f"(기준: {t['value']}, 현재: {t['current_value']})"
        for t in triggered
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔔 [Stock Agent] 알림 {len(triggered)}건 발생"
    msg["From"] = from_email
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP("smtp.naver.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(from_email, app_password)
            server.sendmail(from_email, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"이메일 발송 실패: {e}")
        return False


def run_alert_check() -> Dict[str, Any]:
    """cron 진입점: 체크 → 발송. 결과 요약 반환."""
    triggered = check_alerts()
    sent = send_alert_email(triggered) if triggered else False
    return {"triggered_count": len(triggered), "email_sent": sent, "triggered": triggered}
