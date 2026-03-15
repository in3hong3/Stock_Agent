# -*- coding: utf-8 -*-
"""
Google Sheets Youtube_Log -> Pinecone 재임베딩 스크립트
설계도 1번(LLM 정제)과 2번(Pinecone 전환)을 반영합니다.
"""
import sys, os
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from core.transcript_processor import TranscriptProcessor
from utils.pinecone_store import PineconeStore

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

CREDS_FILE = os.getenv('GOOGLE_SHEETS_CREDENTIALS_JSON')
SPREADSHEET_URL = os.getenv('SPREADSHEET_URL')

def main():
    # PineconeStore 초기화
    try:
        ps = PineconeStore()
    except Exception as e:
        print(f"Pinecone 초기화 실패: {e}")
        return

    # Google Sheets 연결
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
    client = gspread.authorize(creds)
    ws = client.open_by_url(SPREADSHEET_URL).worksheet('Youtube_Log')
    rows = ws.get_all_values()

    print(f"Google Sheets rows (including header): {len(rows)}")

    # ── 중복 방지: Pinecone에 이미 저장된 영상 URL 목록 가져오기 ──
    # summary 네임스페이스의 메타데이터에서 '영상링크' 값을 수집
    existing_urls = set()
    try:
        stats = ps.index.describe_index_stats()
        ns_count = stats.get('namespaces', {}).get('stock-summaries', {}).get('vector_count', 0)
        if ns_count > 0:
            # 전체 목록 페이징 방식으로 가져오기
            for page in ps.index.list(namespace='stock-summaries'):
                if not page:
                    break
                result = ps.index.fetch(ids=page, namespace='stock-summaries')
                for vec in result.get('vectors', {}).values():
                    url = vec.get('metadata', {}).get('영상링크', '')
                    if url:
                        existing_urls.add(url)
        print(f"이미 Pinecone에 저장된 영상: {len(existing_urls)}개")
    except Exception as e:
        print(f"기존 데이터 확인 실패 (전체 재처리): {e}")

    # 처리 대상 필터링 (자막 없음 제외 + 이미 저장된 영상 스킵)
    to_process = []
    for row in rows[1:]:  # 헤더 스킵
        if len(row) < 5: continue
        upload_date, channel, title, transcript, url = row[0:5]

        if not transcript or transcript.strip() in ['자막 없음 (자동 자막 미지원)', '자막 없음', '']:
            continue

        if url in existing_urls:
            print(f"  SKIP (이미 저장됨): {title[:40]}")
            continue

        to_process.append((upload_date, channel, title, transcript, url))

    print(f"\n새로 처리할 영상: {len(to_process)}개")
    print("=" * 60)

    if not to_process:
        print("새로 추가된 영상이 없습니다. DB가 최신 상태입니다! ✅")
        return

    processor = TranscriptProcessor()

    json_data_list = []
    metadatas = []

    for i, (upload_date, channel, title, transcript, url) in enumerate(to_process, 1):
        print(f"\n[{i}/{len(to_process)}] {title[:50]}")
        
        try:
            # LLM 전처리 (설계도 1번: Ticker, Stance, Reason 추출)
            json_data = processor.process(
                transcript=transcript,
                video_title=title,
                video_url=url
            )

            stocks = json_data.get('stocks', [])
            print(f"  추출 종목: {[s.get('ticker') for s in stocks]}")

            metadata = {
                '업로드일자': upload_date,
                '채널명': channel,
                '영상제목': title,
                '영상링크': url,
            }

            json_data_list.append(json_data)
            metadatas.append(metadata)

            # 배치 사이즈 조절 (너무 많으면 메모리 이슈)
            if len(json_data_list) >= 5:
                print(f"--- 5개 단위로 Pinecone 저장 중 ---")
                ps.add_json_documents_v2(json_data_list, metadatas)
                json_data_list = []
                metadatas = []

        except Exception as e:
            print(f"  ERROR processing {title}: {e}")
            continue

    # 남은 데이터 저장
    if json_data_list:
        print(f"\n남은 {len(json_data_list)}개 데이터 Pinecone 저장...")
        ps.add_json_documents_v2(json_data_list, metadatas)

    print("\n" + "="*60)
    print("Pinecone 재구축 완료!")
    print("="*60)

if __name__ == "__main__":
    main()
