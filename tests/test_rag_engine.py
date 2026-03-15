"""
RAG 엔진 테스트 스크립트
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rag_engine import RAGEngine

def test_rag_engine():
    print("=== RAG 엔진 테스트 ===\n")
    
    engine = RAGEngine()
    
    # 테스트 1: 구글 검색
    print("[테스트 1] '구글의 전망' 검색")
    print("-" * 50)
    
    # retrieve 메서드 직접 테스트
    retrieved = engine.retrieve("구글의 전망", top_k=5)
    print(f"검색 결과: {len(retrieved)}개\n")
    
    if retrieved:
        for i, doc in enumerate(retrieved[:3], 1):
            print(f"{i}. {doc['metadata'].get('영상제목', 'N/A')[:60]}")
            print(f"   채널: {doc['metadata'].get('채널명', 'N/A')}")
            print(f"   거리: {doc['distance']:.4f}")
            print()
    else:
        print("⚠️ 검색 결과가 비어있습니다!")
        print("retrieve() 메서드에서 문제가 발생했을 수 있습니다.")
    
    print("\n" + "=" * 50 + "\n")
    
    # 테스트 2: chat 메서드 테스트 (OPENAI_API_KEY 필요)
    print("[테스트 2] chat() 메서드 테스트")
    print("-" * 50)
    
    try:
        result = engine.chat("구글의 전망은?", top_k=5)
        print(f"답변 길이: {len(result['answer'])} 자")
        print(f"소스 개수: {len(result['sources'])}개\n")
        
        if result['sources']:
            print("참고 소스:")
            for i, source in enumerate(result['sources'][:3], 1):
                print(f"{i}. {source.get('영상제목', 'N/A')[:60]}")
        
        print(f"\n답변:\n{result['answer'][:500]}...")
        
    except Exception as e:
        print(f"❌ 오류: {type(e).__name__} - {str(e)}")
        print("\nOPENAI_API_KEY가 설정되지 않았거나 다른 문제가 있을 수 있습니다.")


if __name__ == "__main__":
    test_rag_engine()
