"""
실시간 주가 업데이트 모듈
yfinance를 사용하여 포트폴리오의 현재가를 자동으로 업데이트
"""
import os
import yfinance as yf
import pandas as pd
import logging
from typing import Dict, List, Optional
from datetime import datetime
import time

logger = logging.getLogger(__name__)


class PriceUpdater:
    """주가 실시간 업데이트 클래스"""
    
    def __init__(self):
        """초기화"""
        self.exchange_rate_krw_usd = None
        self.last_update_time = None
    
    def _normalize_ticker(self, ticker: str) -> str:
        """
        티커를 yfinance 형식으로 변환
        
        Args:
            ticker: 원본 티커
            
        Returns:
            str: 정규화된 티커
        """
        # 한국 주식 (KS, KQ)
        if ticker.endswith('.KS') or ticker.endswith('.KQ'):
            return ticker
        
        # 일본 주식 (.T)
        if ticker.endswith('.T'):
            return ticker
        
        # 미국 주식 (기본)
        if ticker == 'USD':
            return 'KRW=X'  # 원/달러 환율
        
        return ticker
    
    def get_current_price(self, ticker: str) -> Optional[float]:
        """
        단일 종목의 현재가 조회
        
        Args:
            ticker: 종목 티커
            
        Returns:
            float: 현재가 (실패 시 None)
        """
        try:
            normalized_ticker = self._normalize_ticker(ticker)
            
            # USD (외화예수금)는 환율 반환
            if ticker == 'USD':
                return self.get_exchange_rate()
            
            # yfinance로 현재가 조회
            stock = yf.Ticker(normalized_ticker)
            
            # 실시간 가격 시도 (fast_info)
            try:
                current_price = stock.fast_info.get('lastPrice')
                if current_price and current_price > 0:
                    return float(current_price)
            except:
                pass
            
            # 대체: history 사용
            hist = stock.history(period='1d', interval='1m')
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                return float(current_price)
            
            # 대체: info 사용
            info = stock.info
            current_price = info.get('currentPrice') or info.get('regularMarketPrice')
            if current_price:
                return float(current_price)
            
            logger.warning(f"가격 조회 실패: {ticker}")
            return None
            
        except Exception as e:
            logger.error(f"가격 조회 오류 ({ticker}): {str(e)}")
            return None
    
    def get_exchange_rate(self, base: str = 'USD') -> Optional[float]:
        """
        환율 조회 (기본: USD/KRW)
        """
        try:
            cache_key = f"rate_{base}"
            if not hasattr(self, '_rates'):
                self._rates = {}
            if not hasattr(self, '_rates_time'):
                self._rates_time = {}
                
            if cache_key in self._rates and cache_key in self._rates_time:
                elapsed = (datetime.now() - self._rates_time[cache_key]).seconds
                if elapsed < 3600:
                    return self._rates[cache_key]
            
            ticker = 'KRW=X' if base == 'USD' else 'JPYKRW=X'
            rate_ticker = yf.Ticker(ticker)
            hist = rate_ticker.history(period='1d')
            
            if not hist.empty:
                rate = hist['Close'].iloc[-1]
                self._rates[cache_key] = float(rate)
                self._rates_time[cache_key] = datetime.now()
                return self._rates[cache_key]
            
            return None
        except Exception as e:
            logger.error(f"환율 조회 오류 ({base}): {str(e)}")
            return None

    def _get_ticker_currency(self, ticker: str) -> str:
        """티커의 통화 감지"""
        if ticker.endswith('.KS') or ticker.endswith('.KQ'):
            return 'KRW'
        if ticker.endswith('.T'):
            return 'JPY'
        if ticker == 'USD':
            return 'USD'
        return 'USD'
    
    def update_portfolio_prices(self, portfolio_df: pd.DataFrame, 
                                delay_seconds: float = 0.5) -> pd.DataFrame:
        """
        포트폴리오 전체 가격 업데이트 및 원화 환산
        """
        if portfolio_df is None or portfolio_df.empty:
            return portfolio_df
        
        updated_df = portfolio_df.copy()
        
        # 환율 미리 가져오기
        usd_rate = self.get_exchange_rate('USD') or 1450.0
        jpy_rate = self.get_exchange_rate('JPY') or 9.5
        
        # 배치 가격 조회
        tickers = updated_df['ticker'].tolist()
        batch_prices = self.get_batch_prices(tickers)
        
        for idx, row in updated_df.iterrows():
            ticker = row['ticker']
            currency = self._get_ticker_currency(ticker)
            
            current_price = batch_prices.get(ticker)
            if current_price is None:
                current_price = self.get_current_price(ticker)
                if idx < len(updated_df) - 1:
                    time.sleep(delay_seconds)
            
            if current_price is not None:
                updated_df.at[idx, 'current_price'] = current_price
                
                # 원화 환산가 계산
                if ticker == 'USD':
                    current_price_krw = current_price # USD 티커 자체가 환율이므로 그대로 사용
                elif currency == 'USD':
                    current_price_krw = current_price * usd_rate
                elif currency == 'JPY':
                    current_price_krw = current_price * jpy_rate
                else:
                    current_price_krw = current_price
                
                updated_df.at[idx, 'current_price_krw'] = current_price_krw
            
        # 모든 계산을 KRW 기준으로 수행 (avg_price가 KRW라고 가정)
        updated_df['eval_amount'] = updated_df['quantity'] * updated_df.get('current_price_krw', updated_df['current_price'])
        updated_df['profit_loss'] = updated_df['eval_amount'] - (updated_df['quantity'] * updated_df['avg_price'])
        
        mask = (updated_df['quantity'] * updated_df['avg_price']) > 0
        updated_df.loc[mask, 'profit_rate'] = (updated_df.loc[mask, 'profit_loss'] / (updated_df.loc[mask, 'quantity'] * updated_df.loc[mask, 'avg_price'])) * 100
        updated_df['profit_rate'] = updated_df['profit_rate'].fillna(0)
        
        return updated_df
    
    def save_portfolio(self, portfolio_df: pd.DataFrame, file_path: str = "data/portfolio.csv"):
        """
        업데이트된 포트폴리오 저장
        
        Args:
            portfolio_df: 포트폴리오 데이터프레임
            file_path: 저장 경로
        """
        try:
            # 저장할 컬럼만 선택
            save_columns = ['ticker', 'name', 'quantity', 'avg_price', 'current_price']
            save_df = portfolio_df[save_columns]
            
            # CSV 저장
            save_df.to_csv(file_path, index=False, encoding='utf-8-sig')
            logger.info(f"포트폴리오 저장 완료: {file_path}")
            
        except Exception as e:
            logger.error(f"포트폴리오 저장 오류: {str(e)}")
    
    def get_watchlist_data(self, tickers: List[str]) -> pd.DataFrame:
        """
        관심 종목에 대한 실시간 정보 조회 (가격, 등락률)
        """
        results = []
        try:
            normalized_tickers = [self._normalize_ticker(t) for t in tickers]
            # 최근 2일 데이터를 가져와서 전일 종가 대비 등락 계산
            data = yf.download(tickers=normalized_tickers, period='2d', interval='1d', group_by='ticker', progress=False)
            
            for orig, norm in zip(tickers, normalized_tickers):
                try:
                    if len(tickers) == 1:
                        ticker_data = data
                    else:
                        ticker_data = data[norm]
                    
                    if not ticker_data.empty and len(ticker_data) >= 1:
                        current_price = ticker_data['Close'].iloc[-1]
                        
                        # 전일 종가가 있는 경우 등락률 계산
                        if len(ticker_data) >= 2:
                            prev_close = ticker_data['Close'].iloc[-2]
                            change_pct = ((current_price - prev_close) / prev_close) * 100
                        else:
                            # fast_info 등을 통해 시도
                            stock = yf.Ticker(norm)
                            prev_close = stock.info.get('regularMarketPreviousClose')
                            if prev_close:
                                change_pct = ((current_price - prev_close) / prev_close) * 100
                            else:
                                change_pct = 0.0
                                
                        results.append({
                            "종목": orig,
                            "현재가": current_price,
                            "등락": f"{change_pct:+.2f}%"
                        })
                except:
                    results.append({"종목": orig, "현재가": 0.0, "등락": "0.00%"})
        except Exception as e:
            logger.error(f"Watchlist 조회 오류: {e}")
            
        return pd.DataFrame(results)

    def get_batch_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        여러 종목의 가격을 한 번에 조회 (더 빠름)
        
        Args:
            tickers: 티커 리스트
            
        Returns:
            Dict[str, float]: {ticker: price}
        """
        prices = {}
        
        try:
            # 티커 정규화
            normalized_tickers = [self._normalize_ticker(t) for t in tickers if t != 'USD']
            
            # 배치 조회 — interval='1m'은 휴장/장외에 빈 결과를 자주 줘서 5d 일봉 사용
            if normalized_tickers:
                data = yf.download(
                    tickers=normalized_tickers,
                    period='5d',
                    interval='1d',
                    group_by='ticker',
                    progress=False
                )
                
                # 단일 티커인 경우
                if len(normalized_tickers) == 1:
                    if not data.empty:
                        prices[tickers[0]] = float(data['Close'].iloc[-1])
                else:
                    # 여러 티커인 경우
                    for original_ticker, normalized_ticker in zip(tickers, normalized_tickers):
                        try:
                            if normalized_ticker in data.columns.levels[0]:
                                ticker_data = data[normalized_ticker]
                                if not ticker_data.empty:
                                    prices[original_ticker] = float(ticker_data['Close'].iloc[-1])
                        except:
                            pass
            
            # USD 환율 추가
            if 'USD' in tickers:
                exchange_rate = self.get_exchange_rate()
                if exchange_rate:
                    prices['USD'] = exchange_rate
            
        except Exception as e:
            logger.error(f"배치 가격 조회 오류: {str(e)}")
        
        return prices


def refresh_portfolio_from_cache(user_id: str = None) -> Dict[str, any]:
    """사용자 포트폴리오 CSV의 current_price를 market_cache 종가로 갱신/저장.
    추가 yfinance 호출 없이(캐시 우선) 새벽 cron이 호출 → 버튼 없이도 현재가가 최신 유지.
    current_price 컬럼만 건드리고 ticker/quantity/avg_price는 보존(사용자 편집 보호)."""
    from utils.user_data import portfolio_path
    from core.services.market_cache import get_history

    path = portfolio_path(user_id)
    if not os.path.exists(path):
        return {"user": user_id, "skipped": "포트폴리오 없음"}

    try:
        df = pd.read_csv(path)
    except Exception as e:
        return {"user": user_id, "error": str(e)}

    if "current_price" not in df.columns or "ticker" not in df.columns:
        return {"user": user_id, "skipped": "컬럼 없음"}

    from core.services.market_cache import get_info

    updated, fixed = 0, []
    for idx, row in df.iterrows():
        ticker = str(row.get("ticker", "")).strip().upper()
        if not ticker or ticker in ("USD", "NAN", "NONE"):  # 빈 행(NaN) 스킵
            continue
        # 종목명이 비어있으면 캐시된 info에서 회사명 채우기
        _nm = str(row.get("name", "") or "").strip()
        if "name" in df.columns and (not _nm or _nm.lower() in ("nan", "none")):
            try:
                info = get_info(ticker)
                nm = info.get("shortName") or info.get("longName")
                if nm:
                    df.at[idx, "name"] = nm
            except Exception:
                pass
        try:
            hist = get_history(ticker, "5d")
            if hist is None or hist.empty:
                continue
            real = round(float(hist["Close"].iloc[-1]), 2)
            old = float(row.get("current_price", 0) or 0)
            if real > 0:
                df.at[idx, "current_price"] = real
                updated += 1
                if old > 0 and abs(real / old - 1) > 0.05:  # 5%↑ 어긋났던 것 기록
                    fixed.append(f"{ticker} {old:,.2f}→{real:,.2f}")
        except Exception:
            continue

    try:
        df.to_csv(path, index=False, encoding="utf-8-sig")
    except Exception as e:
        return {"user": user_id, "error": f"저장 실패: {e}"}

    return {"user": user_id, "updated": updated, "fixed": fixed}


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
    print("포트폴리오 가격 업데이트")
    print("=" * 60)
    
    # 포트폴리오 로드
    df = pd.read_csv(portfolio_path)
    print(f"\n📊 로드된 종목: {len(df)}개")
    
    # 가격 업데이트
    updater = PriceUpdater()
    print("\n🔄 가격 업데이트 중...\n")
    
    updated_df = updater.update_portfolio_prices(df, delay_seconds=0.3)
    
    # 변경 사항 표시
    print("\n" + "=" * 60)
    print("업데이트 결과")
    print("=" * 60)
    
    for idx, row in updated_df.iterrows():
        old_price = df.at[idx, 'current_price']
        new_price = row['current_price']
        change = ((new_price - old_price) / old_price) * 100 if old_price > 0 else 0
        
        print(f"\n{row['name']} ({row['ticker']})")
        print(f"  이전: {old_price:,.2f} → 현재: {new_price:,.2f} ({change:+.2f}%)")
        print(f"  수익률: {row['profit_rate']:.2f}%")
    
    # 저장 여부 확인
    save = input("\n💾 업데이트된 가격을 저장하시겠습니까? (y/n): ")
    
    if save.lower() == 'y':
        updater.save_portfolio(updated_df, portfolio_path)
        print("✅ 저장 완료!")
    else:
        print("❌ 저장 취소")
