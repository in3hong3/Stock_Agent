"""ChromaDB 청크 상태 확인 스크립트"""
from utils.vector_store import VectorStore

vs = VectorStore()

print("=" * 80)
print("ChromaDB 청크 상태 확인")
print("=" * 80)

# 전체 청크 수
total_chunks = vs.collection.count()
print(f"\n총 청크 수: {total_chunks}개")

# 샘플 청크 가져오기
results = vs.collection.get(limit=10, include=['documents', 'metadatas'])

print(f"\n샘플 청크 10개:")
print("-" * 80)

for i in range(min(10, len(results['documents']))):
    meta = results['metadatas'][i]
    doc = results['documents'][i]
    
    print(f"\n[청크 {i+1}]")
    print(f"영상: {meta.get('영상제목', 'N/A')[:60]}")
    print(f"날짜: {meta.get('업로드일자', 'N/A')}")
    print(f"청크 번호: {meta.get('chunk_index', 'N/A')} / {meta.get('total_chunks', 'N/A')}")
    print(f"내용 길이: {len(doc)} 문자")
    print(f"내용 미리보기:")
    print(f"  {doc[:200]}...")
    print("-" * 80)

# 특정 영상의 모든 청크 확인
print("\n\n특정 영상의 청크 분포 확인:")
print("=" * 80)

# 첫 번째 영상의 모든 청크 가져오기
first_video_title = results['metadatas'][0].get('영상제목', 'N/A')
first_video_link = results['metadatas'][0].get('영상링크', 'N/A')

# 같은 영상의 모든 청크 찾기
all_results = vs.collection.get(include=['metadatas'])
same_video_chunks = [
    (i, meta) for i, meta in enumerate(all_results['metadatas'])
    if meta.get('영상링크') == first_video_link
]

print(f"\n영상: {first_video_title}")
print(f"총 청크 수: {len(same_video_chunks)}개")
print(f"청크 인덱스: ", end="")
print([meta.get('chunk_index', 'N/A') for _, meta in same_video_chunks[:10]])

print("\n" + "=" * 80)
print("확인 완료!")
print("=" * 80)
