"""
히스토리컬 데이터 수집 스크립트
특정 채널의 과거 영상을 수집하고 종목 정보 및 주가 데이터를 저장합니다.
"""
import os
import datetime
import argparse
from dotenv import load_dotenv
from main import YouTubeManager, SheetLogger
from core.stock_extractor import StockExtractor
from modules.stock_tracker import StockTracker
from tqdm import tqdm

load_dotenv()


def collect_historical_data(channel_ids, start_date, end_date=None, max_videos=100):
    """
    히스토리컬 데이터 수집 메인 함수 (AI 요약 제거, 원본 자막 버전)
    Args:
        channel_ids: YouTube 채널 ID 리스트
        start_date: 시작일 (YYYY-MM-DD)
        end_date: 종료일 (None이면 현재)
        max_videos: 채널당 최대 수집 영상 수
    """
    print("=== Historical Data Collection Started (Raw Transcript Version) ===\n")
    
    # API 키 확인
    youtube_api_key = os.getenv("YOUTUBE_API_KEY")
    google_creds = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_url = os.getenv("SPREADSHEET_URL")
    
    if not all([youtube_api_key, google_creds, sheet_url]):
        print("Error: Missing required environment variables")
        return
    
    # 초기화
    yt_manager = YouTubeManager(youtube_api_key)
    stock_extractor = StockExtractor()
    stock_tracker = StockTracker()
    sheet_logger = SheetLogger(google_creds, sheet_url)
    
    all_videos_processed = 0
    all_mentions_count = 0
    
    for channel_id in channel_ids:
        channel_id = channel_id.strip()
        if not channel_id or channel_id.startswith("Other"): continue
        
        print(f"\n>>> Processing Channel: {channel_id}")
        
        # 1. 영상 수집
        print(f"Step 1: Fetching videos from {start_date} to {end_date or 'now'}...")
        videos = yt_manager.get_videos_in_range(
            channel_id, 
            start_date, 
            end_date, 
            max_results=max_videos
        )
        
        if not videos:
            print(f"No videos found for channel {channel_id} in the specified range.")
            continue
        
        print(f"Found {len(videos)} videos\n")
        
        # 데이터 저장용 리스트 (채널별)
        youtube_data = []
        stock_mentions_data = []
        stock_prices_data = []
        
        # 2. 각 영상 처리
        print(f"Step 2: Processing {len(videos)} videos...")
        print(f"⏱️  Rate limiting: 15초/영상 + 5개마다 60초 휴식 (YouTube 차단 방지)")
        
        for idx, video in enumerate(tqdm(videos, desc=f"Channel {channel_id[:10]}..."), 1):
            video_title = video['title']
            video_url = video['url']
            video_id = video['video_id']
            channel_title = video['channel_title']
            upload_date = video['publish_time'].split('T')[0]
            
            # 2.1 자막 추출 (텍스트 + 타임스탬프)
            transcript_result = yt_manager.get_transcript(video_id)
            
            if not transcript_result or not transcript_result[0]:
                print(f"      No transcript for: {video_title[:30]}...")
                transcript_text = "자막 없음 (자동 자막 미지원)"
            else:
                transcript_text, _ = transcript_result
            
            # 50,000자 제한 대응
            transcript_part1 = transcript_text[:50000] if len(transcript_text) > 50000 else transcript_text
            
            # YouTube 데이터 저장 (6개 컬럼: 업로드일자, 채널명, 영상제목, 전체자막, 영상링크, 수집일시)
            collect_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            youtube_row = [
                upload_date,        # 0: 업로드일자
                channel_title,      # 1: 채널명
                video_title,        # 2: 영상제목
                transcript_part1,   # 3: 전체자막
                video_url,          # 4: 영상링크
                collect_time        # 5: 수집일시
            ]
            youtube_data.append(youtube_row)
            
            # 2.3 종목 추출 (자막에서 직접)
            if transcript_text and transcript_text != "자막 없음 (자동 자막 미지원)":
                stocks = stock_extractor.extract_stocks_from_transcript(transcript_text, video_title)
                
                if stocks:
                    # 종목 언급 데이터 저장
                    for stock in stocks:
                        mention_row = [
                            video_title,
                            channel_title,
                            upload_date,
                            stock['종목명'],
                            stock['ticker'],
                            stock['market'],
                            video_url
                        ]
                        stock_mentions_data.append(mention_row)
                    
                    # 2.4 주가 데이터 수집 (히스토리컬 수집 시에는 시간이 많이 걸리므로 선택사항이지만 일단 유지)
                    price_results = stock_tracker.track_mentioned_stocks(stocks, upload_date)
                    for ticker, prices_df in price_results.items():
                        if not prices_df.empty:
                            for _, p_row in prices_df.iterrows():
                                stock_prices_data.append([
                                    p_row['날짜'].strftime('%Y-%m-%d'),
                                    ticker,
                                    p_row['종목명'],
                                    p_row['종가'],
                                    p_row['전일대비'],
                                    p_row['등락률(%)'],
                                    int(p_row['거래량'])
                                ])
            
            # YouTube API 차단 방지: 영상당 15초 대기 (더욱 보수적으로 조정)
            import time
            time.sleep(15)
            
            # 5개마다 저장 및 긴 휴식 (실시간으로 시트에서 확인 가능하도록)
            if idx % 5 == 0 or idx == len(videos):
                print(f"\n\n--- [Batch Save] Saving data for videos {idx-len(youtube_data)+1} to {idx} ---")
                
                if youtube_data:
                    print(f"Saving {len(youtube_data)} videos to Youtube_Log...")
                    sheet_logger.log_youtube_data(youtube_data)
                    all_videos_processed += len(youtube_data)
                    youtube_data = [] # 버퍼 비우기
                
                if stock_mentions_data:
                    print(f"Saving {len(stock_mentions_data)} stock mentions...")
                    sheet_logger.log_stock_mentions(stock_mentions_data)
                    all_mentions_count += len(stock_mentions_data)
                    stock_mentions_data = [] # 버퍼 비우기
                
                if stock_prices_data:
                    print(f"Saving {len(stock_prices_data)} stock price records...")
                    sheet_logger.log_stock_prices(stock_prices_data)
                    stock_prices_data = [] # 버퍼 비우기
                
                if idx % 5 == 0 and idx != len(videos):
                    print(f"      ⏸️  5개 처리 완료. 60초 긴 휴식 중... ({idx}/{len(videos)})")
                    time.sleep(60)

    print("\n=== All Historical Collection Tasks Completed ===")
    print(f"Total Videos: {all_videos_processed}")
    print(f"Total Stock Mentions: {all_mentions_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect historical YouTube data (Raw Transcript Version)")
    parser.add_argument('--channel-id', type=str, help='YouTube channel ID (comma separated list)')
    parser.add_argument('--start-date', type=str, default='2026-01-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default=None, help='End date (YYYY-MM-DD, default: now)')
    parser.add_argument('--max-videos', type=int, default=50, help='Max videos per channel')
    
    args = parser.parse_args()
    
    # 채널 ID 결정
    if args.channel_id:
        channel_ids = [cid.strip() for cid in args.channel_id.split(",")]
    else:
        channel_ids = [cid.strip() for cid in os.getenv("TARGET_CHANNEL_ID_LIST", "").split(",") if cid.strip()]
    
    if not channel_ids:
        print("Error: No channel ID provided. Use --channel-id or set TARGET_CHANNEL_ID_LIST in .env")
        exit(1)
    
    print(f"Channel IDs: {channel_ids}")
    print(f"Date range: {args.start_date} ~ {args.end_date or 'now'}")
    print(f"Max videos per channel: {args.max_videos}\n")
    
    collect_historical_data(
        channel_ids=channel_ids,
        start_date=args.start_date,
        end_date=args.end_date,
        max_videos=args.max_videos
    )
