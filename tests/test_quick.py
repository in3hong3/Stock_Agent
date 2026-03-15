"""
간단한 통합 테스트 - 개인화 RAG + 알림 시스템
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rag_engine import RAGEngine
from core.personalized_rag import PersonalizedRAG
from modules.portfolio_analyzer import PortfolioAnalyzer
from modules.portfolio_alert import PortfolioAlert

def main():
    print("=" * 80)
    print("포트폴리오 기능 통합 테스트")
    print("=" * 80)
    
    # 1. 개인화 RAG 테스트
    print("\n" + "=" * 80)
    print("TEST 1: 개인화 RAG 챗봇")
    print("=" * 80)
    
    try:
        base_rag = RAGEngine()
        personalized_rag = PersonalizedRAG(base_rag, portfolio_path="data/portfolio.csv")
        
        if personalized_rag.portfolio_df is not None and not personalized_rag.portfolio_df.empty:
            print(f"✅ 포트폴리오 로드 성공: {len(personalized_rag.portfolio_df)}개 종목")
            
            # 간단한 질문 테스트
            query = "내가 보유한 AI 종목들 어때?"
            print(f"\n질문: {query}")
            
            result = personalized_rag.chat(query=query, top_k=3, temperature=0.7, use_portfolio_context=True)
            
            print(f"\n답변 (처음 200자):\n{result['answer'][:200]}...")
            
            if result.get('related_holdings'):
                print(f"\n✅ 관련 보유 종목 매칭 성공: {len(result['related_holdings'])}개")
                for stock in result['related_holdings'][:3]:
                    print(f"  - {stock['name']} ({stock['ticker']})")
            else:
                print("\n⚠️ 관련 보유 종목 없음")
            
            print("\n✅ TEST 1 통과!")
        else:
            print("❌ 포트폴리오 로드 실패")
    except Exception as e:
        print(f"❌ TEST 1 실패: {str(e)}")
    
    # 2. 알림 시스템 테스트
    print("\n" + "=" * 80)
    print("TEST 2: 포트폴리오 알림 시스템")
    print("=" * 80)
    
    try:
        rag_engine = RAGEngine()
        analyzer = PortfolioAnalyzer(rag_engine)
        portfolio_df = analyzer.load_portfolio_from_csv("data/portfolio.csv")
        
        if not portfolio_df.empty:
            print(f"✅ 포트폴리오 로드 성공: {len(portfolio_df)}개 종목")
            
            # 포트폴리오 요약
            total_eval = portfolio_df['eval_amount'].sum()
            avg_profit_rate = (portfolio_df['profit_loss'].sum() / (portfolio_df['quantity'] * portfolio_df['avg_price']).sum()) * 100
            
            print(f"\n포트폴리오 요약:")
            print(f"  - 총 평가액: ${total_eval:,.0f}")
            print(f"  - 평균 수익률: {avg_profit_rate:.2f}%")
            
            # 알림 확인 (최근 3일만, 빠른 테스트)
            alert_system = PortfolioAlert(rag_engine)
            print(f"\n알림 확인 중 (최근 3일)...")
            
            alerts = alert_system.check_portfolio_alerts(portfolio_df, days_back=3)
            
            print(f"\n✅ 알림 확인 완료: {len(alerts)}개 발견")
            
            if alerts:
                # 알림 타입별 개수
                by_type = {}
                for alert in alerts:
                    alert_type = alert['type']
                    by_type[alert_type] = by_type.get(alert_type, 0) + 1
                
                print("\n알림 타입별 개수:")
                for alert_type, count in by_type.items():
                    print(f"  - {alert_type}: {count}개")
                
                # 상위 3개 알림 출력
                print("\n주요 알림 (상위 3개):")
                for i, alert in enumerate(alerts[:3], 1):
                    print(f"\n  {i}. {alert['name']} ({alert['ticker']})")
                    print(f"     {alert['title']}: {alert['message']}")
            else:
                print("\n📭 새로운 알림 없음")
            
            print("\n✅ TEST 2 통과!")
        else:
            print("❌ 포트폴리오 로드 실패")
    except Exception as e:
        print(f"❌ TEST 2 실패: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # 완료
    print("\n" + "=" * 80)
    print("✅ 모든 테스트 완료!")
    print("=" * 80)

if __name__ == "__main__":
    main()
