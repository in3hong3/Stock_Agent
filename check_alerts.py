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

if __name__ == "__main__":
    result = run_alert_check()
    print(f"알림 체크 완료: {result['triggered_count']}건 충족, 이메일 발송: {result['email_sent']}")
