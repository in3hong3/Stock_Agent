# -*- coding: utf-8 -*-
"""
Google Sheets Youtube_Log -> stock_summaries + stock_raw_chunks 재임베딩 스크립트

- Sheets에서 자막 텍스트를 읽어 새 Multi-Vector 파이프라인으로 저장
- 이미 stock_summaries에 있는 영상은 스킵 (중복 방지)
- 자막 없는 영상은 스킵
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from core.transcript_processor import TranscriptProcessor
from utils.vector_store import VectorStore

CREDS_FILE = os.getenv('GOOGLE_SHEETS_CREDENTIALS_JSON')
SPREADSHEET_URL = os.getenv('SPREADSHEET_URL')

# Google Sheets 연결
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
client = gspread.authorize(creds)
ws = client.open_by_url(SPREADSHEET_URL).worksheet('Youtube_Log')
rows = ws.get_all_values()

print(f"Google Sheets rows (including header): {len(rows)}")

# VectorStore 초기화
vs = VectorStore()

# 이미 stock_summaries 에 있는 영상링크 목록 (중복 방지)
existing = vs.summary_collection.get(include=['metadatas'])
existing_urls = set(m.get('영상링크', '') for m in existing.get('metadatas', []))
print(f"Already in stock_summaries: {len(existing_urls)} entries")
print(f"stock_summaries count: {vs.get_summary_collection_count()}")
print(f"stock_raw_chunks count: {vs.get_raw_collection_count()}")

# 처리 대상 필터링
to_process = []
for row in rows[1:]:  # 헤더 스킵
    if len(row) < 5:
        continue
    upload_date = row[0]
    channel    = row[1]
    title      = row[2]
    transcript = row[3]
    url        = row[4]

    if not transcript or transcript.strip() in ['자막 없음 (자동 자막 미지원)', '자막 없음', '']:
        continue
    if url in existing_urls:
        print(f"  SKIP (already in stock_summaries): {title[:40]}")
        continue

    to_process.append((upload_date, channel, title, transcript, url))

print(f"\n처리 대상: {len(to_process)}개 영상")
print("=" * 60)

if not to_process:
    print("처리할 영상이 없습니다.")
    sys.exit(0)

processor = TranscriptProcessor()

json_data_list = []
metadatas = []

for i, (upload_date, channel, title, transcript, url) in enumerate(to_process, 1):
    print(f"\n[{i}/{len(to_process)}] {title[:50]}")
    print(f"  날짜: {upload_date} | 채널: {channel}")

    # LLM 전처리 (transcript_list 없이 → Time-aware 청킹 없이, 요약+종목 추출만)
    # Sheets에는 timestamps_json이 없으므로 transcript_list=None
    try:
        json_data = processor.process(
            transcript=transcript,
            video_title=title,
            video_url=url,
            transcript_list=None  # Sheets에는 타임스탬프 없음
        )

        stocks = json_data.get('stocks', [])
        print(f"  종목 추출: {[s.get('ticker') for s in stocks]}")

        metadata = {
            '업로드일자': upload_date,
            '채널명': channel,
            '영상제목': title,
            '영상링크': url,
        }

        json_data_list.append(json_data)
        metadatas.append(metadata)

    except Exception as e:
        print(f"  ERROR: {e}")
        continue

# 배치 임베딩
if json_data_list:
    print(f"\n{'='*60}")
    print(f"ChromaDB 저장 시작: {len(json_data_list)}개 영상")
    vs.add_json_documents_v2(json_data_list, metadatas)
    print(f"\n{'='*60}")
    print(f"완료!")
    print(f"stock_summaries: {vs.get_summary_collection_count()}")
    print(f"stock_raw_chunks: {vs.get_raw_collection_count()}")
else:
    print("저장할 데이터가 없습니다.")
