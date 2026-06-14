"""
daily_smart_collect.py
컴퓨터 부팅 시 자동 실행되는 스마트 수집 스크립트.

1. 구글 시트에서 마지막 수집 날짜를 확인
2. 오늘까지 빠진 날짜가 있으면 유튜브 영상 수집
3. 시장 지표(CNN 공포/탐욕, 주가 등)도 함께 업데이트
"""

import os
import sys
import datetime
from dotenv import load_dotenv

# 프로젝트 루트를 기준으로 모듈 import가 되도록 설정
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()


def collect_youtube():
    """구글 시트의 마지막 수집일 이후 ~ 오늘까지 유튜브 영상 수집"""
    from core.services.data_pipeline import DataPipeline
    from utils.sheet_loader import SheetDataLoader

    print("\n" + "=" * 50)
    print("  📺 유튜브 영상 수집")
    print("=" * 50)

    loader = SheetDataLoader()
    pipeline = DataPipeline()

    # 1. 마지막 수집 날짜 확인
    info = loader.get_last_data_info()
    last_date_str = info.get("youtube_date")

    if last_date_str and last_date_str != "N/A":
        last_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
        start_date = last_date  # 마지막 날짜부터 다시 확인 (당일 추가 영상 대비)
        print(f"  📅 마지막 수집일: {last_date_str}")
    else:
        start_date = datetime.date.today() - datetime.timedelta(days=2)
        print(f"  ⚠️ 수집 이력 없음. {start_date}부터 수집합니다.")

    today = datetime.date.today()

    if start_date > today:
        print(f"  ✅ 이미 최신 상태입니다.")
        return

    print(f"  🔍 수집 범위: {start_date} ~ {today}")

    # 2. 채널별 수집
    channels = os.getenv("TARGET_CHANNEL_ID_LIST", "").split(",")
    total_collected = 0

    for cid in channels:
        cid = cid.strip()
        if not cid or cid.startswith("Other"):
            continue

        print(f"\n  📡 채널: {cid}")

        try:
            result = pipeline.run_youtube_pipeline(
                channel_id=cid,
                start_date_str=start_date.strftime("%Y-%m-%d"),
                end_date_str=today.strftime("%Y-%m-%d"),
            )

            success = result.get("success_count", 0)
            skip = result.get("skip_count", 0)
            fail = result.get("fail_count", 0)
            total_collected += success

            print(f"     ✅ 신규: {success}개 | ⏭️ 중복: {skip}개 | ❌ 실패: {fail}개")

        except Exception as e:
            print(f"     ❌ 오류: {e}")

    print(f"\n  🎉 총 {total_collected}개 영상 수집 완료!")


def collect_market():
    """시장 지표 수집 (CNN 공포탐욕 + yfinance 주가)"""
    from main import update_market_log

    print("\n" + "=" * 50)
    print("  📈 시장 지표 수집")
    print("=" * 50)

    try:
        update_market_log()
        print("  ✅ 시장 지표 업데이트 완료!")
    except Exception as e:
        print(f"  ❌ 시장 지표 수집 실패: {e}")


def main():
    start_time = datetime.datetime.now()
    print("🚀" + "=" * 48)
    print(f"  Stock Agent 자동 수집 시작")
    print(f"  실행 시각: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 1. 유튜브 영상 수집
    collect_youtube()

    # 2. 시장 지표 수집
    collect_market()

    # 완료
    elapsed = datetime.datetime.now() - start_time
    print("\n" + "=" * 50)
    print(f"  🏁 전체 수집 완료! (소요 시간: {elapsed.seconds // 60}분 {elapsed.seconds % 60}초)")
    print("=" * 50)


if __name__ == "__main__":
    main()
