"""
주간 유튜버 리포트 자동 발행 (cron 전용)
매주 일요일 저녁(KST) 1회 호출 — 이번 주 영상들을 종합해 data/weekly_reports/에 저장.

사용:
  0 9 * * 0 cd /home/ubuntu/stock-agent && .venv/bin/python scripts/publish_weekly_report.py >> logs/weekly_report.log 2>&1
  (UTC 일 09:00 = KST 일 18:00 — 아침 잡들과 시간대 분리)
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from utils.yf_quiet import silence_yfinance
silence_yfinance()


def main():
    from modules.weekly_youtube_report import publish_weekly_report, week_key

    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M')} 주간 리포트 발행 시작 ({week_key()}) ===")
    try:
        report = publish_weekly_report()
        print(
            f"✅ 완료: {report['week_key']} · 영상 {report['video_count']}개 · "
            f"채널 {report['channel_count']}개 · 종목 {report['stock_count']}개 · "
            f"엔진 {report['engine']}"
        )
    except Exception as e:
        print(f"❌ 실패: {e}")
        raise


if __name__ == "__main__":
    main()
