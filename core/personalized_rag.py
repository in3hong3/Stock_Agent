"""
개인화된 RAG 엔진
사용자의 보유 포트폴리오를 고려한 맞춤형 답변 생성
"""
from core.rag_engine import RAGEngine
from modules.portfolio_analyzer import PortfolioAnalyzer
import pandas as pd
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)


class PersonalizedRAG:
    """포트폴리오 정보를 활용한 개인화 RAG 시스템"""
    
    def __init__(self, rag_engine: RAGEngine, portfolio_path: str = "data/portfolio.csv"):
        """
        초기화
        
        Args:
            rag_engine: 기본 RAG 엔진
            portfolio_path: 포트폴리오 CSV 파일 경로
        """
        self.rag_engine = rag_engine
        self.portfolio_path = portfolio_path
        self.portfolio_analyzer = PortfolioAnalyzer(rag_engine)
        self.portfolio_df = None
        self._load_portfolio()
    
    def _load_portfolio(self):
        """포트폴리오 데이터 로드"""
        try:
            self.portfolio_df = self.portfolio_analyzer.load_portfolio_from_csv(self.portfolio_path)
            if not self.portfolio_df.empty:
                logger.info(f"포트폴리오 로드 완료: {len(self.portfolio_df)}개 종목")
            else:
                logger.warning("포트폴리오가 비어있습니다")
        except Exception as e:
            logger.error(f"포트폴리오 로드 실패: {str(e)}")
            self.portfolio_df = pd.DataFrame()
    
    def _get_portfolio_context(self) -> str:
        """
        포트폴리오 정보를 컨텍스트로 변환
        
        Returns:
            str: 포트폴리오 요약 텍스트
        """
        if self.portfolio_df is None or self.portfolio_df.empty:
            return ""
        
        # 보유 종목 요약
        context = "\n\n[사용자 보유 포트폴리오]\n"
        context += f"총 {len(self.portfolio_df)}개 종목 보유 중\n\n"
        
        # 주요 종목 (평가금액 상위 5개)
        top_holdings = self.portfolio_df.nlargest(5, 'eval_amount')
        context += "주요 보유 종목:\n"
        for _, stock in top_holdings.iterrows():
            context += f"- {stock['name']} ({stock['ticker']}): "
            context += f"{stock['quantity']:,}주, "
            context += f"수익률 {stock['profit_rate']:.1f}%\n"
        
        # 수익/손실 종목 수
        profitable = len(self.portfolio_df[self.portfolio_df['profit_loss'] > 0])
        losing = len(self.portfolio_df[self.portfolio_df['profit_loss'] < 0])
        context += f"\n수익 종목: {profitable}개 | 손실 종목: {losing}개\n"
        
        return context
    
    def _extract_tickers_from_query(self, query: str) -> List[str]:
        """
        질문에서 보유 종목 티커 추출
        
        Args:
            query: 사용자 질문
            
        Returns:
            List[str]: 관련 티커 리스트
        """
        if self.portfolio_df is None or self.portfolio_df.empty:
            return []
        
        mentioned_tickers = []
        query_lower = query.lower()
        
        for _, stock in self.portfolio_df.iterrows():
            ticker = stock['ticker']
            name = stock['name'].lower()
            
            # 티커나 종목명이 질문에 포함되어 있는지 확인
            if ticker.lower() in query_lower or name in query_lower:
                mentioned_tickers.append(ticker)
        
        return mentioned_tickers
    
    def _get_related_holdings(self, query: str) -> List[Dict]:
        """
        질문과 관련된 보유 종목 찾기
        
        Args:
            query: 사용자 질문
            
        Returns:
            List[Dict]: 관련 종목 정보
        """
        if self.portfolio_df is None or self.portfolio_df.empty:
            return []
        
        related_stocks = []
        query_lower = query.lower()
        
        # 키워드 기반 매칭
        keyword_map = {
            'ai': ['NVDA', 'GOOGL', 'META', 'AMZN', 'ORCL', 'IONQ'],
            '반도체': ['NVDA', 'MU', 'TSM', 'SKYT'],
            '빅테크': ['GOOGL', 'AMZN', 'META', 'ORCL'],
            '클라우드': ['GOOGL', 'AMZN', 'ORCL'],
            '양자컴퓨팅': ['IONQ'],
            '태양광': ['FSLR'],
            '일본': ['1497.T', '9984.T'],
            '은행': ['KRE'],
            '헬스케어': ['XLV'],
        }
        
        # 키워드 매칭
        for keyword, tickers in keyword_map.items():
            if keyword in query_lower:
                for ticker in tickers:
                    stock_data = self.portfolio_df[self.portfolio_df['ticker'] == ticker]
                    if not stock_data.empty:
                        related_stocks.append(stock_data.iloc[0].to_dict())
        
        # 직접 언급된 종목 추가
        mentioned_tickers = self._extract_tickers_from_query(query)
        for ticker in mentioned_tickers:
            stock_data = self.portfolio_df[self.portfolio_df['ticker'] == ticker]
            if not stock_data.empty:
                stock_dict = stock_data.iloc[0].to_dict()
                if stock_dict not in related_stocks:
                    related_stocks.append(stock_dict)
        
        return related_stocks
    
    def _augment_query(self, query: str) -> str:
        """
        질문에 보유 종목 정보 추가
        
        Args:
            query: 원본 질문
            
        Returns:
            str: 증강된 질문
        """
        related_stocks = self._get_related_holdings(query)
        
        if not related_stocks:
            return query
        
        # 관련 종목 티커 추가
        tickers = [stock['ticker'] for stock in related_stocks]
        augmented = f"{query} {' '.join(tickers)}"
        
        logger.info(f"질문 증강: {query} → {augmented}")
        return augmented
    
    def chat(self, query: str, top_k: int = 10, temperature: float = 0.7, 
             conversation_history: Optional[List[Dict]] = None,
             use_portfolio_context: bool = True) -> Dict:
        """
        개인화된 RAG 채팅
        
        Args:
            query: 사용자 질문
            top_k: 검색할 문서 개수
            temperature: AI 응답의 창의성
            conversation_history: 이전 대화 히스토리
            use_portfolio_context: 포트폴리오 컨텍스트 사용 여부
            
        Returns:
            Dict: 답변, 소스, 후속 질문, 관련 보유 종목
        """
        try:
            # 1. 질문 증강 (보유 종목 티커 추가)
            augmented_query = self._augment_query(query) if use_portfolio_context else query
            
            # 2. 포트폴리오 컨텍스트 준비
            portfolio_context = ""
            related_holdings = []
            if use_portfolio_context:
                portfolio_context = self._get_portfolio_context()
                related_holdings = self._get_related_holdings(query)

            # 3. 기본 RAG 검색 및 답변 생성
            result = self.rag_engine.chat(
                query=augmented_query,
                top_k=top_k,
                temperature=temperature,
                conversation_history=conversation_history,
                extra_context=portfolio_context  # 신규 필드 전달
            )
            
            # 4. 관련 보유 종목 정보 메타데이터로 추가
            result['related_holdings'] = related_holdings
            
            return result
            
        except Exception as e:
            logger.error(f"개인화 RAG 오류: {str(e)}")
            return {
                'answer': f"오류가 발생했습니다: {str(e)}",
                'sources': [],
                'followup_questions': [],
                'related_holdings': []
            }
    
    def _format_related_holdings(self, holdings: List[Dict]) -> str:
        """
        관련 보유 종목을 텍스트로 포맷팅
        
        Args:
            holdings: 관련 종목 리스트
            
        Returns:
            str: 포맷팅된 텍스트
        """
        if not holdings:
            return ""
        
        text = "\n\n💼 **보유 중인 관련 종목**\n"
        for stock in holdings:
            text += f"\n- **{stock['name']}** ({stock['ticker']})\n"
            text += f"  - 보유: {stock['quantity']:,}주\n"
            text += f"  - 평균단가: {stock['avg_price']:,.0f}원\n"
            text += f"  - 현재가: {stock['current_price']:,.0f}원\n"
            text += f"  - 수익률: {stock['profit_rate']:.1f}%\n"
        
        return text
    
    def _inject_portfolio_context(self, answer: str, portfolio_context: str) -> str:
        """
        답변에 포트폴리오 컨텍스트 주입
        
        Args:
            answer: 원본 답변
            portfolio_context: 포트폴리오 컨텍스트
            
        Returns:
            str: 컨텍스트가 추가된 답변
        """
        # 답변 끝에 포트폴리오 정보 추가
        return f"{answer}\n\n{portfolio_context}"
    
    def get_portfolio_summary(self) -> Dict:
        """
        포트폴리오 전체 요약
        
        Returns:
            Dict: 요약 정보
        """
        if self.portfolio_df is None or self.portfolio_df.empty:
            return {
                'status': 'empty',
                'message': '보유 주식이 없습니다'
            }
        
        return self.portfolio_analyzer.analyze_portfolio(self.portfolio_df)


if __name__ == "__main__":
    # 테스트 코드
    logging.basicConfig(level=logging.INFO)
    
    # RAG 엔진 초기화
    base_rag = RAGEngine()
    
    # 개인화 RAG 초기화
    personalized_rag = PersonalizedRAG(base_rag)
    
    # 테스트 질문
    test_queries = [
        "AI 반도체 시장 전망은?",
        "엔비디아 주가 어떻게 될까?",
        "빅테크 기업들 실적은?"
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"질문: {query}")
        print('='*60)
        
        result = personalized_rag.chat(query, top_k=5)
        
        print(f"\n답변:\n{result['answer'][:300]}...")
        
        if result.get('related_holdings'):
            print(f"\n관련 보유 종목: {len(result['related_holdings'])}개")
            for stock in result['related_holdings']:
                print(f"  - {stock['name']} ({stock['ticker']})")
