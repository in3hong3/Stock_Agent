"""
포트폴리오 수학적 최적화 모듈
Modern Portfolio Theory (MPT) 기반의 Efficient Frontier 계산 및 최적 비중 산출
"""
import logging
import numpy as np
import pandas as pd
import yfinance as yf
from scipy.optimize import minimize
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class PortfolioOptimizer:
    """포트폴리오 최적화 클래스"""

    def __init__(self, risk_free_rate: float = 0.035):
        """
        초기화
        
        Args:
            risk_free_rate: 무위험 수익률 (기본값: 3.5% - 미국 국채 10년물 기준)
        """
        self.risk_free_rate = risk_free_rate

    def fetch_historical_data(self, tickers: List[str], period: str = "2y") -> pd.DataFrame:
        """
        종목별 과거 수정주가 데이터 수집
        
        Args:
            tickers: 종목 티커 리스트
            period: 데이터 수집 기간 (1y, 2y, 5y 등)
            
        Returns:
            pd.DataFrame: 수정주가 데이터프레임 (인덱스: 날짜, 컬럼: 티커)
        """
        if not tickers:
            return pd.DataFrame()
        
        try:
            logger.info(f"데이터 수집 중: {len(tickers)}개 종목, 기간: {period}")
            data = yf.download(tickers, period=period, progress=False)['Adj Close']
            
            # 단일 종목일 경우 Series를 DataFrame으로 변환
            if isinstance(data, pd.Series):
                data = data.to_frame(name=tickers[0])
            
            # 결측치 처리 (앞의 값으로 채움)
            data = data.fillna(method='ffill').dropna()
            
            return data
        except Exception as e:
            logger.error(f"데이터 수집 실패: {str(e)}")
            return pd.DataFrame()

    def calculate_metrics(self, prices: pd.DataFrame) -> Tuple[pd.Series, pd.DataFrame]:
        """
        기대 수익률과 공분산 행렬 계산
        
        Args:
            prices: 수정주가 데이터프레임
            
        Returns:
            Tuple: (연간 기대 수익률 Series, 연간 공분산 행렬 DataFrame)
        """
        # 일간 수익률 계산
        daily_returns = prices.pct_change().dropna()
        
        # 연간 기대 수익률 (일간 평균 * 252)
        expected_returns = daily_returns.mean() * 252
        
        # 연간 공분산 행렬 (일간 공분산 * 252)
        cov_matrix = daily_returns.cov() * 252
        
        return expected_returns, cov_matrix

    def portfolio_performance(self, weights: np.array, expected_returns: pd.Series, 
                            cov_matrix: pd.DataFrame) -> Tuple[float, float, float]:
        """
        주어진 비중에서의 포트폴리오 성과 계산
        
        Args:
            weights: 종목별 비중 배열
            expected_returns: 기대 수익률
            cov_matrix: 공분산 행렬
            
        Returns:
            Tuple: (수익률, 변동성, 샤프지수)
        """
        returns = np.sum(expected_returns * weights)
        volatility = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
        sharpe_ratio = (returns - self.risk_free_rate) / volatility
        
        return returns, volatility, sharpe_ratio

    def optimize_portfolio(self, prices: pd.DataFrame, 
                          objective: str = "max_sharpe") -> Dict:
        """
        포트폴리오 최적화 수행
        
        Args:
            prices: 수정주가 데이터프레임
            objective: 목표 ("max_sharpe" 또는 "min_volatility")
            
        Returns:
            Dict: 최적화 결과
        """
        expected_returns, cov_matrix = self.calculate_metrics(prices)
        num_assets = len(expected_returns)
        args = (expected_returns, cov_matrix)
        
        # 제약조건: 비중 합 = 1
        constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
        
        # 경계조건: 각 종목 비중 0~1
        bounds = tuple((0.0, 1.0) for asset in range(num_assets))
        
        # 초기값: 균등 배분
        initial_guess = num_assets * [1. / num_assets,]
        
        if objective == "max_sharpe":
            # 샤프지수 최대화 (음의 샤프지수 최소화)
            def neg_sharpe(weights, expected_returns, cov_matrix):
                returns, volatility, sharpe = self.portfolio_performance(weights, expected_returns, cov_matrix)
                return -sharpe
            
            result = minimize(neg_sharpe, initial_guess, args=args,
                            method='SLSQP', bounds=bounds, constraints=constraints)
            
        elif objective == "min_volatility":
            # 변동성 최소화
            def get_volatility(weights, expected_returns, cov_matrix):
                returns, volatility, sharpe = self.portfolio_performance(weights, expected_returns, cov_matrix)
                return volatility
            
            result = minimize(get_volatility, initial_guess, args=args,
                            method='SLSQP', bounds=bounds, constraints=constraints)
        
        else:
            raise ValueError(f"지원하지 않는 목표: {objective}")
        
        # 결과 정리
        opt_weights = result.x
        opt_returns, opt_volatility, opt_sharpe = self.portfolio_performance(
            opt_weights, expected_returns, cov_matrix
        )
        
        return {
            'weights': dict(zip(expected_returns.index, opt_weights)),
            'returns': opt_returns,
            'volatility': opt_volatility,
            'sharpe_ratio': opt_sharpe,
            'success': result.success,
            'message': result.message
        }

    def simulate_efficient_frontier(self, prices: pd.DataFrame, 
                                  num_portfolios: int = 5000) -> pd.DataFrame:
        """
        Efficient Frontier 시뮬레이션 (몬테카를로)
        
        Args:
            prices: 수정주가 데이터프레임
            num_portfolios: 시뮬레이션 횟수
            
        Returns:
            pd.DataFrame: 시뮬레이션 결과 (Returns, Volatility, Sharpe)
        """
        expected_returns, cov_matrix = self.calculate_metrics(prices)
        num_assets = len(expected_returns)
        
        results = np.zeros((3, num_portfolios))
        
        for i in range(num_portfolios):
            # 랜덤 비중 생성
            weights = np.random.random(num_assets)
            weights /= np.sum(weights)
            
            # 성과 계산
            ret, vol, sharpe = self.portfolio_performance(weights, expected_returns, cov_matrix)
            
            results[0,i] = ret
            results[1,i] = vol
            results[2,i] = sharpe
            
        return pd.DataFrame({
            'Returns': results[0],
            'Volatility': results[1],
            'Sharpe': results[2]
        })
