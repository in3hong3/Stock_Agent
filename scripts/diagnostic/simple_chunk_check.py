"""간단한 청크 상태 확인"""
from utils.vector_store import VectorStore

vs = VectorStore()
results = vs.collection.get(limit=3, include=['documents', 'metadatas'])

print(f"총 청크 수: {vs.collection.count()}개\n")

for i in range(3):
    meta = results['metadatas'][i]
    doc = results['documents'][i]
    print(f"[청크 {i+1}]")
    print(f"영상: {meta.get('영상제목', 'N/A')[:50]}")
    print(f"청크: {meta.get('chunk_index', '?')} / {meta.get('total_chunks', '?')}")
    print(f"길이: {len(doc)}자")
    print(f"내용: {doc[:100]}...")
    print()
