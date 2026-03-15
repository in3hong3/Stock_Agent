"""
포트폴리오 분석 모듈
로컬 CSV 파일로 관리하는 보유 주식을 RAG 시스템과 연동하여 분석
"""

import logging
import os
from typing import Dict, List, Optional
import pandas as pd
from core.rag_engine import RAGEngine

logger = logging.getLogger(__name__)


class PortfolioAnalyzer:
    """포트폴리오 분석기"""
    
    def __init__(self, rag_engine: RAGEngine):
        """
        초기화
        
        Args:
            rag_engine: RAG 엔진 인스턴스
        """
        self.rag_engine = rag_engine
    
    def load_portfolio_from_csv(self, file_path: str = "data/portfolio.csv") -> pd.DataFrame:
        """
        CSV 파일에서 포트폴리오 로드
        
        Args:
            file_path: 파일 경로
            
        Returns:
            pd.DataFrame: 포트폴리오 데이터프레임
        """
        try:
            if not os.path.exists(file_path):
                logger.error(f"파일을 찾을 수 없습니다: {file_path}")
                return pd.DataFrame()
            
            df = pd.read_csv(file_path)
            
            # 필수 컬럼 확인 및 기본값 처리
            required_cols = ['ticker', 'name', 'quantity', 'avg_price', 'current_price']
            for col in required_cols:
                if col not in df.columns:
                    logger.warning(f"필수 컬럼 누락: {col}. 빈 값이 생성됩니다.")
                    df[col] = 0 if 'price' in col or 'quantity' in col else ""
            
            # 계산된 컬럼 추가 (eval_amount, profit_loss, profit_rate)
            df['eval_amount'] = df['quantity'] * df['current_price']
            df['profit_loss'] = df['eval_amount'] - (df['quantity'] * df['avg_price'])
            df['profit_rate'] = (df['profit_loss'] / (df['quantity'] * df['avg_price'])) * 100
            
            return df
            
        except Exception as e:
            logger.error(f"포트폴리오 로드 중 오류: {str(e)}")
            return pd.DataFrame()
    
    def analyze_portfolio(self, portfolio_df: pd.DataFrame) -> Dict:
        """
        포트폴리오 종합 분석
        
        Args:
            portfolio_df: 분석할 포트폴리오 데이터프레임
            
        Returns:
            Dict: 분석 결과
        """
        try:
            if portfolio_df is None or portfolio_df.empty:
                logger.warning("포트폴리오가 비어있습니다")
                return {
                    'status': 'empty',
                    'message': '보유 주식이 없습니다'
                }
            
            # 2. 각 종목별 분석 (병렬 처리로 속도 개선)
            from concurrent.futures import ThreadPoolExecutor
            
            stock_analyses = []
            with ThreadPoolExecutor(max_workers=5) as executor:
                # iterrows() 대신 데이터프레임의 행들을 리스트로 전달
                stocks = [row for _, row in portfolio_df.iterrows()]
                # map을 사용하여 병렬 실행
                results = list(executor.map(self._analyze_single_stock, stocks))
                stock_analyses = results
            
            # 3. 포트폴리오 전체 요약
            summary = self._generate_portfolio_summary(portfolio_df, stock_analyses)
            
            return {
                'status': 'success',
                'portfolio': portfolio_df.to_dict('records'),
                'stock_analyses': stock_analyses,
                'summary': summary
            }
            
        except Exception as e:
            logger.error(f"포트폴리오 분석 중 오류: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def _analyze_single_stock(self, stock: pd.Series) -> Dict:
        """
        개별 종목 분석
        
        Args:
            stock: 종목 정보 (Series)
            
        Returns:
            Dict: 분석 결과
        """
        try:
            ticker = stock['ticker']
            name = stock['name']
            
            # RAG 시스템에서 해당 종목 관련 정보 검색
            query = f"{name} {ticker} 투자 의견 전망 분석"
            rag_results = self.rag_engine.retrieve(query, top_k=5)
            
            # AI 피드백 생성
            feedback = self._generate_ai_feedback(stock, rag_results)
            
            return {
                'ticker': ticker,
                'name': name,
                'current_info': {
                    'quantity': stock['quantity'],
                    'avg_price': stock['avg_price'],
                    'current_price': stock['current_price'],
                    'current_price_krw': stock.get('current_price_krw', stock['current_price']),
                    'profit_loss': stock['profit_loss'],
                    'profit_rate': stock['profit_rate']
                },
                'rag_insights': rag_results,
                'ai_feedback': feedback
            }
            
        except Exception as e:
            logger.error(f"종목 분석 중 오류 ({stock.get('name', 'Unknown')}): {str(e)}")
            return {
                'ticker': stock.get('ticker', ''),
                'name': stock.get('name', ''),
                'error': str(e)
            }
    
    def _generate_ai_feedback(self, stock: pd.Series, rag_results: List[Dict]) -> str:
        """
        AI 피드백 생성
        
        Args:
            stock: 종목 정보
            rag_results: RAG 검색 결과
            
        Returns:
            str: AI 피드백
        """
        try:
            from openai import OpenAI
            import os
            
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            
            # RAG 결과를 컨텍스트로 정리
            context = "\n\n".join([
                f"[{i+1}] {result.get('summary', result.get('content', ''))}"
                for i, result in enumerate(rag_results[:3])
            ])
            
            # 프롬프트 생성
            prompt = f"""
당신은 전문 주식 애널리스트입니다. 다음 보유 주식에 대한 투자 피드백을 제공해주세요.

## 보유 종목 정보
- 종목명: {stock['name']} ({stock['ticker']})
- 보유 수량: {stock['quantity']:,}주
- 평균 매수가: {stock['avg_price']:,.0f} KRW
- 현재가: {stock.get('current_price_krw', stock['current_price']):,.0f} KRW (원화 환산가)
- 평가 손익: {stock['profit_loss']:,.0f} KRW ({stock['profit_rate']:.2f}%)

## 최근 시장 분석 (YouTube 전문가 의견)
{context}

## 요청사항
위 정보를 바탕으로 다음 내용을 포함한 투자 피드백을 작성해주세요:
1. 현재 포지션 평가 (수익률 및 시장 상황 고려)
2. 최근 전문가 의견 요약
3. 향후 전망 및 추천 액션 (보유/매도/추가매수)
4. 주의사항 및 리스크

간결하고 명확하게 작성해주세요.
"""
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 보수적이고 신중한 주식 투자 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"AI 피드백 생성 중 오류: {str(e)}")
            return "AI 피드백 생성 중 오류가 발생했습니다."
    
    def _generate_portfolio_summary(self, portfolio_df: pd.DataFrame, 
                                   stock_analyses: List[Dict]) -> Dict:
        """
        포트폴리오 전체 요약
        
        Args:
            portfolio_df: 포트폴리오 데이터프레임
            stock_analyses: 개별 종목 분석 결과
            
        Returns:
            Dict: 요약 정보
        """
        try:
            total_eval = portfolio_df['eval_amount'].sum()
            total_purchase = (portfolio_df['quantity'] * portfolio_df['avg_price']).sum()
            total_profit = portfolio_df['profit_loss'].sum()
            avg_profit_rate = (total_profit / total_purchase) * 100 if total_purchase > 0 else 0
            
            # 수익률 상위/하위 종목
            top_performer = portfolio_df.loc[portfolio_df['profit_rate'].idxmax()]
            worst_performer = portfolio_df.loc[portfolio_df['profit_rate'].idxmin()]
            
            return {
                'total_stocks': len(portfolio_df),
                'total_evaluation': total_eval,
                'total_profit_loss': total_profit,
                'average_profit_rate': avg_profit_rate,
                'top_performer': {
                    'name': top_performer['name'],
                    'profit_rate': top_performer['profit_rate']
                },
                'worst_performer': {
                    'name': worst_performer['name'],
                    'profit_rate': worst_performer['profit_rate']
                },
                'profitable_stocks': len(portfolio_df[portfolio_df['profit_loss'] > 0]),
                'losing_stocks': len(portfolio_df[portfolio_df['profit_loss'] < 0])
            }
            
        except Exception as e:
            logger.error(f"포트폴리오 요약 생성 중 오류: {str(e)}")
            return {}


# 사용 예시
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # RAG 엔진 초기화
    rag_engine = RAGEngine()
    
    # 분석기 생성
    analyzer = PortfolioAnalyzer(rag_engine)
    
    # 포트폴리오 로드 및 분석
    df = analyzer.load_portfolio_from_csv("data/portfolio.csv")
    if not df.empty:
        result = analyzer.analyze_portfolio(df)
        print(result)
