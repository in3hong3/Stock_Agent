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
    
    def _get_portfolio_context(self, related_holdings: Optional[List[Dict]] = None) -> str:
        """포트폴리오 정보를 LLM이 활용 가능한 구조화 컨텍스트로 변환.

        - 전체 비중%, 평단/현재가, 손익률을 종목별로 명시
        - 질문과 관련된 종목(`related_holdings`)은 우선 상세 노출, 나머지는 요약
        - 답변 지시문을 함께 끼워 LLM이 '내 관점에서' 답하도록 유도
        """
        if self.portfolio_df is None or self.portfolio_df.empty:
            return ""

        df = self.portfolio_df
        total_eval = float(df['eval_amount'].sum()) or 1.0
        n_total = len(df)
        n_win = int((df['profit_loss'] > 0).sum())
        n_lose = int((df['profit_loss'] < 0).sum())

        related_tickers = {h['ticker'] for h in (related_holdings or [])}

        def _line(stock) -> str:
            weight = float(stock['eval_amount']) / total_eval * 100
            return (
                f"- {stock['name']} ({stock['ticker']}): "
                f"비중 {weight:.1f}% · 평단 {stock['avg_price']:,.2f} → 현재가 {stock['current_price']:,.2f} "
                f"· 수익률 {stock['profit_rate']:+.1f}% · {int(stock['quantity']):,}주"
            )

        lines = []
        lines.append("[사용자 보유 포트폴리오 — 답변할 때 반드시 이 정보를 활용하세요]")
        lines.append(
            f"총 {n_total}개 종목 보유 (수익 {n_win} · 손실 {n_lose}) · "
            f"총 평가액 {total_eval:,.0f}"
        )

        if related_tickers:
            lines.append("\n[질문과 직접 관련된 보유 종목]")
            for _, s in df[df['ticker'].isin(related_tickers)].iterrows():
                lines.append(_line(s))

            others = df[~df['ticker'].isin(related_tickers)].nlargest(5, 'eval_amount')
            if not others.empty:
                lines.append("\n[그 외 주요 보유 종목 (비중 상위 5개)]")
                for _, s in others.iterrows():
                    lines.append(_line(s))
        else:
            lines.append("\n[비중 상위 보유 종목]")
            for _, s in df.nlargest(8, 'eval_amount').iterrows():
                lines.append(_line(s))

        # 가장 큰 손실/수익 종목은 항상 알려준다 (사용자가 신경 쓸 가능성 큼)
        try:
            worst = df.loc[df['profit_rate'].idxmin()]
            best = df.loc[df['profit_rate'].idxmax()]
            lines.append(
                f"\n[극단 수익률] 최고: {best['name']} ({best['ticker']}, {best['profit_rate']:+.1f}%) "
                f"/ 최저: {worst['name']} ({worst['ticker']}, {worst['profit_rate']:+.1f}%)"
            )
        except (ValueError, KeyError):
            pass

        lines.append(
            "\n[답변 지침]"
            "\n1. 사용자가 직접 보유한 종목이 질문과 관련 있으면 그 종목의 '현재 비중·평단 대비 수익률'을 근거로 우선 분석할 것."
            "\n2. 새 종목 추천보다 '보유 중인 어떤 종목과의 관계'를 먼저 짚을 것."
            "\n3. 손실 중인 보유 종목이 관련되면 '추가매수 vs 손절 vs 보유'에 대한 판단을 명확히 제시할 것."
            "\n4. 보유하지 않은 종목을 단순 추천하지 말 것 — 사용자는 이미 포지션이 있음."
        )
        return "\n".join(lines)
    
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
    
    # 일반 산업/테마 키워드 → 보유 종목 매칭은 사용자가 실제 보유한 종목만 추출하기 위한 보조 룰.
    # 종목 자체가 적힌 게 아니라 '주제'만 적힌 질문에서, 어떤 보유 종목이 관련 있는지 좁히는 용도.
    _THEME_KEYWORDS = {
        "ai": ["nvda", "googl", "msft", "meta", "amzn", "orcl", "ionq", "smci", "avgo", "palantir", "pltr"],
        "반도체": ["nvda", "mu", "tsm", "skyt", "amd", "intc", "avgo", "asml", "삼성전자", "sk하이닉스", "하이닉스", "005930", "000660"],
        "빅테크": ["googl", "amzn", "meta", "msft", "aapl", "orcl"],
        "클라우드": ["googl", "amzn", "msft", "orcl", "snow", "ddog"],
        "양자컴퓨팅": ["ionq", "rgti", "qbts"],
        "태양광": ["fslr", "enph", "sedg"],
        "전기차": ["tsla", "rivn", "byd", "nio"],
        "원전": ["smr", "ccj", "uec", "leu"],
        "방산": ["lmt", "rtx", "noc", "ge", "한화에어로", "한국항공우주"],
        "은행": ["kre", "xlf", "jpm", "kb금융", "신한지주", "하나금융"],
        "헬스케어": ["xlv", "lly", "unh", "삼성바이오로직스"],
        "일본": [".t"],
        "한국": [".ks", ".kq"],
    }

    def _get_related_holdings(self, query: str) -> List[Dict]:
        """질문과 관련된 보유 종목 추출.

        결과는 반드시 사용자가 '실제로 보유 중'인 종목만 포함. 다음 순서로 매칭:
        1. 종목명/티커가 질문에 직접 등장 (가장 강한 신호)
        2. 일반 테마 키워드(AI/반도체 등) → 그 테마에 해당하는 종목 중 보유 중인 것만
        3. '내 종목', '포트폴리오', '전부' 같은 전체 지시어가 있으면 모든 보유 종목 반환
        """
        if self.portfolio_df is None or self.portfolio_df.empty:
            return []

        query_lower = query.lower()
        related: List[Dict] = []
        seen: set = set()

        def _add(ticker: str):
            if ticker in seen:
                return
            row = self.portfolio_df[self.portfolio_df['ticker'] == ticker]
            if not row.empty:
                related.append(row.iloc[0].to_dict())
                seen.add(ticker)

        # 1) 직접 언급
        for ticker in self._extract_tickers_from_query(query):
            _add(ticker)

        # 2) 전체 지시어 → 보유 종목 전체
        all_indicators = ["내 종목", "내 포트", "포트폴리오", "보유 중", "보유종목", "보유 종목", "전부", "전체", "모든 종목"]
        if any(k in query_lower for k in all_indicators):
            for _, stock in self.portfolio_df.iterrows():
                _add(stock['ticker'])
            return related

        # 3) 테마 키워드 매칭 — 보유 중인 종목 중에서만
        portfolio_tickers_lower = {t.lower(): t for t in self.portfolio_df['ticker'].astype(str)}
        portfolio_names_lower = {str(n).lower(): t for n, t in zip(self.portfolio_df['name'], self.portfolio_df['ticker'])}

        for theme, candidates in self._THEME_KEYWORDS.items():
            if theme not in query_lower:
                continue
            for cand in candidates:
                cand_low = cand.lower()
                # 접미사 매칭 (.T, .KS 등)
                if cand_low.startswith("."):
                    for t_low, t_orig in portfolio_tickers_lower.items():
                        if t_low.endswith(cand_low):
                            _add(t_orig)
                    continue
                # 티커 정확 매칭
                if cand_low in portfolio_tickers_lower:
                    _add(portfolio_tickers_lower[cand_low])
                    continue
                # 종목명 부분 매칭
                for name_low, t_orig in portfolio_names_lower.items():
                    if cand_low in name_low:
                        _add(t_orig)
                        break

        return related
    
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
            # 포트폴리오는 사용자가 자주 수정하므로 매번 최신 상태로 다시 읽는다
            if use_portfolio_context:
                self._load_portfolio()

            related_holdings = self._get_related_holdings(query) if use_portfolio_context else []
            portfolio_context = self._get_portfolio_context(related_holdings) if use_portfolio_context else ""
            augmented_query = self._augment_query(query) if use_portfolio_context else query

            result = self.rag_engine.chat(
                query=augmented_query,
                top_k=top_k,
                temperature=temperature,
                conversation_history=conversation_history,
                extra_context=portfolio_context,
            )

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
