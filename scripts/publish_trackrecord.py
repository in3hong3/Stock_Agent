"""
유튜버 콜 트랙레코드 갱신 (cron 전용)
전체 매수/주의 콜을 미래 수익률로 채점 → data/youtuber_trackrecord.json.
가격 다운로드가 무거워 주 1회만 (콜 성적은 시간이 지나며 천천히 확정됨).

사용:
  30 9 * * 0 cd /home/ubuntu/stock-agent && .venv/bin/python scripts/publish_trackrecord.py >> logs/trackrecord.log 2>&1
  (UTC 일 09:30 = KST 일 18:30 — 주간 리포트 직후)
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
    from modules.youtuber_trackrecord import publish_trackrecord
    from modules.youtuber_insights import publish_insights

    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M')} 트랙레코드 갱신 시작 ===")
    try:
        r = publish_trackrecord()
        b30 = next((b for b in r["buy_stats"] if b["horizon"] == 30), None)
        head = (f"매수+30일 적중 {b30['hit_rate']}% 알파 {b30['avg_alpha']:+.1f}%"
                if b30 else "")
        print(f"✅ 트랙레코드: {r['channel']} · 콜 {r['total_calls']}개 · "
              f"가격확보 {r['priced_tickers']}종목 · 채점 {r['scored']}건 · {head}")
    except Exception as e:
        print(f"❌ 트랙레코드 실패: {e}")

    # 인사이트(섹터 관심도 + 시황 관점) — 같은 유튜버 주간 배치라 함께 갱신
    try:
        ins = publish_insights(days=30)
        secs = ins["sector_focus"]["sectors"][:3]
        top = ", ".join(f"{s['sector']}({s['total']})" for s in secs)
        print(f"✅ 인사이트: 최근30일 콜 {ins['recent_call_count']}개 · "
              f"상위섹터 {top} · 시황 {len(ins['market_view'])}개")
    except Exception as e:
        print(f"❌ 인사이트 실패: {e}")


if __name__ == "__main__":
    main()
