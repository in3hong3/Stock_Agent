"""
포트폴리오 알림 시스템 테스트 스크립트
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from core.rag_engine import RAGEngine
from modules.portfolio_analyzer import PortfolioAnalyzer
from modules.portfolio_alert import PortfolioAlert

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_portfolio_alert():
    """포트폴리오 알림 시스템 테스트"""
    print("=" * 80)
    print("포트폴리오 알림 시스템 테스트")
    print("=" * 80)
    
    try:
        # 1. RAG 엔진 초기화
        print("\n[1/5] RAG 엔진 초기화 중...")
        rag_engine = RAGEngine()
        print("✅ RAG 엔진 초기화 완료")
        
        # 2. 포트폴리오 로드
        print("\n[2/5] 포트폴리오 로드 중...")
        analyzer = PortfolioAnalyzer(rag_engine)
        portfolio_df = analyzer.load_portfolio_from_csv("data/portfolio.csv")
        
        if portfolio_df.empty:
            print("❌ 포트폴리오를 로드할 수 없습니다.")
            return
        
        print(f"✅ 포트폴리오 로드 완료: {len(portfolio_df)}개 종목")
        
        # 포트폴리오 요약
        print("\n📊 포트폴리오 요약:")
        total_eval = portfolio_df['eval_amount'].sum()
        total_profit = portfolio_df['profit_loss'].sum()
        avg_profit_rate = (total_profit / (portfolio_df['quantity'] * portfolio_df['avg_price']).sum()) * 100
        
        print(f"  - 총 평가액: ${total_eval:,.0f}")
        print(f"  - 총 평가손익: ${total_profit:,.0f}")
        print(f"  - 평균 수익률: {avg_profit_rate:.2f}%")
        
        # 수익률 상위/하위
        top_stock = portfolio_df.loc[portfolio_df['profit_rate'].idxmax()]
        worst_stock = portfolio_df.loc[portfolio_df['profit_rate'].idxmin()]
        print(f"\n  🏆 최고 수익: {top_stock['name']} ({top_stock['profit_rate']:.1f}%)")
        print(f"  📉 최저 수익: {worst_stock['name']} ({worst_stock['profit_rate']:.1f}%)")
        
        # 3. 알림 시스템 초기화
        print("\n[3/5] 알림 시스템 초기화 중...")
        alert_system = PortfolioAlert(rag_engine)
        print("✅ 알림 시스템 초기화 완료")
        
        # 4. 알림 확인 (최근 7일)
        print("\n[4/5] 알림 확인 중 (최근 7일)...")
        print("⏳ 이 작업은 시간이 걸릴 수 있습니다 (RAG 검색 + AI 분석)...")
        
        alerts = alert_system.check_portfolio_alerts(portfolio_df, days_back=7)
        
        print(f"\n✅ 알림 확인 완료: {len(alerts)}개 발견")
        
        # 5. 알림 출력
        print("\n[5/5] 알림 결과:")
        print("=" * 80)
        
        if alerts:
            # 타입별 분류
            by_type = {}
            for alert in alerts:
                alert_type = alert['type']
                if alert_type not in by_type:
                    by_type[alert_type] = []
                by_type[alert_type].append(alert)
            
            # 타입별 출력
            type_names = {
                'price_change': '📈 가격 변동',
                'news': '📰 뉴스',
                'stop_loss': '🚨 손절 알림',
                'take_profit': '💰 익절 알림',
                'warning': '⚠️ 경고'
            }
            
            for alert_type, type_alerts in by_type.items():
                type_name = type_names.get(alert_type, alert_type)
                print(f"\n{type_name} ({len(type_alerts)}개)")
                print("-" * 80)
                
                for alert in type_alerts:
                    print(f"\n  종목: {alert['name']} ({alert['ticker']})")
                    print(f"  제목: {alert['title']}")
                    print(f"  내용: {alert['message']}")
                    print(f"  우선순위: {alert['priority']}/10")
                    
                    if alert.get('sources'):
                        print(f"  출처: {', '.join(alert['sources'][:2])}")
        else:
            print("\n📭 새로운 알림이 없습니다.")
        
        print("\n" + "=" * 80)
        print("✅ 모든 테스트 완료!")
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_portfolio_alert()
