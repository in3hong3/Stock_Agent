"""
포트폴리오 알림 시스템
보유 종목 관련 중요 뉴스 및 이벤트 모니터링
"""
import logging
from typing import Dict, List, Optional
import pandas as pd
from datetime import datetime, timedelta
from core.rag_engine import RAGEngine
from openai import OpenAI
import os

logger = logging.getLogger(__name__)


class PortfolioAlert:
    """포트폴리오 알림 클래스"""
    
    def __init__(self, rag_engine: RAGEngine):
        """
        초기화
        
        Args:
            rag_engine: RAG 엔진 인스턴스
        """
        self.rag_engine = rag_engine
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def check_portfolio_alerts(self, portfolio_df: pd.DataFrame, 
                               days_back: int = 3) -> List[Dict]:
        """
        포트폴리오 전체 알림 확인
        
        Args:
            portfolio_df: 포트폴리오 데이터프레임
            days_back: 확인할 과거 일수
            
        Returns:
            List[Dict]: 알림 리스트
        """
        if portfolio_df is None or portfolio_df.empty:
            return []
        
        all_alerts = []
        
        logger.info(f"알림 확인 시작: {len(portfolio_df)}개 종목")
        
        # 종목별 알림 확인 (병렬 처리)
        from concurrent.futures import ThreadPoolExecutor
        
        def process_stock(stock):
            return self._check_stock_alerts(
                ticker=stock['ticker'],
                name=stock['name'],
                current_price=stock['current_price'],
                avg_price=stock['avg_price'],
                profit_rate=stock['profit_rate'],
                days_back=days_back
            )
            
        with ThreadPoolExecutor(max_workers=5) as executor:
            stocks = [row for _, row in portfolio_df.iterrows()]
            results = list(executor.map(process_stock, stocks))
            for alerts in results:
                if alerts:
                    all_alerts.extend(alerts)
        
        # 중요도 순으로 정렬
        all_alerts.sort(key=lambda x: x['priority'], reverse=True)
        
        logger.info(f"알림 {len(all_alerts)}개 발견")
        
        return all_alerts
    
    def _check_stock_alerts(self, ticker: str, name: str, 
                           current_price: float, avg_price: float,
                           profit_rate: float, days_back: int = 3) -> List[Dict]:
        """
        개별 종목 알림 확인
        
        Args:
            ticker: 종목 티커
            name: 종목명
            current_price: 현재가
            avg_price: 평균 매수가
            profit_rate: 수익률
            days_back: 확인할 과거 일수
            
        Returns:
            List[Dict]: 알림 리스트
        """
        alerts = []
        
        try:
            # 1. 가격 변동 알림 (±10% 이상)
            if abs(profit_rate) >= 10:
                alerts.append({
                    'ticker': ticker,
                    'name': name,
                    'type': 'price_change',
                    'priority': 8,
                    'title': f"{'급등' if profit_rate > 0 else '급락'} 알림",
                    'message': f"{name} 수익률 {profit_rate:+.1f}%",
                    'timestamp': datetime.now()
                })
            
            # 2. RAG 기반 뉴스 알림
            news_alerts = self._check_news_alerts(ticker, name, days_back)
            alerts.extend(news_alerts)
            
            # 3. 기술적 알림 (손절/익절 기준)
            technical_alerts = self._check_technical_alerts(
                ticker, name, current_price, avg_price, profit_rate
            )
            alerts.extend(technical_alerts)
            
        except Exception as e:
            logger.error(f"알림 확인 오류 ({ticker}): {str(e)}")
        
        return alerts
    
    def _check_news_alerts(self, ticker: str, name: str, 
                          days_back: int = 3) -> List[Dict]:
        """
        RAG 기반 뉴스 알림 확인
        
        Args:
            ticker: 종목 티커
            name: 종목명
            days_back: 확인할 과거 일수
            
        Returns:
            List[Dict]: 뉴스 알림 리스트
        """
        alerts = []
        
        try:
            # RAG 검색: 최근 영상에서 해당 종목 언급 확인
            query = f"{name} {ticker} 최근 뉴스 이슈 전망"
            results = self.rag_engine.retrieve(query, top_k=5)
            
            if not results:
                return alerts
            
            # 최근 영상만 필터링
            cutoff_date = datetime.now() - timedelta(days=days_back)
            recent_results = []
            
            for result in results:
                metadata = result.get('metadata', {})
                upload_date_str = metadata.get('업로드일자', '')
                
                try:
                    # 날짜 파싱 (YYYY-MM-DD 형식 가정)
                    upload_date = datetime.strptime(upload_date_str, '%Y-%m-%d')
                    if upload_date >= cutoff_date:
                        recent_results.append(result)
                except:
                    # 날짜 파싱 실패 시 포함
                    recent_results.append(result)
            
            # 최근 영상이 있으면 AI로 중요도 판단
            if recent_results:
                importance = self._analyze_news_importance(
                    ticker, name, recent_results
                )
                
                if importance['is_important']:
                    alerts.append({
                        'ticker': ticker,
                        'name': name,
                        'type': 'news',
                        'priority': importance['priority'],
                        'title': importance['title'],
                        'message': importance['summary'],
                        'sources': [r['metadata'].get('영상제목', '') for r in recent_results[:3]],
                        'timestamp': datetime.now()
                    })
            
        except Exception as e:
            logger.error(f"뉴스 알림 확인 오류 ({ticker}): {str(e)}")
        
        return alerts
    
    def _analyze_news_importance(self, ticker: str, name: str, 
                                 results: List[Dict]) -> Dict:
        """
        AI를 사용하여 뉴스 중요도 분석
        
        Args:
            ticker: 종목 티커
            name: 종목명
            results: RAG 검색 결과
            
        Returns:
            Dict: 중요도 분석 결과
        """
        try:
            # 컨텍스트 구성
            context = ""
            for i, result in enumerate(results[:3]):
                meta = result['metadata']
                context += f"\n[영상 {i+1}] {meta.get('영상제목', 'N/A')}\n"
                context += f"채널: {meta.get('채널명', 'N/A')}\n"
                context += f"업로드: {meta.get('업로드일자', 'N/A')}\n"
                context += f"내용: {result['document'][:200]}...\n"
            
            # AI 프롬프트
            prompt = f"""다음은 {name} ({ticker}) 종목에 대한 최근 YouTube 영상 분석입니다.

{context}

**임무**: 위 내용이 투자자에게 **중요한 알림**이 필요한지 판단하세요.

**중요 알림 기준**:
- 실적 발표, 어닝 서프라이즈
- 주요 계약 체결, M&A
- 규제 이슈, 소송
- 경영진 변동
- 급격한 주가 변동 원인
- 산업 트렌드 변화

**응답 형식** (JSON):
{{
    "is_important": true/false,
    "priority": 1-10 (10이 가장 중요),
    "title": "알림 제목 (20자 이내)",
    "summary": "요약 (50자 이내)"
}}

일반적인 시장 전망이나 기술적 분석은 중요하지 않습니다.
"""
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 투자 뉴스 중요도를 판단하는 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            logger.error(f"뉴스 중요도 분석 오류: {str(e)}")
            return {
                'is_important': False,
                'priority': 0,
                'title': '',
                'summary': ''
            }
    
    def _check_technical_alerts(self, ticker: str, name: str,
                                current_price: float, avg_price: float,
                                profit_rate: float) -> List[Dict]:
        """
        기술적 알림 확인 (손절/익절 기준)
        
        Args:
            ticker: 종목 티커
            name: 종목명
            current_price: 현재가
            avg_price: 평균 매수가
            profit_rate: 수익률
            
        Returns:
            List[Dict]: 기술적 알림 리스트
        """
        alerts = []
        
        # 손절 기준: -15% 이하
        if profit_rate <= -15:
            alerts.append({
                'ticker': ticker,
                'name': name,
                'type': 'stop_loss',
                'priority': 9,
                'title': "손절 기준 도달",
                'message': f"{name} 손실률 {profit_rate:.1f}% (기준: -15%)",
                'timestamp': datetime.now()
            })
        
        # 익절 기준: +30% 이상
        elif profit_rate >= 30:
            alerts.append({
                'ticker': ticker,
                'name': name,
                'type': 'take_profit',
                'priority': 7,
                'title': "익절 고려 구간",
                'message': f"{name} 수익률 {profit_rate:.1f}% (기준: +30%)",
                'timestamp': datetime.now()
            })
        
        # 경고: -10% ~ -15%
        elif -15 < profit_rate <= -10:
            alerts.append({
                'ticker': ticker,
                'name': name,
                'type': 'warning',
                'priority': 6,
                'title': "손실 경고",
                'message': f"{name} 손실률 {profit_rate:.1f}%",
                'timestamp': datetime.now()
            })
        
        return alerts
    
    def format_alerts(self, alerts: List[Dict]) -> str:
        """
        알림을 읽기 쉬운 형식으로 포맷팅
        
        Args:
            alerts: 알림 리스트
            
        Returns:
            str: 포맷팅된 알림 텍스트
        """
        if not alerts:
            return "📭 새로운 알림이 없습니다."
        
        text = f"🔔 **포트폴리오 알림** ({len(alerts)}개)\n\n"
        
        # 타입별 그룹화
        by_type = {}
        for alert in alerts:
            alert_type = alert['type']
            if alert_type not in by_type:
                by_type[alert_type] = []
            by_type[alert_type].append(alert)
        
        # 타입별 출력
        type_icons = {
            'price_change': '📈',
            'news': '📰',
            'stop_loss': '🚨',
            'take_profit': '💰',
            'warning': '⚠️'
        }
        
        type_names = {
            'price_change': '가격 변동',
            'news': '뉴스',
            'stop_loss': '손절 알림',
            'take_profit': '익절 알림',
            'warning': '경고'
        }
        
        for alert_type, type_alerts in by_type.items():
            icon = type_icons.get(alert_type, '📌')
            type_name = type_names.get(alert_type, alert_type)
            
            text += f"\n{icon} **{type_name}** ({len(type_alerts)}개)\n"
            text += "-" * 50 + "\n"
            
            for alert in type_alerts:
                text += f"\n**{alert['name']}** ({alert['ticker']})\n"
                text += f"  {alert['title']}\n"
                text += f"  {alert['message']}\n"
                
                if alert.get('sources'):
                    text += f"  출처: {', '.join(alert['sources'][:2])}\n"
        
        return text


# CLI 사용 예시
if __name__ == "__main__":
    import sys
    from modules.portfolio_analyzer import PortfolioAnalyzer
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("포트폴리오 알림 확인")
    print("=" * 60)
    
    # RAG 엔진 초기화
    rag_engine = RAGEngine()
    
    # 포트폴리오 로드
    analyzer = PortfolioAnalyzer(rag_engine)
    portfolio_df = analyzer.load_portfolio_from_csv("data/portfolio.csv")
    
    if portfolio_df.empty:
        print("❌ 포트폴리오를 로드할 수 없습니다.")
        sys.exit(1)
    
    print(f"\n📊 로드된 종목: {len(portfolio_df)}개")
    
    # 알림 확인
    alert_system = PortfolioAlert(rag_engine)
    print("\n🔍 알림 확인 중...\n")
    
    alerts = alert_system.check_portfolio_alerts(portfolio_df, days_back=7)
    
    # 결과 출력
    print("\n" + "=" * 60)
    formatted = alert_system.format_alerts(alerts)
    print(formatted)
    print("=" * 60)
