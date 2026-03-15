"""
섹터 자동 분류 모듈
yfinance를 사용하여 종목의 섹터 정보를 자동으로 가져옴
"""
import yfinance as yf
import pandas as pd
import logging
from typing import Dict, Optional
import time

logger = logging.getLogger(__name__)


class SectorClassifier:
    """종목 섹터 자동 분류 클래스"""
    
    def __init__(self):
        """초기화"""
        self.sector_cache = {}  # 섹터 정보 캐시
        self.industry_cache = {}  # 산업 정보 캐시
    
    def get_sector(self, ticker: str) -> str:
        """
        종목의 섹터 정보 조회
        
        Args:
            ticker: 종목 티커
            
        Returns:
            str: 섹터명 (실패 시 'Unknown')
        """
        # 캐시 확인
        if ticker in self.sector_cache:
            return self.sector_cache[ticker]
        
        try:
            # 특수 케이스 처리
            if ticker == 'USD':
                sector = 'Cash'
            elif ticker.endswith('.KS') or ticker.endswith('.KQ'):
                # 한국 주식
                sector = self._get_korean_sector(ticker)
            elif ticker.endswith('.T'):
                # 일본 주식
                sector = self._get_japanese_sector(ticker)
            else:
                # 미국 주식 (yfinance)
                stock = yf.Ticker(ticker)
                info = stock.info
                sector = info.get('sector', 'Unknown')
            
            # 캐시 저장
            self.sector_cache[ticker] = sector
            logger.info(f"섹터 조회 성공: {ticker} → {sector}")
            return sector
            
        except Exception as e:
            logger.error(f"섹터 조회 오류 ({ticker}): {str(e)}")
            self.sector_cache[ticker] = 'Unknown'
            return 'Unknown'
    
    def get_industry(self, ticker: str) -> str:
        """
        종목의 산업 정보 조회
        
        Args:
            ticker: 종목 티커
            
        Returns:
            str: 산업명 (실패 시 'Unknown')
        """
        # 캐시 확인
        if ticker in self.industry_cache:
            return self.industry_cache[ticker]
        
        try:
            if ticker == 'USD':
                industry = 'Cash'
            elif ticker.endswith('.KS') or ticker.endswith('.KQ'):
                industry = self._get_korean_industry(ticker)
            elif ticker.endswith('.T'):
                industry = self._get_japanese_industry(ticker)
            else:
                stock = yf.Ticker(ticker)
                info = stock.info
                industry = info.get('industry', 'Unknown')
            
            self.industry_cache[ticker] = industry
            return industry
            
        except Exception as e:
            logger.error(f"산업 조회 오류 ({ticker}): {str(e)}")
            self.industry_cache[ticker] = 'Unknown'
            return 'Unknown'
    
    def _get_korean_sector(self, ticker: str) -> str:
        """한국 주식 섹터 조회 (하드코딩 + yfinance)"""
        # 하드코딩된 매핑 (ETF 등)
        korean_sector_map = {
            '445290.KS': 'ETF - Robotics',  # KODEX 로봇액티브
        }
        
        if ticker in korean_sector_map:
            return korean_sector_map[ticker]
        
        # yfinance 시도
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            return info.get('sector', 'Korea Stock')
        except:
            return 'Korea Stock'
    
    def _get_japanese_sector(self, ticker: str) -> str:
        """일본 주식 섹터 조회 (하드코딩 + yfinance)"""
        # 하드코딩된 매핑
        japanese_sector_map = {
            '9984.T': 'Communication Services',  # 소프트뱅크
            '1497.T': 'ETF - Japan Equity',  # 노무라 TOPIX ETF
        }
        
        if ticker in japanese_sector_map:
            return japanese_sector_map[ticker]
        
        # yfinance 시도
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            return info.get('sector', 'Japan Stock')
        except:
            return 'Japan Stock'
    
    def _get_korean_industry(self, ticker: str) -> str:
        """한국 주식 산업 조회"""
        korean_industry_map = {
            '445290.KS': 'Robotics & AI ETF',
        }
        return korean_industry_map.get(ticker, 'Korea Stock')
    
    def _get_japanese_industry(self, ticker: str) -> str:
        """일본 주식 산업 조회"""
        japanese_industry_map = {
            '9984.T': 'Telecom & Conglomerate',
            '1497.T': 'Japan Index ETF',
        }
        return japanese_industry_map.get(ticker, 'Japan Stock')
    
    def classify_portfolio(self, portfolio_df: pd.DataFrame, 
                          delay_seconds: float = 0.3) -> pd.DataFrame:
        """
        포트폴리오 전체 섹터 분류
        
        Args:
            portfolio_df: 포트폴리오 데이터프레임
            delay_seconds: API 호출 간 지연 시간
            
        Returns:
            pd.DataFrame: 섹터/산업 정보가 추가된 데이터프레임
        """
        if portfolio_df is None or portfolio_df.empty:
            return portfolio_df
        
        df = portfolio_df.copy()
        
        # 섹터/산업 컬럼 추가
        df['sector'] = ''
        df['industry'] = ''
        
        logger.info(f"섹터 분류 시작: {len(df)}개 종목")
        
        for idx, row in df.iterrows():
            ticker = row['ticker']
            
            # 캐시 확인 (캐시에 없으면 API 호출 후 대기)
            needs_delay = ticker not in self.sector_cache and ticker not in self.industry_cache
            
            # 섹터 조회
            sector = self.get_sector(ticker)
            df.at[idx, 'sector'] = sector
            
            # 산업 조회
            industry = self.get_industry(ticker)
            df.at[idx, 'industry'] = industry
            
            # API 호출이 일어난 경우에만 지연 시간 적용 (API 제한 방지)
            if needs_delay and idx < len(df) - 1:
                time.sleep(delay_seconds)
        
        logger.info("섹터 분류 완료")
        
        return df
    
    def get_sector_summary(self, portfolio_df: pd.DataFrame) -> Dict:
        """
        섹터별 요약 정보
        
        Args:
            portfolio_df: 섹터 정보가 포함된 포트폴리오 데이터프레임
            
        Returns:
            Dict: 섹터별 요약
        """
        if 'sector' not in portfolio_df.columns:
            return {}
        
        # 섹터별 평가금액 합계
        sector_values = portfolio_df.groupby('sector')['eval_amount'].sum().to_dict()
        
        # 총 평가금액
        total_value = portfolio_df['eval_amount'].sum()
        
        # 섹터별 비중 계산
        sector_weights = {
            sector: (value / total_value * 100) if total_value > 0 else 0
            for sector, value in sector_values.items()
        }
        
        # 섹터별 종목 수
        sector_counts = portfolio_df.groupby('sector').size().to_dict()
        
        # 섹터별 평균 수익률
        sector_profit_rates = portfolio_df.groupby('sector')['profit_rate'].mean().to_dict()
        
        return {
            'sector_values': sector_values,
            'sector_weights': sector_weights,
            'sector_counts': sector_counts,
            'sector_profit_rates': sector_profit_rates,
            'total_value': total_value
        }


# CLI 사용 예시
if __name__ == "__main__":
    import sys
    import os
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 포트폴리오 로드
    portfolio_path = "data/portfolio.csv"
    
    if not os.path.exists(portfolio_path):
        print(f"❌ 파일을 찾을 수 없습니다: {portfolio_path}")
        sys.exit(1)
    
    print("=" * 60)
    print("포트폴리오 섹터 자동 분류")
    print("=" * 60)
    
    # 포트폴리오 로드
    df = pd.read_csv(portfolio_path)
    print(f"\n📊 로드된 종목: {len(df)}개")
    
    # 계산된 컬럼 추가
    df['eval_amount'] = df['quantity'] * df['current_price']
    df['profit_loss'] = df['eval_amount'] - (df['quantity'] * df['avg_price'])
    df['profit_rate'] = (df['profit_loss'] / (df['quantity'] * df['avg_price'])) * 100
    
    # 섹터 분류
    classifier = SectorClassifier()
    print("\n🔍 섹터 분류 중...\n")
    
    classified_df = classifier.classify_portfolio(df, delay_seconds=0.3)
    
    # 결과 출력
    print("\n" + "=" * 60)
    print("섹터 분류 결과")
    print("=" * 60)
    
    for idx, row in classified_df.iterrows():
        print(f"\n{row['name']} ({row['ticker']})")
        print(f"  섹터: {row['sector']}")
        print(f"  산업: {row['industry']}")
    
    # 섹터별 요약
    summary = classifier.get_sector_summary(classified_df)
    
    print("\n" + "=" * 60)
    print("섹터별 요약")
    print("=" * 60)
    
    for sector, weight in sorted(summary['sector_weights'].items(), key=lambda x: x[1], reverse=True):
        count = summary['sector_counts'][sector]
        value = summary['sector_values'][sector]
        avg_profit = summary['sector_profit_rates'][sector]
        
        print(f"\n{sector}")
        print(f"  비중: {weight:.1f}%")
        print(f"  종목 수: {count}개")
        print(f"  평가금액: ${value:,.0f}")
        print(f"  평균 수익률: {avg_profit:.2f}%")
