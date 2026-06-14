"""
매일 자동 신문 발행 (cron 전용)
서버 crontab에서 매일 새벽 호출되어 모든 사용자의 데일리 신문을 미리 발행해둔다.
사용자가 아침에 접속하면 이미 만들어진 신문이 떠있어서 대기 없음.

사용:
  0 22 * * * cd /home/ubuntu/stock-agent && .venv/bin/python scripts/auto_publish_paper.py
  (UTC 22:00 = KST 07:00)
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def publish_for_user(user_id: str) -> dict:
    """특정 사용자의 신문 발행"""
    # user_data가 streamlit 세션을 보지만, 환경변수로 강제 지정 가능하게
    os.environ["FORCED_USER_ID"] = user_id

    # user_data 모듈 캐시 초기화를 위해 monkey patch
    import utils.user_data as ud
    ud.current_user = lambda: user_id

    from modules.daily_paper import (
        publish_daily_paper, fetch_holdings_news, get_sec_filings,
    )
    from modules.market_overview import get_macro_data
    from modules.issue_tracker import get_portfolio_holdings

    holdings = get_portfolio_holdings()
    if not holdings:
        return {"user": user_id, "skipped": "보유 종목 없음"}

    tickers = [h["ticker"] for h in holdings]
    print(f"[{user_id}] {len(tickers)}종목 신문 발행 중...")

    macro = get_macro_data()
    news = fetch_holdings_news([{"ticker": t, "name": t} for t in tickers])
    filings = get_sec_filings(tickers)
    result = publish_daily_paper(macro, news, filings, holdings=holdings)

    return {
        "user": user_id,
        "status": result.get("status"),
        "engine": result.get("engine"),
    }


def main():
    # 사용자 목록: data/users/ 하위 폴더 전체
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "users")
    if not os.path.isdir(base):
        print("data/users/ 폴더 없음")
        return

    users = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
    if not users:
        print("사용자 없음")
        return

    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M')} 자동 발행 시작: {len(users)}명 ===")
    for user_id in users:
        try:
            result = publish_for_user(user_id)
            print(f"  ✅ {result}")
        except Exception as e:
            print(f"  ❌ {user_id} 실패: {e}")
    print("=== 완료 ===")


if __name__ == "__main__":
    main()
