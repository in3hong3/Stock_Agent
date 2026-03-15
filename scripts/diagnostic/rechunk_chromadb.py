"""ChromaDB 재청킹 스크립트"""
import sys
from utils.vector_store import VectorStore
from utils.sheet_loader import SheetDataLoader

print("=" * 80)
print("ChromaDB 재청킹 시작")
print("=" * 80)

# 1. 기존 컬렉션 삭제
print("\n[1/4] 기존 컬렉션 삭제 중...")
vector_store = VectorStore()
try:
    vector_store.delete_collection()
    print("✅ 기존 컬렉션 삭제 완료")
except Exception as e:
    print(f"⚠️ 삭제 중 오류 (무시 가능): {e}")

# 2. 새 컬렉션 생성
print("\n[2/4] 새 컬렉션 생성 중...")
vector_store = VectorStore()  # 재초기화
print("✅ 새 컬렉션 생성 완료")

# 3. Google Sheets에서 데이터 로드
print("\n[3/4] Google Sheets에서 데이터 로드 중...")
try:
    loader = SheetDataLoader()
    youtube_data = loader.load_youtube_data()
    
    if youtube_data.empty:
        print("❌ 데이터가 없습니다!")
        sys.exit(1)
    
    print(f"✅ {len(youtube_data)}개 영상 로드 완료")
    
    # 자막 없는 영상 제외
    valid_data = youtube_data[
        (youtube_data['전체자막'].notna()) & 
        (youtube_data['전체자막'] != '자막 없음 (자동 자막 미지원)')
    ]
    
    print(f"   유효한 영상: {len(valid_data)}개")
    
except Exception as e:
    print(f"❌ 데이터 로드 실패: {e}")
    sys.exit(1)

# 4. 청킹 및 임베딩
print("\n[4/4] 청킹 및 임베딩 중...")
print("   (시간이 걸릴 수 있습니다...)")

documents = []
metadatas = []

for idx, row in valid_data.iterrows():
    documents.append(row['전체자막'])
    metadatas.append({
        '업로드일자': str(row['업로드일자']),
        '채널명': row['채널명'],
        '영상제목': row['영상제목'],
        '영상링크': row['영상링크']
    })

try:
    vector_store.add_documents(documents, metadatas)
    print(f"\n✅ 재청킹 완료!")
    print(f"   총 청크 수: {vector_store.collection.count()}")
    
except Exception as e:
    print(f"❌ 임베딩 실패: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("재청킹 완료!")
print("=" * 80)
