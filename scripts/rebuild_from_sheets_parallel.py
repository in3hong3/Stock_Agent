# -*- coding: utf-8 -*-
import sys, os
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from core.transcript_processor import TranscriptProcessor
from utils.vector_store import VectorStore

def process_video(item, processor):
    upload_date, channel, title, transcript, url = item
    try:
        # Semantic Segmentation (LLM-based)
        json_data = processor.process(
            transcript=transcript,
            video_title=title,
            video_url=url,
            transcript_list=None
        )
        
        metadata = {
            '업로드일자': upload_date,
            '채널명': channel,
            '영상제목': title,
            '영상링크': url,
        }
        return (json_data, metadata)
    except Exception as e:
        print(f"  [ERROR] {title[:30]}: {e}")
        return None

def main():
    CREDS_FILE = os.getenv('GOOGLE_SHEETS_CREDENTIALS_JSON')
    SPREADSHEET_URL = os.getenv('SPREADSHEET_URL')

    # Google Sheets 연결
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
    client = gspread.authorize(creds)
    ws = client.open_by_url(SPREADSHEET_URL).worksheet('Youtube_Log')
    rows = ws.get_all_values()

    print(f"Google Sheets rows: {len(rows)}")

    vs = VectorStore()
    
    # 중복 체크 로직 (URL + Ticker 조합이 아닌 URL만으로 체크할 경우 위험하므로 초기화 상태 권장)
    # 이미 reset_db를 했으므로 existing_urls는 비어있을 것임
    existing = vs.summary_collection.get(include=['metadatas'])
    existing_urls = set(m.get('영상링크', '') for m in existing.get('metadatas', []))
    
    to_process = []
    for row in rows[1:]:
        if len(row) < 5: continue
        transcript = row[3]
        url = row[4]
        if not transcript or transcript.strip() in ['자막 없음', '']: continue
        if url in existing_urls: continue
        to_process.append(row[:5])

    print(f"Total to process: {len(to_process)}")
    if not to_process: return

    processor = TranscriptProcessor()
    
    results = []
    # 병렬 처리 (OpenAI API Rate Limit 주의)
    max_workers = 5
    print(f"Starting parallel processing with {max_workers} workers...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_video = {executor.submit(process_video, item, processor): item for item in to_process}
        
        count = 0
        for future in as_completed(future_to_video):
            count += 1
            res = future.result()
            if res:
                results.append(res)
                print(f"[{count}/{len(to_process)}] Processed: {res[1]['영상제목'][:40]}")
            
            # 10개 단위로 중간 저장 (안전장치)
            if len(results) >= 10:
                print(f"\n--- Batch Saving {len(results)} docs to ChromaDB ---")
                json_list = [r[0] for r in results]
                meta_list = [r[1] for r in results]
                vs.add_json_documents_v2(json_list, meta_list)
                results = []

    # 남은 데이터 저장
    if results:
        print(f"\n--- Saving final {len(results)} docs to ChromaDB ---")
        json_list = [r[0] for r in results]
        meta_list = [r[1] for r in results]
        vs.add_json_documents_v2(json_list, meta_list)

    print("\nAll done!")
    print(f"stock_summaries: {vs.get_summary_collection_count()}")

if __name__ == "__main__":
    main()
