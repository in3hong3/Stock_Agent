"""
포트폴리오 리밸런싱 제안 시스템
AI 기반 포트폴리오 최적화 및 조정 제안
"""
import logging
from typing import Dict, List, Optional
import pandas as pd
from openai import OpenAI
import os
from core.rag_engine import RAGEngine

logger = logging.getLogger(__name__)


class PortfolioRebalancer:
    """포트폴리오 리밸런싱 제안 클래스"""
    
    def __init__(self, rag_engine: RAGEngine):
        """
        초기화
        
        Args:
            rag_engine: RAG 엔진 인스턴스
        """
        self.rag_engine = rag_engine
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def analyze_portfolio_balance(self, portfolio_df: pd.DataFrame) -> Dict:
        """
        포트폴리오 균형 분석
        
        Args:
            portfolio_df: 포트폴리오 데이터프레임
            
        Returns:
            Dict: 균형 분석 결과
        """
        if portfolio_df is None or portfolio_df.empty:
            return {'status': 'empty'}
        
        try:
            total_value = portfolio_df['eval_amount'].sum()
            
            # 종목별 비중 계산
            portfolio_df['weight'] = (portfolio_df['eval_amount'] / total_value) * 100
            
            # 섹터 분류 (간단한 매핑)
            sector_map = self._classify_sectors(portfolio_df)
            
            # 섹터별 비중
            sector_weights = {}
            for sector, tickers in sector_map.items():
                sector_value = portfolio_df[portfolio_df['ticker'].isin(tickers)]['eval_amount'].sum()
                sector_weights[sector] = (sector_value / total_value) * 100
            
            # 집중도 분석
            top_5_weight = portfolio_df.nlargest(5, 'weight')['weight'].sum()
            
            # 리스크 분석
            losing_stocks = len(portfolio_df[portfolio_df['profit_loss'] < 0])
            total_stocks = len(portfolio_df)
            
            return {
                'status': 'success',
                'total_value': total_value,
                'stock_weights': portfolio_df[['ticker', 'name', 'weight', 'profit_rate']].to_dict('records'),
                'sector_weights': sector_weights,
                'concentration': {
                    'top_5_weight': top_5_weight,
                    'is_concentrated': top_5_weight > 70  # 상위 5개가 70% 이상
                },
                'risk_metrics': {
                    'losing_stocks_ratio': (losing_stocks / total_stocks) * 100,
                    'avg_profit_rate': portfolio_df['profit_rate'].mean(),
                    'volatility': portfolio_df['profit_rate'].std()
                }
            }
            
        except Exception as e:
            logger.error(f"포트폴리오 균형 분석 오류: {str(e)}")
            return {'status': 'error', 'message': str(e)}
    
    def _classify_sectors(self, portfolio_df: pd.DataFrame) -> Dict[str, List[str]]:
        """
        종목을 섹터별로 분류
        
        Args:
            portfolio_df: 포트폴리오 데이터프레임
            
        Returns:
            Dict[str, List[str]]: {섹터명: [티커 리스트]}
        """
        sector_map = {
            '빅테크': ['GOOGL', 'AMZN', 'META', 'ORCL'],
            '반도체': ['NVDA', 'MU', 'TSM', 'SKYT'],
            '양자컴퓨팅': ['IONQ'],
            '에너지': ['FSLR', 'IREN'],
            '금융': ['KRE'],
            '헬스케어': ['XLV'],
            '일본': ['1497.T', '9984.T'],
            'ETF': ['445290.KS', 'SGOV'],
            '현금': ['USD']
        }
        
        # 실제 보유 종목만 필터링
        tickers = portfolio_df['ticker'].tolist()
        filtered_map = {}
        
        for sector, sector_tickers in sector_map.items():
            matching_tickers = [t for t in sector_tickers if t in tickers]
            if matching_tickers:
                filtered_map[sector] = matching_tickers
        
        return filtered_map
    
    def generate_rebalancing_suggestions(self, portfolio_df: pd.DataFrame,
                                         target_allocation: Optional[Dict] = None) -> Dict:
        """
        리밸런싱 제안 생성
        
        Args:
            portfolio_df: 포트폴리오 데이터프레임
            target_allocation: 목표 섹터 비중 (None이면 균형 포트폴리오 제안)
            
        Returns:
            Dict: 리밸런싱 제안
        """
        try:
            # 현재 포트폴리오 분석
            balance = self.analyze_portfolio_balance(portfolio_df)
            
            if balance['status'] != 'success':
                return balance
            
            # 1. 수학적 최적화 (Efficient Frontier)
            optimization_result = self._optimize_portfolio_weights(portfolio_df)
            
            # 2. 리밸런싱 시뮬레이션 (비용 포함)
            simulation_result = {}
            if optimization_result.get('success'):
                simulation_result = self._simulate_rebalancing(
                    portfolio_df, 
                    optimization_result['weights']
                )
            
            # 3. RAG 기반 시장 분석
            market_insights = self._get_market_insights(portfolio_df)
            
            # 4. AI 리밸런싱 제안 생성
            suggestions = self._generate_ai_suggestions(
                balance, 
                market_insights,
                target_allocation,
                optimization_result,
                simulation_result
            )
            
            return {
                'status': 'success',
                'current_balance': balance,
                'optimization': optimization_result,
                'simulation': simulation_result,
                'market_insights': market_insights,
                'suggestions': suggestions
            }
            
        except Exception as e:
            logger.error(f"리밸런싱 제안 생성 오류: {str(e)}")
            return {'status': 'error', 'message': str(e)}

    def _optimize_portfolio_weights(self, portfolio_df: pd.DataFrame) -> Dict:
        """
        MPT 기반 포트폴리오 최적 비중 계산
        """
        try:
            from modules.portfolio_optimizer import PortfolioOptimizer
            
            optimizer = PortfolioOptimizer()
            tickers = portfolio_df['ticker'].tolist()
            
            # 데이터 수집 (최근 2년)
            prices = optimizer.fetch_historical_data(tickers, period="2y")
            
            if prices.empty:
                return {'success': False, 'message': '데이터 부족'}
            
            # Max Sharpe 포트폴리오 계산
            result = optimizer.optimize_portfolio(prices, objective="max_sharpe")
            
            # Efficient Frontier 시뮬레이션
            frontier = optimizer.simulate_efficient_frontier(prices, num_portfolios=1000)
            
            # 결과에 Frontier 데이터 추가 (시각화용)
            result['frontier'] = frontier.to_dict('list')
            
            # 현재 포트폴리오의 위치 계산
            current_weights = portfolio_df.set_index('ticker')['weight'] / 100
            # 인덱스 정렬을 위해 prices 컬럼 순서 맞춤
            current_weights = current_weights.reindex(prices.columns).fillna(0).values
            
            curr_ret, curr_vol, curr_sharpe = optimizer.portfolio_performance(
                current_weights, 
                *optimizer.calculate_metrics(prices)
            )
            
            result['current_metrics'] = {
                'returns': curr_ret,
                'volatility': curr_vol,
                'sharpe_ratio': curr_sharpe
            }
            
            return result
            
        except Exception as e:
            logger.error(f"포트폴리오 최적화 오류: {str(e)}")
            return {'success': False, 'message': str(e)}

    def _simulate_rebalancing(self, portfolio_df: pd.DataFrame, 
                            target_weights: Dict[str, float]) -> Dict:
        """
        리밸런싱 비용 및 효과 시뮬레이션
        """
        try:
            total_value = portfolio_df['eval_amount'].sum()
            current_holdings = portfolio_df.set_index('ticker')['eval_amount'].to_dict()
            
            simulation = []
            total_cost = 0
            
            for ticker, target_w in target_weights.items():
                current_val = current_holdings.get(ticker, 0)
                target_val = total_value * target_w
                diff = target_val - current_val
                
                # 비용 계산 (수수료 0.25%, 세금 0.25% 가정 - 간소화)
                cost = 0
                if diff != 0:
                    cost = abs(diff) * 0.0025  # 수수료
                    if diff < 0:  # 매도 시 세금 추가 (국내주식 가정 or 미국주식 양도세 별도)
                        cost += abs(diff) * 0.0025
                
                total_cost += cost
                
                simulation.append({
                    'ticker': ticker,
                    'current_value': current_val,
                    'target_value': target_val,
                    'diff': diff,
                    'action': 'BUY' if diff > 0 else 'SELL',
                    'cost': cost
                })
            
            return {
                'total_cost': total_cost,
                'net_value_after_rebalancing': total_value - total_cost,
                'cost_ratio': (total_cost / total_value) * 100,
                'details': simulation
            }
            
        except Exception as e:
            logger.error(f"리밸런싱 시뮬레이션 오류: {str(e)}")
            return {}
    
    def _get_market_insights(self, portfolio_df: pd.DataFrame) -> Dict:
        """
        RAG 기반 시장 인사이트 수집
        
        Args:
            portfolio_df: 포트폴리오 데이터프레임
            
        Returns:
            Dict: 시장 인사이트
        """
        insights = {}
        
        try:
            # 주요 보유 종목 (상위 5개)
            top_holdings = portfolio_df.nlargest(5, 'eval_amount')
            
            # RAG 검색 및 요약 (병렬 처리)
            from concurrent.futures import ThreadPoolExecutor
            
            def get_stock_insight(stock):
                ticker = stock['ticker']
                name = stock['name']
                query = f"{name} {ticker} 최근 전망 투자의견"
                results = self.rag_engine.retrieve(query, top_k=3)
                
                if results:
                    summary = self._summarize_insights(name, results)
                    return ticker, {
                        'name': name,
                        'summary': summary,
                        'sources_count': len(results)
                    }
                return None
            
            with ThreadPoolExecutor(max_workers=5) as executor:
                stocks = [row for _, row in top_holdings.iterrows()]
                results = list(executor.map(get_stock_insight, stocks))
                for res in results:
                    if res:
                        ticker, data = res
                        insights[ticker] = data
            
        except Exception as e:
            logger.error(f"시장 인사이트 수집 오류: {str(e)}")
        
        return insights
    
    def _summarize_insights(self, name: str, results: List[Dict]) -> str:
        """
        RAG 결과를 간단히 요약
        
        Args:
            name: 종목명
            results: RAG 검색 결과
            
        Returns:
            str: 요약
        """
        try:
            context = "\n\n".join([
                f"{r['metadata'].get('영상제목', '')}: {r['document'][:150]}..."
                for r in results[:2]
            ])
            
            prompt = f"""다음은 {name} 종목에 대한 최근 전문가 의견입니다:

{context}

위 내용을 **한 문장(30자 이내)**으로 요약하세요. 투자 방향성(긍정/부정/중립)을 명확히 하세요.

예시: "AI 수요 증가로 상승 전망", "실적 부진으로 하락 우려", "횡보 예상"
"""
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 투자 의견을 간결하게 요약하는 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=50
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"인사이트 요약 오류: {str(e)}")
            return "정보 부족"
    
    def _generate_ai_suggestions(self, balance: Dict, 
                                 market_insights: Dict,
                                 target_allocation: Optional[Dict],
                                 optimization_result: Optional[Dict] = None,
                                 simulation_result: Optional[Dict] = None) -> Dict:
        """
        AI 기반 리밸런싱 제안 생성
        """
        try:
            # 컨텍스트 구성
            context = f"""
## 현재 포트폴리오 분석

**총 평가금액**: {balance['total_value']:,.0f}원
**평균 수익률**: {balance['risk_metrics']['avg_profit_rate']:.2f}%
"""
            # 최적화 결과 추가
            if optimization_result and optimization_result.get('success'):
                opt_sharpe = optimization_result['sharpe_ratio']
                curr_sharpe = optimization_result.get('current_metrics', {}).get('sharpe_ratio', 0)
                
                context += f"""
### MPT 최적화 분석
**현재 Sharpe Ratio**: {curr_sharpe:.2f}
**최적 Sharpe Ratio**: {opt_sharpe:.2f}
**개선 가능 수익률**: {(optimization_result['returns'] * 100):.2f}% (현재대비)

### 최적 비중 제안 (Top 5)
"""
                sorted_weights = sorted(optimization_result['weights'].items(), key=lambda x: x[1], reverse=True)
                for ticker, weight in sorted_weights[:5]:
                    if weight > 0.01:
                        context += f"- {ticker}: {weight*100:.1f}%\n"

            # 시뮬레이션 결과 추가
            if simulation_result:
                context += f"""
### 리밸런싱 비용 시뮬레이션
**예상 비용 (수수료+세금)**: {simulation_result['total_cost']:,.0f}원 ({simulation_result['cost_ratio']:.2f}%)
"""

            context += f"""
### 현재 섹터별 비중
"""
            for sector, weight in balance['sector_weights'].items():
                context += f"- {sector}: {weight:.1f}%\n"
            
            context += f"\n**집중도**: 상위 5개 종목이 {balance['concentration']['top_5_weight']:.1f}% 차지\n"
            
            if balance['concentration']['is_concentrated']:
                context += "⚠️ 포트폴리오가 과도하게 집중되어 있습니다.\n"
            
            # 시장 인사이트 추가
            if market_insights:
                context += "\n### 주요 종목 전망\n"
                for ticker, insight in market_insights.items():
                    context += f"- {insight['name']}: {insight['summary']}\n"
            
            # 프롬프트
            prompt = f"""{context}

**임무**: 위 포트폴리오에 대한 리밸런싱 제안을 작성하세요.

**제안 항목**:
1. **매도 추천** (손실 종목 정리, 비중 축소)
2. **보유 유지** (현재 비중 적정)
3. **매수 추천** (비중 확대, 신규 진입)
4. **섹터 조정** (과도한 집중 해소)
5. **최적화 의견** (Sharpe Ratio 개선 방향)

**응답 형식**:
- 각 항목별로 구체적 종목명과 이유 명시
- 리밸런싱 우선순위 표시
- 리스크 관리 방안 포함

간결하고 실행 가능한 제안을 작성하세요.
"""
**손실 종목 비율**: {balance['risk_metrics']['losing_stocks_ratio']:.1f}%

### 섹터별 비중
"""
            for sector, weight in balance['sector_weights'].items():
                context += f"- {sector}: {weight:.1f}%\n"
            
            context += f"\n**집중도**: 상위 5개 종목이 {balance['concentration']['top_5_weight']:.1f}% 차지\n"
            
            if balance['concentration']['is_concentrated']:
                context += "⚠️ 포트폴리오가 과도하게 집중되어 있습니다.\n"
            
            # 시장 인사이트 추가
            if market_insights:
                context += "\n### 주요 종목 전망\n"
                for ticker, insight in market_insights.items():
                    context += f"- {insight['name']}: {insight['summary']}\n"
            
            # 프롬프트
            prompt = f"""{context}

**임무**: 위 포트폴리오에 대한 리밸런싱 제안을 작성하세요.

**제안 항목**:
1. **매도 추천** (손실 종목 정리, 비중 축소)
2. **보유 유지** (현재 비중 적정)
3. **매수 추천** (비중 확대, 신규 진입)
4. **섹터 조정** (과도한 집중 해소)

**응답 형식**:
- 각 항목별로 구체적 종목명과 이유 명시
- 리밸런싱 우선순위 표시
- 리스크 관리 방안 포함

간결하고 실행 가능한 제안을 작성하세요.
"""
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 보수적이고 신중한 포트폴리오 매니저입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500
            )
            
            suggestion_text = response.choices[0].message.content
            
            # 구조화된 제안 생성
            structured_suggestions = self._parse_suggestions(suggestion_text, balance)
            
            return {
                'full_text': suggestion_text,
                'structured': structured_suggestions
            }
            
        except Exception as e:
            logger.error(f"AI 제안 생성 오류: {str(e)}")
            return {
                'full_text': "제안 생성 중 오류가 발생했습니다.",
                'structured': {}
            }
    
    def _parse_suggestions(self, suggestion_text: str, balance: Dict) -> Dict:
        """
        AI 제안을 구조화된 형식으로 파싱
        
        Args:
            suggestion_text: AI 제안 텍스트
            balance: 포트폴리오 균형 정보
            
        Returns:
            Dict: 구조화된 제안
        """
        # 간단한 파싱 (실제로는 더 정교한 파싱 필요)
        return {
            'sell_candidates': [],  # 매도 후보
            'hold_stocks': [],      # 보유 유지
            'buy_candidates': [],   # 매수 후보
            'sector_adjustment': {} # 섹터 조정
        }


# CLI 사용 예시
if __name__ == "__main__":
    import sys
    from modules.portfolio_analyzer import PortfolioAnalyzer
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("포트폴리오 리밸런싱 제안")
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
    
    # 리밸런싱 분석
    rebalancer = PortfolioRebalancer(rag_engine)
    print("\n🔍 리밸런싱 분석 중...\n")
    
    result = rebalancer.generate_rebalancing_suggestions(portfolio_df)
    
    if result['status'] == 'success':
        # 현재 균형 출력
        print("\n" + "=" * 60)
        print("현재 포트폴리오 균형")
        print("=" * 60)
        
        balance = result['current_balance']
        print(f"\n총 평가금액: {balance['total_value']:,.0f}원")
        print(f"평균 수익률: {balance['risk_metrics']['avg_profit_rate']:.2f}%")
        
        print("\n섹터별 비중:")
        for sector, weight in balance['sector_weights'].items():
            print(f"  - {sector}: {weight:.1f}%")
        
        # 리밸런싱 제안 출력
        print("\n" + "=" * 60)
        print("리밸런싱 제안")
        print("=" * 60)
        print(f"\n{result['suggestions']['full_text']}")
        
    else:
        print(f"❌ 오류: {result.get('message', '알 수 없는 오류')}")
