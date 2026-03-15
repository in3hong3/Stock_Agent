"""
ChromaDB 재구축 스크립트
기존 DB를 백업하고 새로운 JSON 기반 청킹으로 전체 재구축
"""
import os
import sys
import shutil
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.vector_store import VectorStore
from utils.sheet_loader import SheetDataLoader
from core.transcript_processor import TranscriptProcessor

load_dotenv()



def backup_chromadb(source_dir="./data/chroma_db", backup_dir="./data/chroma_db_backup"):
    """
    현재 ChromaDB를 백업
    """
    if os.path.exists(source_dir):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{backup_dir}_{timestamp}"
        
        print(f"📦 Backing up ChromaDB to {backup_path}...")
        shutil.copytree(source_dir, backup_path)
        print(f"✅ Backup complete: {backup_path}")
        return backup_path
    else:
        print("⚠️  No existing ChromaDB found. Skipping backup.")
        return None


def rebuild_chromadb():
    """
    ChromaDB를 새로운 JSON 기반 청킹으로 재구축
    """
    print("\n" + "="*60)
    print("🔄 ChromaDB 재구축 시작")
    print("="*60 + "\n")
    
    # 1. 백업
    backup_path = backup_chromadb()
    
    # 2. 기존 DB 삭제
    print("\n🗑️  Deleting old ChromaDB...")
    vector_store = VectorStore()
    try:
        vector_store.delete_collection()
        print("✅ Old collection deleted")
    except Exception as e:
        print(f"⚠️  Could not delete collection: {e}")
    
    # 3. 새 컬렉션 생성
    print("\n🆕 Creating new collection...")
    vector_store = VectorStore()  # 재초기화
    print("✅ New collection created")
    
    # 4. Google Sheets에서 데이터 로드
    print("\n📊 Loading data from Google Sheets...")
    sheet_loader = SheetDataLoader()
    
    try:
        # Youtube_Log 시트에서 데이터 가져오기
        worksheet = sheet_loader.get_worksheet("Youtube_Log")
        all_data = worksheet.get_all_values()
        
        if not all_data or len(all_data) < 2:
            print("❌ No data found in Youtube_Log sheet")
            return
        
        # 헤더 제외
        headers = all_data[0]
        rows = all_data[1:]
        
        print(f"✅ Loaded {len(rows)} videos from Google Sheets")
        
        # 5. 전처리 및 임베딩
        print("\n🤖 Processing transcripts with LLM...")
        processor = TranscriptProcessor()
        
        processed_count = 0
        skipped_count = 0
        error_count = 0
        
        # 배치 처리
        batch_size = 10
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]
            
            json_data_list = []
            metadatas = []
            
            for row in batch:
                # 데이터 파싱 (헤더: 업로드일자, 채널명, 영상제목, 전체자막, 영상링크, 수집일시)
                if len(row) < 5:
                    skipped_count += 1
                    continue
                
                upload_date = row[0]
                channel = row[1]
                title = row[2]
                transcript = row[3]
                video_url = row[4]
                
                # 자막 없는 경우 스킵
                if not transcript or "자막 없음" in transcript:
                    skipped_count += 1
                    continue
                
                try:
                    # LLM 전처리
                    print(f"  Processing [{processed_count + 1}]: {title[:40]}...")
                    json_data = processor.process(transcript, title, video_url)
                    
                    # 메타데이터 구성
                    metadata = {
                        '업로드일자': upload_date,
                        '채널명': channel,
                        '영상제목': title,
                        '영상링크': video_url
                    }
                    
                    json_data_list.append(json_data)
                    metadatas.append(metadata)
                    processed_count += 1
                    
                except Exception as e:
                    print(f"  ❌ Error processing video: {e}")
                    error_count += 1
            
            # 배치 임베딩
            if json_data_list:
                print(f"\n  💾 Embedding batch {i//batch_size + 1}...")
                vector_store.add_json_documents_v2(json_data_list, metadatas)
        
        # 6. 완료 통계
        print("\n" + "="*60)
        print("✅ ChromaDB 재구축 완료!")
        print("="*60)
        print(f"📊 통계:")
        print(f"  - 처리 성공: {processed_count}개")
        print(f"  - 스킵: {skipped_count}개")
        print(f"  - 오류: {error_count}개")
        print(f"  - 총 청크 수: {vector_store.get_collection_count()}개")
        
        if backup_path:
            print(f"\n💾 백업 위치: {backup_path}")
            print("   (문제 발생 시 이 폴더를 ./data/chroma_db로 복원하세요)")
        
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        
        if backup_path:
            print(f"\n⚠️  백업에서 복원하려면:")
            print(f"   1. ./data/chroma_db 삭제")
            print(f"   2. {backup_path}를 ./data/chroma_db로 이름 변경")


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║          ChromaDB 재구축 스크립트                           ║
║                                                            ║
║  ⚠️  경고: 기존 ChromaDB가 삭제되고 재구축됩니다            ║
║  💾 백업은 자동으로 생성됩니다                              ║
║  🤖 모든 영상을 LLM으로 재처리합니다 (비용 발생)            ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
    """)
    
    response = input("계속하시겠습니까? (yes/no): ")
    
    if response.lower() in ['yes', 'y']:
        rebuild_chromadb()
    else:
        print("❌ 취소되었습니다.")
