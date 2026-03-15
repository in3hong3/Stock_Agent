"""
RAG 대화 기록 관리 테스트 스크립트
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rag_engine import RAGEngine

def test_conversation_memory():
    print("=== RAG 대화 기록 관리 테스트 ===\n")
    
    engine = RAGEngine()
    
    # 대화 히스토리 시뮬레이션
    conversation_history = []
    
    # 첫 번째 질문
    print("[테스트 1] 첫 번째 질문 (맥락 없음)")
    print("-" * 50)
    query1 = "올랜도 킴의 최근 영상 요약해줘"
    
    try:
        result1 = engine.chat(
            query=query1,
            top_k=5,
            temperature=0.3,
            conversation_history=None
        )
        
        print(f"질문: {query1}")
        print(f"\n답변 (처음 300자):\n{result1['answer'][:300]}...")
        print(f"\n소스 개수: {len(result1['sources'])}개")
        print(f"후속 질문 개수: {len(result1.get('followup_questions', []))}개")
        
        if result1.get('followup_questions'):ㅂㅂ
            print("\n후속 질문:")
            for i, q in enumerate(result1['followup_questions'], 1):
                print(f"  {i}. {q}")
        
        # 대화 히스토리에 추가
        conversation_history.append({"role": "user", "content": query1})
        conversation_history.append({"role": "assistant", "content": result1['answer']})0
    except Exception as e:
        print(f"❌ 오류: {type(e).__name__} - {str(e)}")
    
    print("\n" + "=" * 50 + "\n")
    
    # 두 번째 질문 (맥락 참조)
    print("[테스트 2] 두 번째 질문 (이전 대화 맥락 참조)")
    print("-" * 50)
    query2 = "그 종목의 리스크 요인은 뭐야?"
    
    try:
        result2 = engine.chat(
            query=query2,
            top_k=5,
            temperature=0.3,
            conversation_history=conversation_history
        )
        
        print(f"질문: {query2}")
        print(f"\n답변 (처음 300자):\n{result2['answer'][:300]}...")
        print(f"\n소스 개수: {len(result2['sources'])}개")
        print(f"후속 질문 개수: {len(result2.get('followup_questions', []))}개")
        
        if result2.get('followup_questions'):
            print("\n후속 질문:")
            for i, q in enumerate(result2['followup_questions'], 1):
                print(f"  {i}. {q}")
        
        # 대화 히스토리에 추가
        conversation_history.append({"role": "user", "content": query2})
        conversation_history.append({"role": "assistant", "content": result2['answer']})
        
    except Exception as e:
        print(f"❌ 오류: {type(e).__name__} - {str(e)}")
    
    print("\n" + "=" * 50 + "\n")
    
    # 세 번째 질문 (맥락 계속 참조)
    print("[테스트 3] 세 번째 질문 (대화 맥락 계속 유지)")
    print("-" * 50)
    query3 = "그럼 지금 매수하는게 좋을까?"
    
    try:
        result3 = engine.chat(
            query=query3,
            top_k=5,
            temperature=0.3,
            conversation_history=conversation_history
        )
        
        print(f"질문: {query3}")
        print(f"\n답변 (처음 300자):\n{result3['answer'][:300]}...")
        print(f"\n소스 개수: {len(result3['sources'])}개")
        print(f"후속 질문 개수: {len(result3.get('followup_questions', []))}개")
        
        if result3.get('followup_questions'):
            print("\n후속 질문:")
            for i, q in enumerate(result3['followup_questions'], 1):
                print(f"  {i}. {q}")
        
    except Exception as e:
        print(f"❌ 오류: {type(e).__name__} - {str(e)}")
    
    print("\n✅ 테스트 완료!")


if __name__ == "__main__":
    test_conversation_memory()
