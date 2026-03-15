"""
주가 추적 모듈
yfinance를 사용하여 종목의 일별 주가 데이터를 수집합니다.
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


class StockTracker:
    """종목 주가 추적 클래스"""
    
    @staticmethod
    def get_historical_prices(ticker, start_date, end_date=None):
        """
        특정 종목의 일별 주가 데이터 조회
        Args:
            ticker: 티커 심볼 (예: "005930.KS", "AAPL", "BTC-USD")
            start_date: 시작일 (str 또는 datetime, "2026-01-01")
            end_date: 종료일 (None이면 현재)
        Returns:
            DataFrame: 일별 주가 데이터 (날짜, 종가, 전일대비, 등락률, 거래량)
        """
        if end_date is None:
            end_date = datetime.now()
        
        # 문자열을 datetime으로 변환
        if isinstance(start_date, str):
            start_date = pd.to_datetime(start_date)
        if isinstance(end_date, str):
            end_date = pd.to_datetime(end_date)
        
        try:
            # yfinance로 데이터 가져오기
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date, end=end_date)
            
            if hist.empty:
                print(f"  No data for {ticker}")
                return pd.DataFrame()
            
            # 필요한 컬럼만 선택
            df = pd.DataFrame({
                '날짜': hist.index,
                '종가': hist['Close'],
                '거래량': hist['Volume']
            })
            
            # 전일대비 및 등락률 계산
            df['전일대비'] = df['종가'].diff()
            df['등락률(%)'] = (df['전일대비'] / df['종가'].shift(1) * 100).round(2)
            
            # 첫 행은 전일대비가 없으므로 0으로 설정
            df.loc[df.index[0], '전일대비'] = 0
            df.loc[df.index[0], '등락률(%)'] = 0
            
            # 반올림
            df['종가'] = df['종가'].round(2)
            df['전일대비'] = df['전일대비'].round(2)
            
            return df
            
        except Exception as e:
            print(f"  Error fetching data for {ticker}: {e}")
            return pd.DataFrame()
    
    @staticmethod
    def calculate_returns(prices_df, reference_date=None):
        """
        수익률 계산
        Args:
            prices_df: get_historical_prices()로 얻은 DataFrame
            reference_date: 기준일 (None이면 첫 날)
        Returns:
            DataFrame: 누적 수익률이 추가된 DataFrame
        """
        if prices_df.empty:
            return prices_df
        
        df = prices_df.copy()
        
        # 기준일 설정
        if reference_date is None:
            reference_price = df.iloc[0]['종가']
        else:
            ref_row = df[df['날짜'] == reference_date]
            if ref_row.empty:
                reference_price = df.iloc[0]['종가']
            else:
                reference_price = ref_row.iloc[0]['종가']
        
        # 누적 수익률 계산
        df['누적수익률(%)'] = ((df['종가'] - reference_price) / reference_price * 100).round(2)
        
        return df
    
    @staticmethod
    def track_mentioned_stocks(stocks_list, video_upload_date):
        """
        영상에서 언급된 종목들의 주가 추적
        Args:
            stocks_list: 종목 정보 리스트 [{'종목명': ..., 'ticker': ..., 'market': ...}, ...]
            video_upload_date: 영상 업로드일 (기준일)
        Returns:
            dict: {ticker: DataFrame} 형태의 주가 데이터
        """
        results = {}
        
        for stock in stocks_list:
            ticker = stock['ticker']
            stock_name = stock['종목명']
            
            print(f"  Tracking {stock_name} ({ticker})...")
            
            # 영상 업로드일부터 현재까지 주가 조회
            prices_df = StockTracker.get_historical_prices(
                ticker, 
                start_date=video_upload_date
            )
            
            if not prices_df.empty:
                # 수익률 계산 (영상 업로드일 기준)
                prices_df = StockTracker.calculate_returns(prices_df, video_upload_date)
                
                # 종목명 추가
                prices_df['종목명'] = stock_name
                prices_df['티커'] = ticker
                
                results[ticker] = prices_df
            else:
                print(f"    No price data available for {ticker}")
        
        return results


if __name__ == "__main__":
    # 테스트 코드
    tracker = StockTracker()
    
    # 삼성전자 주가 조회
    print("=== 삼성전자 주가 (2026-01-01 ~ 현재) ===")
    prices = tracker.get_historical_prices("005930.KS", "2026-01-01")
    
    if not prices.empty:
        print(prices.head())
        
        # 수익률 계산
        prices_with_returns = tracker.calculate_returns(prices)
        print("\n=== 수익률 포함 ===")
        print(prices_with_returns.head())
    
    # 여러 종목 추적
    print("\n=== 여러 종목 추적 ===")
    test_stocks = [
        {'종목명': '삼성전자', 'ticker': '005930.KS', 'market': 'KR'},
        {'종목명': 'NVIDIA', 'ticker': 'NVDA', 'market': 'US'}
    ]
    
    results = tracker.track_mentioned_stocks(test_stocks, "2026-01-15")
    
    for ticker, df in results.items():
        print(f"\n{ticker}:")
        print(df.head())
