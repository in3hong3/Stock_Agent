"""
뉴스 & 감성 분석 에이전트 (News & Sentiment Agent)
최신 뉴스 수집 및 시장 감성 분석
"""
from typing import Dict, Any, List, Optional
from agents.base_agent import BaseAgent
import yfinance as yf
from datetime import datetime, timedelta
from openai import OpenAI
import os


class NewsAgent(BaseAgent):
    """뉴스 & 감성 분석 에이전트"""
    
    def __init__(self, agent_id: str = "news_sentiment", 
                 name: str = "뉴스분석관", 
                 description: str = "최신 뉴스 수집 및 시장 감성 분석", 
                 **kwargs):
        super().__init__(agent_id, name, description, **kwargs)
        
        # OpenAI 클라이언트 초기화
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            self.openai_client = OpenAI(api_key=api_key)
        else:
            self.openai_client = None
    
    def fetch_news(self, ticker: str, max_news: int = 10) -> List[Dict[str, Any]]:
        """
        yfinance를 통해 최신 뉴스 가져오기
        
        Args:
            ticker: 종목 티커
            max_news: 최대 뉴스 개수
            
        Returns:
            list: 뉴스 리스트 [{'title', 'publisher', 'link', 'published'}]
        """
        try:
            stock = yf.Ticker(ticker)
            news_data = stock.news
            
            if not news_data:
                return []
            
            news_list = []
            for item in news_data[:max_news]:
                # yfinance 0.2.4x+ 신규 포맷: 'content' 하위에 데이터 존재
                content = item.get('content', item)

                title = content.get('title', 'N/A')

                # 링크: 신규 포맷은 canonicalUrl/clickThroughUrl, 구버전은 link
                link = item.get('link') or '#'
                if link == '#':
                    for url_key in ('canonicalUrl', 'clickThroughUrl'):
                        url_obj = content.get(url_key)
                        if isinstance(url_obj, dict) and url_obj.get('url'):
                            link = url_obj['url']
                            break

                # 출처
                publisher = item.get('publisher', 'N/A')
                if publisher == 'N/A':
                    provider = content.get('provider')
                    if isinstance(provider, dict):
                        publisher = provider.get('displayName', 'N/A')

                # 발행 시각
                published = 'N/A'
                if item.get('providerPublishTime'):
                    published = datetime.fromtimestamp(item['providerPublishTime']).strftime('%Y-%m-%d %H:%M')
                elif content.get('pubDate'):
                    published = str(content['pubDate'])[:16].replace('T', ' ')

                news_list.append({
                    'title': title,
                    'publisher': publisher,
                    'link': link,
                    'published': published,
                    'thumbnail': '',
                })

            return news_list
            
        except Exception as e:
            print(f"뉴스 가져오기 오류: {str(e)}")
            return []
    
    def analyze_sentiment(self, ticker: str, news_list: List[Dict[str, Any]], temperature: float = 0.3) -> Dict[str, Any]:
        """
        AI 기반 뉴스 감성 분석
        
        Args:
            ticker: 종목 티커
            news_list: 뉴스 리스트
            temperature: AI 응답 창의성
            
        Returns:
            dict: {'summary': 요약, 'sentiment_score': 점수(0-100), 'sentiment': 감성, 'key_topics': 주요 토픽}
        """
        if not news_list:
            return {
                "summary": f"{ticker}에 대한 최신 뉴스를 찾을 수 없습니다.",
                "sentiment_score": 50,
                "sentiment": "중립",
                "key_topics": []
            }
        
        if not self.openai_client:
            return {
                "summary": "⚠️ OpenAI API 키가 설정되지 않았습니다.",
                "sentiment_score": 50,
                "sentiment": "중립",
                "key_topics": []
            }
        
        # 뉴스 제목들을 프롬프트에 포함
        news_titles = "\n".join([f"- [{item['published']}] {item['title']} ({item['publisher']})" for item in news_list])
        
        system_prompt = """너는 금융 뉴스 분석 전문가야. 뉴스 제목들을 분석해서 시장의 감성(Sentiment)을 판단해.

**분석 항목**:
1. **감성 점수 (0-100)**: 
   - 0-20: 매우 부정적 (공포)
   - 21-40: 부정적 (우려)
   - 41-60: 중립
   - 61-80: 긍정적 (기대)
   - 81-100: 매우 긍정적 (열광)

2. **주요 토픽**: 뉴스에서 반복되는 핵심 키워드 3-5개

3. **요약**: 전체 뉴스가 말하는 핵심 메시지 (2-3문장)

**주의사항**:
- 뉴스 제목만으로 판단하므로 과도한 해석 금지
- 객관적이고 균형잡힌 시각 유지
- 구체적 근거 제시"""

        user_prompt = f"""다음은 {ticker} 종목에 대한 최신 뉴스 제목들이야:

{news_titles}

위 뉴스들을 분석해서 다음 형식으로 답변해줘:

**감성 점수**: [0-100 사이 숫자]
**감성**: [매우 부정적/부정적/중립/긍정적/매우 긍정적]
**주요 토픽**: [키워드1, 키워드2, 키워드3, ...]
**요약**: [2-3문장으로 핵심 메시지 요약]"""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature
            )
            
            analysis_text = response.choices[0].message.content
            
            # 간단한 파싱 (실제로는 더 정교한 파싱 필요)
            sentiment_score = 50  # 기본값
            sentiment = "중립"
            key_topics = []
            summary = analysis_text
            
            # 텍스트에서 점수 추출 시도
            lines = analysis_text.split('\n')
            for line in lines:
                if '감성 점수' in line or 'sentiment score' in line.lower():
                    try:
                        # 숫자 추출
                        import re
                        numbers = re.findall(r'\d+', line)
                        if numbers:
                            sentiment_score = int(numbers[0])
                    except:
                        pass
                elif '감성:' in line or 'sentiment:' in line.lower():
                    if '매우 긍정' in line or 'very positive' in line.lower():
                        sentiment = "매우 긍정적"
                    elif '긍정' in line or 'positive' in line.lower():
                        sentiment = "긍정적"
                    elif '매우 부정' in line or 'very negative' in line.lower():
                        sentiment = "매우 부정적"
                    elif '부정' in line or 'negative' in line.lower():
                        sentiment = "부정적"
                    else:
                        sentiment = "중립"
                elif '주요 토픽' in line or 'key topics' in line.lower():
                    # 키워드 추출
                    topics_text = line.split(':', 1)[-1].strip()
                    key_topics = [t.strip() for t in topics_text.split(',')]
            
            return {
                "summary": analysis_text,
                "sentiment_score": sentiment_score,
                "sentiment": sentiment,
                "key_topics": key_topics,
                "news_count": len(news_list)
            }
            
        except Exception as e:
            return {
                "summary": f"❌ AI 분석 생성 중 오류: {str(e)}",
                "sentiment_score": 50,
                "sentiment": "중립",
                "key_topics": [],
                "news_count": len(news_list)
            }
    
    def process(self, query: str, **kwargs) -> Dict[str, Any]:
        """
        뉴스 & 감성 분석 처리
        
        Args:
            query: 사용자 질문 (티커 포함)
            **kwargs: 추가 파라미터 (ticker, max_news, temperature 등)
            
        Returns:
            dict: {'analysis': 분석 결과, 'news': 뉴스 리스트}
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
                "analysis": {
                    "summary": "⚠️ 종목 티커를 입력해주세요. (예: TSLA, AAPL, NVDA)",
                    "sentiment_score": 50,
                    "sentiment": "중립",
                    "key_topics": []
                },
                "news": []
            }
        
        max_news = kwargs.get('max_news', 10)
        temperature = kwargs.get('temperature', 0.3)
        
        # 뉴스 가져오기
        news_list = self.fetch_news(ticker, max_news)
        
        # 감성 분석
        analysis = self.analyze_sentiment(ticker, news_list, temperature)
        
        return {
            "analysis": analysis,
            "news": news_list,
            "ticker": ticker
        }


if __name__ == "__main__":
    # 테스트
    agent = NewsAgent()
    
    result = agent.process("NVDA 최신 뉴스", ticker="NVDA")
    
    print("=== 뉴스 & 감성 분석 결과 ===")
    print(result['analysis']['summary'])
    print(f"\n감성 점수: {result['analysis']['sentiment_score']}/100 ({result['analysis']['sentiment']})")
    
    if result['news']:
        print(f"\n=== 최신 뉴스 ({len(result['news'])}개) ===")
        for i, news in enumerate(result['news'][:5], 1):
            print(f"\n[{i}] {news['title']}")
            print(f"    출처: {news['publisher']} | {news['published']}")
            print(f"    링크: {news['link']}")
