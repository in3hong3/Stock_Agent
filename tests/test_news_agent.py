"""
News Agent 테스트 스크립트
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.news_agent import NewsAgent

def test_news_agent():
    print("=== News Agent 테스트 ===\n")
    
    agent = NewsAgent()
    
    # 테스트 1: NVDA 뉴스
    print("[테스트 1] NVDA 최신 뉴스 & 감성 분석")
    print("-" * 50)
    result = agent.process("NVDA 최신 뉴스", ticker="NVDA", max_news=5)
    
    print(f"종목: {result.get('ticker', 'N/A')}")
    print(f"뉴스 개수: {len(result.get('news', []))}")
    
    if result['analysis']:
        print(f"\n감성 점수: {result['analysis']['sentiment_score']}/100")
        print(f"감성: {result['analysis']['sentiment']}")
        
        if result['analysis'].get('key_topics'):
            print(f"주요 토픽: {', '.join(result['analysis']['key_topics'])}")
        
        print(f"\n=== AI 분석 요약 ===")
        print(result['analysis']['summary'])
    
    if result.get('news'):
        print(f"\n\n=== 최신 뉴스 ({len(result['news'])}개) ===")
        for i, news in enumerate(result['news'], 1):
            print(f"\n[{i}] {news['title']}")
            print(f"    출처: {news['publisher']} | {news['published']}")
            print(f"    링크: {news['link']}")
    
    print("\n" + "=" * 50 + "\n")
    
    # 테스트 2: TSLA 뉴스
    print("[테스트 2] TSLA 최신 뉴스 & 감성 분석")
    print("-" * 50)
    result2 = agent.process("TSLA", ticker="TSLA", max_news=3)
    
    print(f"종목: {result2.get('ticker', 'N/A')}")
    print(f"뉴스 개수: {len(result2.get('news', []))}")
    
    if result2['analysis']:
        print(f"\n감성 점수: {result2['analysis']['sentiment_score']}/100")
        print(f"감성: {result2['analysis']['sentiment']}")
        
        print(f"\n=== AI 분석 요약 ===")
        print(result2['analysis']['summary'])


if __name__ == "__main__":
    test_news_agent()
