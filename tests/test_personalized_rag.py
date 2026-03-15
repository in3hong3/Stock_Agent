"""
개인화 RAG 챗봇 테스트 스크립트
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from core.rag_engine import RAGEngine
from core.personalized_rag import PersonalizedRAG

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_personalized_rag():
    """개인화 RAG 챗봇 테스트"""
    print("=" * 80)
    print("개인화 RAG 챗봇 테스트")
    print("=" * 80)
    
    try:
        # 1. RAG 엔진 초기화
        print("\n[1/4] RAG 엔진 초기화 중...")
        base_rag = RAGEngine()
        print("✅ RAG 엔진 초기화 완료")
        
        # 2. 개인화 RAG 초기화
        print("\n[2/4] 개인화 RAG 초기화 중...")
        personalized_rag = PersonalizedRAG(base_rag, portfolio_path="data/portfolio.csv")
        print("✅ 개인화 RAG 초기화 완료")
        
        # 포트폴리오 정보 확인
        if personalized_rag.portfolio_df is not None and not personalized_rag.portfolio_df.empty:
            print(f"\n📊 로드된 포트폴리오: {len(personalized_rag.portfolio_df)}개 종목")
            print("\n주요 보유 종목 (상위 5개):")
            top_5 = personalized_rag.portfolio_df.nlargest(5, 'eval_amount')
            for idx, stock in top_5.iterrows():
                print(f"  - {stock['name']} ({stock['ticker']}): {stock['quantity']:,}주, 수익률 {stock['profit_rate']:.1f}%")
        else:
            print("\n⚠️ 포트폴리오가 비어있습니다")
            return
        
        # 3. 테스트 질문들
        print("\n[3/4] 테스트 질문 실행 중...")
        test_queries = [
            "내가 보유한 AI 종목들 어때?",
            "엔비디아 전망은?",
            "빅테크 기업들 실적은?"
        ]
        
        for i, query in enumerate(test_queries, 1):
            print("\n" + "=" * 80)
            print(f"테스트 {i}/{len(test_queries)}: {query}")
            print("=" * 80)
            
            # 질문 처리
            result = personalized_rag.chat(
                query=query,
                top_k=5,
                temperature=0.7,
                use_portfolio_context=True
            )
            
            # 결과 출력
            print(f"\n📝 답변 (처음 300자):")
            print(result['answer'][:300] + "...")
            
            # 관련 보유 종목
            if result.get('related_holdings'):
                print(f"\n💼 관련 보유 종목: {len(result['related_holdings'])}개")
                for stock in result['related_holdings']:
                    print(f"  - {stock['name']} ({stock['ticker']}): {stock['quantity']:,}주, 수익률 {stock['profit_rate']:.1f}%")
            else:
                print("\n💼 관련 보유 종목: 없음")
            
            # 소스
            if result.get('sources'):
                print(f"\n📺 참고 영상: {len(result['sources'])}개")
                for j, source in enumerate(result['sources'][:3], 1):
                    print(f"  {j}. {source.get('영상제목', 'N/A')[:50]}...")
            
            print("\n" + "-" * 80)
        
        # 4. 완료
        print("\n[4/4] 테스트 완료!")
        print("\n✅ 모든 테스트 성공!")
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_personalized_rag()
