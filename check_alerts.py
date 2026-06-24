"""
가격 알림 체크 스크립트 (cron 전용)
서버 crontab에서 주기적으로 실행:
    */30 * * * * cd /path/to/app && python check_alerts.py
"""
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from modules.price_alert import run_alert_check
from modules.watchlist import run_watchlist_check

if __name__ == "__main__":
    result = run_alert_check()
    print(f"알림 체크 완료: {result['triggered_count']}건 충족, 이메일 발송: {result['email_sent']}")

    # 관심+보유종목 스마트 매수 타이밍 (상태 전환분만 카카오 발송)
    wl = run_watchlist_check()
    print(f"매수 타이밍 체크: 신규 {wl.get('new_count', 0)}건, 카카오 {wl.get('kakao_sent')}")
