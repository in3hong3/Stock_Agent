"""
매일 새벽 유튜버 타이밍 알림 갱신 (cron 전용)
사용: 0 21 * * * cd /home/ubuntu/stock-agent && .venv/bin/python scripts/refresh_video_alerts.py
     (UTC 21:00 = KST 06:00 — 신문 발행보다 1시간 먼저 갱신)
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from utils.yf_quiet import silence_yfinance
silence_yfinance()  # ETF 등 펀더멘털 없는 종목의 404 로그 노이즈 억제

from modules.video_timing import refresh_alerts, needs_refresh
from modules.issue_tracker import get_portfolio_holdings


def main():
    # 비용 절감: 48시간 이내 갱신했으면 스킵 (cron은 매일 돌지만 이틀에 한 번만 실행)
    if not needs_refresh(stale_hours=48):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 48시간 이내 갱신됨 — 스킵")
        return

    # 모든 사용자 종목 합산 (공용 알림이라 합쳐서 한 번에 분석)
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "users"
    )
    all_holdings = []
    seen = set()
    if os.path.isdir(base):
        for user_id in os.listdir(base):
            pf = os.path.join(base, user_id, "portfolio.csv")
            if not os.path.isfile(pf):
                continue
            import utils.user_data as ud
            ud.current_user = lambda uid=user_id: uid
            for h in get_portfolio_holdings():
                key = h.get("ticker")
                if key and key not in seen:
                    seen.add(key)
                    all_holdings.append(h)

    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M')} 영상 알림 갱신 시작 ===")
    print(f"통합 종목 {len(all_holdings)}개 기준 분석...")
    try:
        result = refresh_alerts(holdings=all_holdings, days=90)
        print(f"✅ 완료: 영상 {result['video_count']}개 → 알림 {result['alert_count']}개")
    except Exception as e:
        print(f"❌ 실패: {e}")


if __name__ == "__main__":
    main()
