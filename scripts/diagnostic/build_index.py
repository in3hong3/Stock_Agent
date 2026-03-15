"""
벡터 DB 초기 구축 스크립트
Google Sheets의 YouTube 원본 자막 데이터를 ChromaDB에 인덱싱합니다.
(AI 요약 제거, 원본 자막 기반 임베딩)
"""
from utils.sheet_loader import SheetDataLoader
from utils.vector_store import VectorStore
from tqdm import tqdm
import hashlib


def generate_doc_id(row):
    """
    영상 링크를 기반으로 고유 ID 생성
    Args:
        row: DataFrame row
    Returns:
        str: 고유 ID
    """
    url = row.get('영상링크', '')
    if url:
        return hashlib.md5(url.encode()).hexdigest()
    else:
        # URL이 없으면 제목 + 채널명으로 ID 생성
        title = row.get('영상제목', '')
        channel = row.get('채널명', '')
        return hashlib.md5(f"{title}_{channel}".encode()).hexdigest()


def build_index(days=None, rebuild=False):
    """
    벡터 DB 인덱스 구축
    Args:
        days: 최근 N일 데이터만 인덱싱 (None이면 전체)
        rebuild: True면 기존 컬렉션 삭제 후 재구축
    """
    print("=== Starting Vector DB Indexing ===\n")
    
    # 1. Google Sheets에서 데이터 로드
    print("Loading data from Google Sheets...")
    loader = SheetDataLoader()
    
    if days:
        df = loader.get_latest_entries(days=days)
        print(f"Loaded {len(df)} entries from the last {days} days")
    else:
        df = loader.load_youtube_data()
        print(f"Loaded {len(df)} total entries")
    
    if df.empty:
        print("No data found. Exiting.")
        return
    
    # 2. 벡터 스토어 초기화
    print("\nInitializing Vector Store...")
    store = VectorStore()
    
    if rebuild:
        print("Rebuilding collection...")
        store.delete_collection()
        store = VectorStore()  # 재생성
    
    # 3. 기존 문서 ID 확인 (중복 방지)
    existing_count = store.get_collection_count()
    print(f"Existing documents in collection: {existing_count}")
    
    # 4. 데이터 인덱싱
    print("\nIndexing documents...")
    
    documents = []
    metadatas = []
    ids = []
    
    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Processing"):
        # 새 스키마 (전체자막) 우선, 없으면 구 스키마 (AI 요약) 사용
        transcript = row.get('전체자막', '')
        
        # 하위 호환성: 전체자막이 없으면 AI_3줄요약 사용
        if not transcript or transcript.strip() in ['자막 없음 (자동 자막 미지원)', '']:
            transcript = row.get('AI_3줄요약', '')
        
        # 자막/요약이 없거나 유효하지 않으면 스킵
        if not transcript or transcript.strip() in ['자막 없음', '요약 실패', '자막 없음 (자동 자막 미지원)', '']:
            continue
        
        # 문서 ID 생성 (video_id 우선, 없으면 URL 기반)
        video_id = row.get('영상ID', '')
        if video_id:
            doc_id = f"vid_{video_id}"
        else:
            doc_id = generate_doc_id(row)
        
        # 문서 텍스트 (원본 자막 또는 AI 요약)
        document_text = transcript
        
        # 텍스트 청킹 (OpenAI 임베딩 토큰 제한 대응: 약 8192 토큰, 한글 기준 약 1~2만자 안전)
        # 검색 품질을 위해 더 작은 단위(4000자)로 나누어 저장
        chunk_size = 4000
        text_chunks = [document_text[i:i+chunk_size] for i in range(0, len(document_text), chunk_size)]
        
        # 메타데이터 준비
        base_metadata = {
            '영상제목': str(row.get('영상제목', '')),
            '채널명': str(row.get('채널명', '')),
            '영상링크': str(row.get('영상링크', '')),
            '업로드일자': str(row.get('업로드일자', '')),
            '수집일시': str(row.get('수집일시', '')),
            '영상ID': str(row.get('영상ID', ''))
        }
        
        # 각 청크별로 문서/메타/ID 추가
        for chunk_idx, chunk in enumerate(text_chunks):
            chunk_doc_id = f"{doc_id}_chunk_{chunk_idx}"
            chunk_meta = base_metadata.copy()
            chunk_meta['chunk_index'] = chunk_idx
            chunk_meta['total_chunks'] = len(text_chunks)
            
            documents.append(chunk)
            metadatas.append(chunk_meta)
            ids.append(chunk_doc_id)
    
    # 5. 배치로 추가 (API 호출 최적화)
    if documents:
        print(f"\nAdding {len(documents)} documents to ChromaDB...")
        
        # 배치 크기 설정 (너무 크면 API 제한에 걸릴 수 있음)
        batch_size = 10
        
        for i in tqdm(range(0, len(documents), batch_size), desc="Uploading batches"):
            batch_docs = documents[i:i+batch_size]
            batch_metas = metadatas[i:i+batch_size]
            batch_ids = ids[i:i+batch_size]
            
            try:
                store.add_documents(batch_docs, batch_metas, batch_ids)
            except Exception as e:
                print(f"\nError adding batch {i//batch_size + 1}: {e}")
                continue
        
        print(f"\n✅ Indexing complete!")
        print(f"Total documents in collection: {store.get_collection_count()}")
    else:
        print("No valid documents to index.")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Build vector DB index from Google Sheets")
    parser.add_argument('--days', type=int, default=None, help='Index only last N days of data')
    parser.add_argument('--rebuild', action='store_true', help='Rebuild collection from scratch')
    
    args = parser.parse_args()
    
    build_index(days=args.days, rebuild=args.rebuild)
