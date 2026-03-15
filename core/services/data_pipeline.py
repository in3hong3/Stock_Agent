import os
import time
import datetime
import json
from dotenv import load_dotenv

from main import YouTubeManager, SheetLogger
from core.stock_extractor import StockExtractor
from core.transcript_processor import TranscriptProcessor
from utils.pinecone_store import PineconeStore
from config.settings import VECTOR_DB_TYPE

load_dotenv()

class DataPipeline:
    """
    유튜브 영상 수집 → Sheets 저장 → LLM 정제 → Pinecone 임베딩을 통합 관리하는 서비스 클래스.
    UI 코드(app.py)와 비즈니스 로직을 분리하기 위해 생성.
    """
    
    def __init__(self):
        self.youtube_api_key = os.getenv("YOUTUBE_API_KEY")
        self.google_sheets_creds = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
        self.spreadsheet_url = os.getenv("SPREADSHEET_URL")
        
        if not all([self.youtube_api_key, self.google_sheets_creds, self.spreadsheet_url]):
            raise ValueError("환경 변수 (YOUTUBE_API_KEY, GOOGLE_SHEETS_CREDENTIALS_JSON, SPREADSHEET_URL) 가 올바르게 설정되지 않았습니다.")
            
        self.yt_manager = YouTubeManager(self.youtube_api_key)
        self.stock_extractor = StockExtractor()
        self.logger = SheetLogger(self.google_sheets_creds, self.spreadsheet_url)
        self.processor = TranscriptProcessor()
        self.vector_store = PineconeStore()
        
    def run_youtube_pipeline(self, channel_id, start_date_str, end_date_str, 
                             progress_callback=None, status_callback=None):
        """
        특정 기간의 유튜브 영상을 수집하고 파이프라인(로깅 -> 전처리 -> 임베딩)을 실행합니다.
        진행률 업데이트를 위해 콜백 함수를 지원합니다.
        
        Args:
            channel_id: 유튜브 채널 ID
            start_date_str: "YYYY-MM-DD"
            end_date_str: "YYYY-MM-DD"
            progress_callback: fn(float, str) -> None
            status_callback: fn(str) -> None
            
        Returns:
            dict: 결과 통계 (success_count, fail_count, skip_count, total_videos, extracted_stocks_count)
        """
        def update_status(msg):
            if status_callback: status_callback(msg)
            
        def update_progress(ratio, msg):
            if progress_callback: progress_callback(ratio, msg)
        
        update_status(f"📅 기간: {start_date_str} ~ {end_date_str}")
        
        # 영상 목록 가져오기
        videos = self.yt_manager.get_videos_in_range(
            channel_id,
            start_date_str,
            end_date_str,
            max_results=50
        )
        
        if not videos:
            update_status("해당 기간에 영상이 없습니다.")
            return {"total_videos": 0}
            
        # 기존 데이터 확인 (중복 방지)
        worksheet = self.logger.get_worksheet("Youtube_Log")
        existing_data = worksheet.get_all_values()
        existing_urls = {row[4] for row in existing_data if len(row) > 4 and row[4]}
        
        data_to_log = []
        stock_mentions_to_log = []
        success_count = 0
        fail_count = 0
        skip_count = 0
        total_videos = len(videos)
        
        update_status(f"총 {total_videos}개의 영상을 처리합니다.")
        
        for idx, video in enumerate(videos, 1):
            update_progress(idx / total_videos, f"진행: {idx}/{total_videos}")
            
            # 중복 체크
            if video['url'] in existing_urls:
                skip_count += 1
                update_status(f"⏭️ 건너뜀: {video['title'][:30]}... (이미 존재)")
                continue
                
            update_status(f"🎬 처리 중 ({idx}/{total_videos}): {video['title'][:40]}...")
            
            # API 제한 방지를 위한 지연
            time.sleep(2)  
            transcript_result = self.yt_manager.get_transcript(video['video_id'])
            
            transcript_list_parsed = []
            if transcript_result and transcript_result[0]:
                transcript_text, timestamps_json = transcript_result
                
                if timestamps_json and timestamps_json != "[]":
                    try:
                        transcript_list_parsed = json.loads(timestamps_json)
                    except json.JSONDecodeError:
                        pass
                
                # 시트 저장 용량 제한 대비
                if len(transcript_text) > 50000:
                    transcript_text = transcript_text[:50000]
                
                # 종목 추출 매칭 엔진
                stocks = self.stock_extractor.extract_stocks_from_transcript(transcript_text, video['title'])
                
                if stocks:
                    for stock in stocks:
                        stock_row = [
                            video['title'],
                            video['channel_title'],
                            video['publish_time'].split('T')[0],
                            stock['종목명'],
                            stock['ticker'],
                            stock['market'],
                            video['url']
                        ]
                        stock_mentions_to_log.append(stock_row)
                
                success_count += 1
            else:
                transcript_text = "자막 없음 (자동 자막 미지원)"
                fail_count += 1
            
            upload_date = video['publish_time'].split('T')[0]
            collect_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            row = [
                upload_date,
                video['channel_title'],
                video['title'],
                transcript_text,
                video['url'],
                collect_time
            ]
            
            data_to_log.append({
                'row': row,
                'transcript_list': transcript_list_parsed,
            })
            existing_urls.add(video['url'])
            
        # Google Sheets 저장
        if data_to_log:
            update_status("💾 Google Sheets에 저장 중...")
            sheet_rows = [e['row'] for e in data_to_log]
            self.logger.log_youtube_data(sheet_rows)
            
        if stock_mentions_to_log:
            self.logger.log_stock_mentions(stock_mentions_to_log)
            
        # Pinecone 임베딩 (LLM 처리)
        if success_count > 0:
            update_status("🤖 LLM 정제 중... (GPT-4o-mini가 [종목/관점/근거]를 추출합니다)")
            try:
                new_data_for_embedding = [
                    e for e in data_to_log
                    if e['row'][3] != "자막 없음 (자동 자막 미지원)"
                ]
                
                if new_data_for_embedding:
                    json_data_list = []
                    metadatas = []
                    
                    for idx2, entry in enumerate(new_data_for_embedding, 1):
                        row = entry['row']
                        tl = entry['transcript_list']
                        update_status(f"  📝 LLM 정제 중 ({idx2}/{len(new_data_for_embedding)}): {row[2][:30]}...")
                        
                        json_data = self.processor.process(
                            transcript=row[3],
                            video_title=row[2],
                            video_url=row[4],
                            transcript_list=tl
                        )
                        
                        metadata = {
                            '업로드일자': row[0],
                            '채널명': row[1],
                            '영상제목': row[2],
                            '영상링크': row[4]
                        }
                        
                        json_data_list.append(json_data)
                        metadatas.append(metadata)
                    
                    update_status("☁️ Pinecone에 업로드 중...")
                    self.vector_store.add_json_documents_v2(json_data_list, metadatas)
                    update_status(f"✅ Pinecone에 {len(json_data_list)}개 영상 임베딩 완료!")
                else:
                    update_status("ℹ️ 임베딩할 새 데이터가 없습니다.")
            except Exception as embed_error:
                update_status(f"⚠️ Pinecone 임베딩 실패: {str(embed_error)}")
                
        return {
            "total_videos": total_videos,
            "success_count": success_count,
            "fail_count": fail_count,
            "skip_count": skip_count,
            "extracted_stocks_count": len(stock_mentions_to_log)
        }
