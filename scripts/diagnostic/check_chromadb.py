"""
ChromaDB 데이터 확인 스크립트
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.vector_store import VectorStore

def check_database():
    print("=== ChromaDB 데이터 확인 ===\n")
    
    vs = VectorStore()
    
    # 1. 총 문서 수
    count = vs.collection.count()
    print(f"총 문서 수: {count}\n")
    
    if count == 0:
        print("⚠️ 데이터베이스가 비어있습니다!")
        print("build_index.py를 실행하여 데이터를 인덱싱하세요.")
        return
    
    # 2. 구글 검색
    print("[테스트 1] '구글' 검색")
    print("-" * 50)
    results = vs.search('구글', top_k=3)
    if results and results.get('documents') and results['documents'][0]:
        for i, doc in enumerate(results['documents'][0][:3], 1):
            metadata = results['metadatas'][0][i-1] if results.get('metadatas') else {}
            print(f"{i}. {metadata.get('영상제목', 'N/A')[:60]}")
            print(f"   채널: {metadata.get('채널명', 'N/A')}")
    else:
        print("검색 결과 없음")
    
    print("\n")
    
    # 3. Google 검색
    print("[테스트 2] 'Google' 검색")
    print("-" * 50)
    results = vs.search('Google', top_k=3)
    if results and results.get('documents') and results['documents'][0]:
        for i, doc in enumerate(results['documents'][0][:3], 1):
            metadata = results['metadatas'][0][i-1] if results.get('metadatas') else {}
            print(f"{i}. {metadata.get('영상제목', 'N/A')[:60]}")
            print(f"   채널: {metadata.get('채널명', 'N/A')}")
    else:
        print("검색 결과 없음")
    
    print("\n")
    
    # 4. 샘플 데이터 확인
    print("[샘플 데이터] 최근 3개 문서")
    print("-" * 50)
    sample = vs.collection.get(limit=3)
    if sample and sample.get('metadatas'):
        for i, metadata in enumerate(sample['metadatas'], 1):
            print(f"{i}. {metadata.get('영상제목', 'N/A')[:60]}")
            print(f"   채널: {metadata.get('채널명', 'N/A')}")
            print(f"   날짜: {metadata.get('업로드일자', 'N/A')}")
    
    print("\n")
    
    # 5. 채널별 문서 수
    print("[채널별 통계]")
    print("-" * 50)
    all_data = vs.collection.get()
    if all_data and all_data.get('metadatas'):
        channels = {}
        for metadata in all_data['metadatas']:
            channel = metadata.get('채널명', 'Unknown')
            channels[channel] = channels.get(channel, 0) + 1
        
        for channel, count in sorted(channels.items(), key=lambda x: x[1], reverse=True):
            print(f"{channel}: {count}개")


if __name__ == "__main__":
    check_database()
