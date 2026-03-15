"""
Technical Agent 테스트 스크립트
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.technical_agent import TechnicalAgent

def test_technical_agent():
    print("=== Technical Agent 테스트 ===\n")
    
    agent = TechnicalAgent()
    
    # 테스트 1: TSLA 분석
    print("[테스트 1] TSLA 기술적 분석")
    print("-" * 50)
    result = agent.process("TSLA 기술적 분석", ticker="TSLA")
    
    if result['indicators'] and 'error' not in result['indicators']:
        ind = result['indicators']
        print(f"종목: {ind['ticker']}")
        print(f"현재가: ${ind['current_price']}")
        print(f"날짜: {ind['date']}")
        print(f"\n이동평균선:")
        print(f"  MA20: ${ind['ma20']}")
        print(f"  MA50: ${ind['ma50']}")
        print(f"  MA200: ${ind['ma200']}")
        print(f"\nRSI: {ind['rsi']} ({ind['rsi_signal']})")
        print(f"\nMACD:")
        print(f"  MACD: {ind['macd']}")
        print(f"  Signal: {ind['macd_signal']}")
        print(f"  Histogram: {ind['macd_histogram']} ({ind['macd_trend']})")
        print(f"\n볼린저 밴드 위치: {ind['bb_position']}%")
        print(f"추세: {ind['trend']}")
        print(f"변동성: {ind['volatility']}%")
        
        print(f"\n\n=== AI 분석 결과 ===")
        print(result['analysis'])
    else:
        print(f"오류: {result['indicators'].get('error', '알 수 없는 오류')}")
    
    print("\n" + "=" * 50 + "\n")
    
    # 테스트 2: AAPL 분석
    print("[테스트 2] AAPL 기술적 분석")
    print("-" * 50)
    result2 = agent.process("AAPL", ticker="AAPL")
    
    if result2['indicators'] and 'error' not in result2['indicators']:
        ind2 = result2['indicators']
        print(f"종목: {ind2['ticker']}")
        print(f"현재가: ${ind2['current_price']}")
        print(f"RSI: {ind2['rsi']} ({ind2['rsi_signal']})")
        print(f"추세: {ind2['trend']}")
        
        print(f"\n\n=== AI 분석 결과 ===")
        print(result2['analysis'])
    else:
        print(f"오류: {result2['indicators'].get('error', '알 수 없는 오류')}")


if __name__ == "__main__":
    test_technical_agent()
