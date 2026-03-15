"""
기술적 분석 에이전트 (Technical Analyst Agent)
yfinance를 활용한 차트 지표 분석 및 매매 타이밍 제안
"""
from typing import Dict, Any, Optional
from agents.base_agent import BaseAgent
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from openai import OpenAI
import os


class TechnicalAgent(BaseAgent):
    """기술적 분석 에이전트"""
    
    def __init__(self, agent_id: str = "technical_analyst", 
                 name: str = "기술분석관", 
                 description: str = "차트 지표 분석 및 매매 타이밍 제안", 
                 **kwargs):
        super().__init__(agent_id, name, description, **kwargs)
        
        # OpenAI 클라이언트 초기화
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            self.openai_client = OpenAI(api_key=api_key)
        else:
            self.openai_client = None
    
    def calculate_indicators(self, ticker: str, period: str = "6mo") -> Dict[str, Any]:
        """
        기술적 지표 계산
        
        Args:
            ticker: 종목 티커
            period: 데이터 기간 (1mo, 3mo, 6mo, 1y, 2y, 5y, max)
            
        Returns:
            dict: 계산된 지표들
        """
        try:
            # yfinance로 데이터 다운로드
            stock = yf.Ticker(ticker)
            df = stock.history(period=period)
            
            if df.empty:
                return {"error": f"데이터를 가져올 수 없습니다: {ticker}"}
            
            # 현재가
            current_price = df['Close'].iloc[-1]
            
            # 1. 이동평균선 (Moving Averages)
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df['MA50'] = df['Close'].rolling(window=50).mean()
            df['MA200'] = df['Close'].rolling(window=200).mean()
            
            ma20 = df['MA20'].iloc[-1]
            ma50 = df['MA50'].iloc[-1]
            ma200 = df['MA200'].iloc[-1] if len(df) >= 200 else None
            
            # 2. RSI (Relative Strength Index)
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))
            rsi = df['RSI'].iloc[-1]
            
            # 3. MACD (Moving Average Convergence Divergence)
            exp1 = df['Close'].ewm(span=12, adjust=False).mean()
            exp2 = df['Close'].ewm(span=26, adjust=False).mean()
            df['MACD'] = exp1 - exp2
            df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
            df['MACD_Histogram'] = df['MACD'] - df['Signal']
            
            macd = df['MACD'].iloc[-1]
            signal = df['Signal'].iloc[-1]
            histogram = df['MACD_Histogram'].iloc[-1]
            
            # 4. Bollinger Bands
            df['BB_Middle'] = df['Close'].rolling(window=20).mean()
            df['BB_Std'] = df['Close'].rolling(window=20).std()
            df['BB_Upper'] = df['BB_Middle'] + (df['BB_Std'] * 2)
            df['BB_Lower'] = df['BB_Middle'] - (df['BB_Std'] * 2)
            
            bb_upper = df['BB_Upper'].iloc[-1]
            bb_middle = df['BB_Middle'].iloc[-1]
            bb_lower = df['BB_Lower'].iloc[-1]
            bb_position = (current_price - bb_lower) / (bb_upper - bb_lower) * 100
            
            # 5. 거래량 분석
            avg_volume = df['Volume'].rolling(window=20).mean().iloc[-1]
            current_volume = df['Volume'].iloc[-1]
            volume_ratio = (current_volume / avg_volume) * 100
            
            # 6. 가격 변동성
            volatility = df['Close'].pct_change().std() * np.sqrt(252) * 100  # 연간 변동성
            
            # 7. 추세 판단
            trend = self._determine_trend(current_price, ma20, ma50, ma200)
            
            # 8. 최근 가격 변동
            price_change_1d = ((current_price - df['Close'].iloc[-2]) / df['Close'].iloc[-2]) * 100
            price_change_5d = ((current_price - df['Close'].iloc[-6]) / df['Close'].iloc[-6]) * 100 if len(df) >= 6 else None
            price_change_20d = ((current_price - df['Close'].iloc[-21]) / df['Close'].iloc[-21]) * 100 if len(df) >= 21 else None
            
            return {
                "ticker": ticker,
                "current_price": round(current_price, 2),
                "date": df.index[-1].strftime("%Y-%m-%d"),
                
                # 이동평균선
                "ma20": round(ma20, 2),
                "ma50": round(ma50, 2),
                "ma200": round(ma200, 2) if ma200 else None,
                
                # RSI
                "rsi": round(rsi, 2),
                "rsi_signal": self._interpret_rsi(rsi),
                
                # MACD
                "macd": round(macd, 4),
                "macd_signal": round(signal, 4),
                "macd_histogram": round(histogram, 4),
                "macd_trend": "상승" if histogram > 0 else "하락",
                
                # Bollinger Bands
                "bb_upper": round(bb_upper, 2),
                "bb_middle": round(bb_middle, 2),
                "bb_lower": round(bb_lower, 2),
                "bb_position": round(bb_position, 1),
                
                # 거래량
                "current_volume": int(current_volume),
                "avg_volume": int(avg_volume),
                "volume_ratio": round(volume_ratio, 1),
                
                # 변동성 및 추세
                "volatility": round(volatility, 2),
                "trend": trend,
                
                # 가격 변동
                "price_change_1d": round(price_change_1d, 2),
                "price_change_5d": round(price_change_5d, 2) if price_change_5d else None,
                "price_change_20d": round(price_change_20d, 2) if price_change_20d else None,
            }
            
        except Exception as e:
            return {"error": f"지표 계산 중 오류: {str(e)}"}
    
    def _determine_trend(self, price, ma20, ma50, ma200):
        """추세 판단"""
        if ma200 is None:
            if price > ma20 > ma50:
                return "강한 상승"
            elif price > ma20:
                return "상승"
            elif price < ma20 < ma50:
                return "강한 하락"
            else:
                return "하락"
        else:
            if price > ma20 > ma50 > ma200:
                return "강한 상승"
            elif price > ma20 > ma50:
                return "상승"
            elif price < ma20 < ma50 < ma200:
                return "강한 하락"
            elif price < ma20 < ma50:
                return "하락"
            else:
                return "횡보"
    
    def _interpret_rsi(self, rsi):
        """RSI 해석"""
        if rsi >= 70:
            return "과매수 (조정 가능성)"
        elif rsi >= 60:
            return "강세"
        elif rsi >= 40:
            return "중립"
        elif rsi >= 30:
            return "약세"
        else:
            return "과매도 (반등 가능성)"
    
    def generate_analysis(self, indicators: Dict[str, Any], temperature: float = 0.3, query: str = "") -> str:
        """
        AI 기반 기술적 분석 리포트 생성
        
        Args:
            indicators: 계산된 지표들
            temperature: AI 응답 창의성
            
        Returns:
            str: 분석 리포트
        """
        if "error" in indicators:
            return f"❌ {indicators['error']}"
        
        if not self.openai_client:
            return "⚠️ OpenAI API 키가 설정되지 않았습니다."
        
        # 프롬프트 구성
        system_prompt = """너는 전문 기술적 분석가야. 차트 지표를 바탕으로 투자자에게 명확한 가이드를 제공해.

**분석 원칙**:
1. **현재 상태 진단**: 지표들이 말하는 현재 시장 상황
2. **매매 타이밍**: 지금이 매수/매도/관망 중 어느 시점인지
3. **주요 가격대**: 지지선, 저항선, 손절가
4. **리스크 요인**: 주의해야 할 신호들

**답변 스타일**:
- 구체적 숫자 기반 설명
- 단정적이지 않되, 명확한 방향성 제시
- 초보자도 이해할 수 있게 쉽게 설명"""

        user_prompt = f"""다음 기술적 지표를 분석해줘:

**종목**: {indicators['ticker']}
**현재가**: ${indicators['current_price']} ({indicators['date']})
**1일 변동**: {indicators['price_change_1d']}%
**5일 변동**: {indicators.get('price_change_5d', 'N/A')}%
**20일 변동**: {indicators.get('price_change_20d', 'N/A')}%

**이동평균선**:
- MA20: ${indicators['ma20']}
- MA50: ${indicators['ma50']}
- MA200: ${indicators.get('ma200', 'N/A')}
- 추세: {indicators['trend']}

**RSI (14일)**: {indicators['rsi']} ({indicators['rsi_signal']})

**MACD**:
- MACD: {indicators['macd']}
- Signal: {indicators['macd_signal']}
- Histogram: {indicators['macd_histogram']} ({indicators['macd_trend']})

**볼린저 밴드**:
- 상단: ${indicators['bb_upper']}
- 중간: ${indicators['bb_middle']}
- 하단: ${indicators['bb_lower']}
- 현재 위치: {indicators['bb_position']}% (0%=하단, 100%=상단)

**거래량**:
- 현재: {indicators['current_volume']:,}
- 평균 대비: {indicators['volume_ratio']}%

**변동성**: {indicators['volatility']}% (연간)

위 지표를 바탕으로:
1. 현재 차트 상태 진단
2. 매수/매도/관망 중 추천 행동
3. 주요 가격대 (지지선, 저항선)
4. 주의사항

특히 다음 사용자의 질문이나 요구사항에 집중해서 답변해줘:
사용자 요청: "{query if query else '전반적인 기술적 분석을 해줘.'}"

위 내용을 바탕으로 전문적이고 명확한 분석 리포트를 작성해줘."""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"❌ AI 분석 생성 중 오류: {str(e)}"
    
    def process(self, query: str, **kwargs) -> Dict[str, Any]:
        """
        기술적 분석 처리
        
        Args:
            query: 사용자 질문 (티커 포함)
            **kwargs: 추가 파라미터 (ticker, period, temperature 등)
            
        Returns:
            dict: {'analysis': 분석 리포트, 'indicators': 지표 데이터}
        """
        # 티커 추출 (kwargs 또는 query에서)
        ticker = kwargs.get('ticker')
        if not ticker:
            # query에서 티커 및 종목명 추출 시도
            from core.stock_extractor import StockExtractor
            extractor = StockExtractor()
            
            # 1. 한글명 매핑 시도 (예: "구글" -> "GOOGL")
            for name, mapped_ticker in extractor.TICKER_MAP.items():
                if name in query:
                    ticker = mapped_ticker
                    break
            
            # 2. 매핑 실패 시 영어 대문자 티커 검색 (예: "AAPL")
            if not ticker:
                import re
                words = query.upper().split()
                for word in words:
                    clean_word = re.sub(r'[^A-Z]', '', word)
                    if 1 <= len(clean_word) <= 5:
                        ticker = clean_word
                        break
        
        if not ticker:
            return {
                "analysis": "⚠️ 종목 티커를 입력해주세요. (예: TSLA, AAPL, NVDA)",
                "indicators": None
            }
        
        period = kwargs.get('period', '6mo')
        temperature = kwargs.get('temperature', 0.3)
        
        # 지표 계산
        indicators = self.calculate_indicators(ticker, period)
        
        # AI 분석 생성
        analysis = self.generate_analysis(indicators, temperature, query)
        
        return {
            "analysis": analysis,
            "indicators": indicators
        }


if __name__ == "__main__":
    # 테스트
    agent = TechnicalAgent()
    
    result = agent.process("TSLA 기술적 분석", ticker="TSLA")
    
    print("=== 기술적 분석 결과 ===")
    print(result['analysis'])
    
    if result['indicators'] and 'error' not in result['indicators']:
        print("\n=== 주요 지표 ===")
        ind = result['indicators']
        print(f"현재가: ${ind['current_price']}")
        print(f"RSI: {ind['rsi']} ({ind['rsi_signal']})")
        print(f"추세: {ind['trend']}")
