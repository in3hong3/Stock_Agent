"""
RAG 엔진 모듈
벡터 검색과 AI 답변 생성을 통합한 RAG 시스템
"""
from utils.vector_store import VectorStore
from utils.pinecone_store import PineconeStore
from openai import OpenAI
import os
import datetime
from dotenv import load_dotenv
from config.settings import VECTOR_DB_TYPE, LLM_MODEL_SMART, LLM_MODEL_DEFAULT

load_dotenv()


class RAGEngine:
    """RAG 검색 및 답변 생성 엔진"""
    
    def __init__(self, vector_store=None):
        # 벡터 스토어 초기화
        if vector_store:
            self.vector_store = vector_store
        else:
            if VECTOR_DB_TYPE == "pinecone":
                self.vector_store = PineconeStore()
            else:
                self.vector_store = VectorStore()
        
        # OpenAI 클라이언트 초기화
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        self.openai_client = OpenAI(api_key=api_key)
    
    def _extract_date_from_query(self, query: str):
        """
        쿼리에서 날짜를 추출하여 YYYY-MM-DD 형식으로 반환
        예: "2월 26일", "26일", "2026-02-26" 등 처리
        Returns: str (YYYY-MM-DD) or None
        """
        import re
        import datetime
        today = datetime.date.today()

        # 패턴 1: "YYYY년 M월 D일" 또는 "M월 D일" 또는 "M/D"
        # "2월 26일", "2월26일", "2026년 2월 26일"
        patterns = [
            r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일',  # 2026년 2월 26일
            r'(\d{1,2})월\s*(\d{1,2})일',               # 2월 26일
            r'(\d{4})-(\d{2})-(\d{2})',                  # 2026-02-26
            r'(\d{1,2})/(\d{1,2})',                      # 2/26
        ]

        for pattern in patterns:
            m = re.search(pattern, query)
            if m:
                groups = m.groups()
                try:
                    if len(groups) == 3 and len(groups[0]) == 4:
                        # YYYY년 M월 D일 or YYYY-MM-DD
                        return f"{groups[0]}-{int(groups[1]):02d}-{int(groups[2]):02d}"
                    elif len(groups) == 2:
                        # M월 D일 or M/D → 올해 기준
                        month = int(groups[0])
                        day = int(groups[1])
                        return f"{today.year}-{month:02d}-{day:02d}"
                    elif len(groups) == 3:
                        year = int(groups[0])
                        month = int(groups[1])
                        day = int(groups[2])
                        return f"{year}-{month:02d}-{day:02d}"
                except (ValueError, IndexError):
                    continue

        # 패턴 2: "오늘", "최신", "어제"
        if "오늘" in query:
            return today.strftime("%Y-%m-%d")
        if "어제" in query:
            return (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

        return None

    def retrieve(self, query, top_k=5, use_multi_vector=True, agent_filter=None):
        """
        질문과 관련된 상위 K개 문서 검색
        use_multi_vector=True 시 Summary 검색 후 Raw Fetch 수행
        """
        try:
            # 쿼리 검증
            if not query or not query.strip():
                print("Empty query provided")
                return []
            
            # 쿼리 정제 (너무 긴 쿼리 제한)
            query = query.strip()[:500]

            # 날짜 추출 시도
            extracted_date = self._extract_date_from_query(query)
            date_filter = {"업로드일자": extracted_date} if extracted_date else None

            # 쿼리 성격 분석 (거시적/전략적 질문 여부)
            is_strategic_query = any(word in query for word in ["방법", "방식", "타이밍", "접근", "전략", "어떻게", "언제", "매수법"])
            if is_strategic_query:
                print(f"  [RAG] 전략적 쿼리 감지. 검색 범위를 확장합니다. (top_k {top_k} -> {top_k * 2})")
                top_k = top_k * 2

            if use_multi_vector:
                print(f"  [RAG] Multi-Vector Retrieval ({VECTOR_DB_TYPE}): searching summaries...")
                
                if VECTOR_DB_TYPE == "pinecone":
                    # 1. 1차 검색 (일반적으로 수행)
                    results = self.vector_store.search_summaries(query, k=top_k, date_filter=date_filter)
                    
                    # 2. 전략적 쿼리라면 'MARKET' 태그를 포함한 정보 추가 검색 (하이브리드 보완)
                    if is_strategic_query:
                        market_results = self.vector_store.search_summaries(query, k=3, ticker="MARKET")
                        # 중복 제거하며 합치기
                        existing_ids = {r['id'] for r in results}
                        for mr in market_results:
                            if mr['id'] not in existing_ids:
                                results.append(mr)
                    
                    # 원문 일괄 fetch (문서당 1회 왕복 → 전체 1회)
                    doc_ids = [r['metadata'].get('doc_id') for r in results if r['metadata'].get('doc_id')]
                    raw_map = self.vector_store.get_raw_texts(doc_ids)
                    final_docs = []
                    for res in results:
                        doc_id = res['metadata'].get('doc_id')
                        raw_text = raw_map.get(doc_id, '') if doc_id else ''
                        res['page_content'] = raw_text if raw_text else res.get('text', '')
                        final_docs.append(res)
                else:
                    # ChromaDB 검색
                    results = self.vector_store.search_summaries(query, k=top_k, date_filter=date_filter)
                    final_docs = []
                    for res in results:
                        doc_id = res['metadata'].get('doc_id')
                        if doc_id:
                            raw_text = self.vector_store.get_raw_by_doc_id(doc_id)
                            res['page_content'] = raw_text if raw_text else res['page_content']
                        final_docs.append(res)
                
                # 결과가 없을 경우 date_filter 제거 후 재검색 시도
                if not final_docs and date_filter:
                    print(f"  [RAG] No results with date_filter {date_filter}. Retrying without date_filter...")
                    if VECTOR_DB_TYPE == "pinecone":
                        results = self.vector_store.search_summaries(query, k=top_k)
                        doc_ids = [r['metadata'].get('doc_id') for r in results if r['metadata'].get('doc_id')]
                        raw_map = self.vector_store.get_raw_texts(doc_ids)
                        for res in results:
                            doc_id = res['metadata'].get('doc_id')
                            raw_text = raw_map.get(doc_id, '') if doc_id else ''
                            res['page_content'] = raw_text if raw_text else res.get('text', '')
                            final_docs.append(res)
                    else:
                        results = self.vector_store.search_summaries(query, k=top_k)
                        for res in results:
                            doc_id = res['metadata'].get('doc_id')
                            if doc_id:
                                raw_text = self.vector_store.get_raw_by_doc_id(doc_id)
                                res['page_content'] = raw_text if raw_text else res['page_content']
                            final_docs.append(res)

                if not final_docs:
                    print(f"  [RAG] No Multi-Vector results in {VECTOR_DB_TYPE}.")
                    return []
                
                return final_docs

            # 하위 호환성: 기존 youtube_transcripts 컬렉션 검색
            print(f"  [RAG] Standard Retrieval: searching legacy transcripts...")
            raw_results = self.vector_store.search(query, top_k=top_k, filter_metadata=date_filter)
            
            formatted_docs = []
            if raw_results and raw_results.get('documents') and raw_results['documents'][0]:
                for i in range(len(raw_results['documents'][0])):
                    formatted_docs.append({
                        'page_content': raw_results['documents'][0][i],
                        'metadata': raw_results['metadatas'][0][i] if raw_results.get('metadatas') else {},
                        'distance': raw_results['distances'][0][i] if raw_results.get('distances') else 1.0
                    })
            return formatted_docs

        except Exception as e:
            print(f"Error in retrieve: {type(e).__name__} - {str(e)}")
            return []

    def _evaluate_documents(self, query: str, context_docs: list) -> str:
        """
        검색된 문서들이 사용자 질문에 답하기 적합한지 평가 (CRAG)
        Returns: "정확함", "모호함", "무관함" 중 하나
        """
        if not context_docs:
            return "무관함"
            
        context_text = ""
        for i, doc in enumerate(context_docs[:3]):  # 상위 3개만 평가
            content = doc.get('page_content', '') if isinstance(doc, dict) else (doc.page_content if hasattr(doc, 'page_content') else '')
            context_text += f"[문서 {i+1}]\n{content[:500]}\n\n"
            
        system_prompt = """당신은 '문서 평가자(Grader)'입니다. 
제공된 [문서]들이 사용자의 [질문]에 답변하는 데 얼마나 유용한지 평가하세요.
평가 기준:
- 정확함: 문서에 질문에 직답할 수 있는 핵심 정보가 충분히 포함됨. (일부 정보만 있어도 정확함으로 판정하여 기존 정보를 최대한 활용)
- 모호함: 관련된 단어나 맥락은 있으나, 직접적인 답변을 하기에는 정보가 다소 부족함.
- 무관함: 문서가 질문과 전혀 관련이 없거나, 전혀 다른 주식/시황을 이야기하고 있음.

아래 JSON 형식으로만 답변하세요:
{
  "score": "정확함" | "모호함" | "무관함",
  "reason": "평가 사유 (1문장)"
}"""
        user_prompt = f"[질문]\n{query}\n\n[문서]\n{context_text}"
        
        try:
            response = self.openai_client.chat.completions.create(
                model=LLM_MODEL_DEFAULT,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            import json
            result = json.loads(response.choices[0].message.content)
            score = result.get('score', '모호함')
            print(f"  [CRAG] 문서 평가 결과: {score} ({result.get('reason', '')})")
            return score
        except Exception as e:
            print(f"  [CRAG] 문서 평가 실패: {e}")
            return "정확함" # 오류 시 기존 파이프라인 유지

    def _web_search_fallback(self, query: str) -> list:
        """
        DuckDuckGo 웹 검색을 통한 백업 플랜
        """
        print("  [CRAG] 백업 플랜(웹 검색) 가동...")
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                # 검색 품질 향상을 위해 쿼리 구성
                search_query = f"{query} 주식 경제 뉴스"
                results = list(ddgs.news(search_query, region='kr-kr', max_results=3))
                
                fallback_docs = []
                for res in results:
                    fallback_docs.append({
                        'page_content': f"[웹 검색 결과] {res.get('title', '')}\n{res.get('body', '')}",
                        'metadata': {
                            '영상제목': f"웹 검색: {res.get('title', '')}",
                            '채널명': "DuckDuckGo 뉴스 검색",
                            '영상링크': res.get('url', ''),
                            '업로드일자': datetime.date.today().strftime('%Y-%m-%d'),
                        },
                        'distance': 0.1
                    })
                return fallback_docs
        except ImportError:
            print("  [CRAG] duckduckgo-search 모듈이 설치되지 않았습니다. 'pip install duckduckgo-search'가 필요합니다.")
            return []
        except Exception as e:
            print(f"  [CRAG] 웹 검색 실패: {e}")
            return []
    
    def generate_answer(self, query, context_docs, temperature=0.7, conversation_history=None, extra_context=""):
        """
        검색된 문서를 바탕으로 답변 생성
        Args:
            query: 사용자 질문
            context_docs: 검색 결과 리스트
            temperature: AI 응답의 창의성 (0~1)
            conversation_history: 이전 대화 히스토리
            extra_context: 추가로 LLM에 전달할 정보 (예: 보유 종목 현황)
        Returns:
            str: AI 답변
        """
        if not context_docs:
            return "죄송합니다. 관련 정보를 찾지 못했습니다."

        # 컨텍스트 구성
        context_text = ""
        sources = []
        for i, doc in enumerate(context_docs, 1):
            if isinstance(doc, dict):
                content = doc.get('page_content', '')
                m = doc.get('metadata', {})
            elif hasattr(doc, 'page_content'):
                content = doc.page_content
                m = doc.metadata
            else:
                continue

            ts_url = m.get('timestamp_url', m.get('영상링크', 'URL 없음'))
            rel_stocks = m.get('related_stocks', '')
            
            context_text += f"[문서 {i}] (채널: {m.get('채널명','?')}, 종목: {m.get('ticker','?')}, 날짜: {m.get('업로드일자','?')})\n{content}\n\n"
            
            source_info = f"- {m.get('영상제목','영상')} ({m.get('업로드일자','?')}) "
            if rel_stocks:
                source_info += f"[연관: {rel_stocks}] "
            source_info += f"\n  링크: {ts_url}"
            
            if source_info not in sources:
                sources.append(source_info)

        system_prompt = f"""당신은 전문 주식 분석가이자 투자 어시스턴트입니다.
제공된 [참고 문서]들의 내용을 바탕으로 사용자의 질문에 깊이 있는 답변을 작성하세요.

**답변 원칙**:
1. **질문에 직접 답하기**: 첫 문단에서 질문에 대한 핵심 결론부터 제시하고, 그 다음 근거를 풀어가세요. 자문자답(Q&A) 형식은 금지합니다.
2. **풍부하고 구체적인 분석**: 문서에 등장하는 핵심 논거, 목표가, 매매 시나리오, 긍정/부정적 요인을 논리적으로 서술하세요. 핵심 항목은 불릿 포인트를 활용해 읽기 쉽게.
3. **시점 명시**: 유튜버 발언은 영상 날짜 기준 과거 시점의 의견입니다. "X월 X일 영상에서 ~라고 했다"처럼 시점을 밝혀, 현재 사실처럼 들리지 않게 하세요.
4. **다각도 비교**: 여러 문서에서 상충되거나 보완되는 의견이 있다면 비교 대조하세요.
5. **근거 중심**: 문서에 없는 수치나 사실을 지어내지 마세요. 각 주요 주장 뒤에 근거 문서 번호(예: [1], [2])를 기재하세요.
6. **솔직함**: 관련 내용이 문서에 없다면 "제공된 정보 내에서는 확인할 수 없습니다"라고 명확히 안내하세요.

오늘 날짜: {datetime.date.today().strftime('%Y-%m-%d')}
"""
        
        user_prompt = f"{extra_context}\n\n질문: {query}\n\n[참고 문서]\n{context_text}"

        try:
            response = self.openai_client.chat.completions.create(
                model=LLM_MODEL_SMART,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature  # 파라미터로 전달받은 온도 사용
            )
            
            answer = response.choices[0].message.content
            # UI의 st.expander에서 소스 목록을 별도로 렌더링하므로, 텍스트 답변에는 소스 원문을 직접 붙이지 않습니다.
            return answer

        except Exception as e:
            print(f"Error generating answer: {e}")
            return "답변 생성 중 오류가 발생했습니다."
    
    def generate_followup_questions(self, query: str, answer: str, temperature=0.7):
        """
        답변 기반 후속 질문 3개 생성
        Args:
            query: 원래 질문
            answer: AI 답변
            temperature: AI 응답의 창의성
        Returns:
            list: 후속 질문 리스트 (최대 3개)
        """
        try:
            system_prompt = """너는 투자자의 궁금증을 예측하는 전문가야.

사용자의 질문과 AI 답변을 보고, 사용자가 **추가로 궁금해할 만한 질문 3개**를 생성해줘.

**주의**: 만약 답변 내용이 "정보를 찾지 못했다"거나 "직접적인 정보가 없다"는 내용이라면, 사용자가 대안으로 물어볼 수 있는 **우리 시스템(주식 분석/RAG)이 대답 가능한 가장 유사한 질문** 3개를 추천해줘.
(예: 엔비디아 배당금 정보를 못 찾았다면 -> "엔비디아 최근 실적", "엔비디아 향후 성장성 전망", "엔비디아 기술적 분석 결과" 등)

**형식**: 질문만 한 줄씩 출력 (번호 없이)"""

            user_prompt = f"""[원래 질문]
{query}

[AI 답변]
{answer[:500]}...

위 내용을 바탕으로 후속 질문 3개를 생성해줘."""

            response = self.openai_client.chat.completions.create(
                model=LLM_MODEL_DEFAULT,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
                max_tokens=150
            )
            
            # 응답을 줄 단위로 분리하여 질문 추출
            questions_text = response.choices[0].message.content.strip()
            questions = [q.strip() for q in questions_text.split('\n') if q.strip()]
            
            # 최대 3개만 반환
            return questions[:3]
            
        except Exception as e:
            print(f"Error generating follow-up questions: {str(e)}")
            return []
    
    def chat(self, query, top_k=10, temperature=0.7, agent_filter=None, conversation_history=None, extra_context=""):
        """
        RAG 전체 파이프라인: 검색 + CRAG 평가 + 답변 생성 + 후속 질문 제안
        """
        try:
            # 1. 관련 문서 검색 (Multi-Vector 모드 사용)
            retrieved_docs = self.retrieve(query, top_k=top_k, use_multi_vector=True, agent_filter=agent_filter)
            
            # --- CRAG 평가 단계 ---
            evaluation_score = self._evaluate_documents(query, retrieved_docs)
            
            if evaluation_score == "무관함":
                # 무관할 경우 기존 문서를 폐기하고 웹 검색 결과로 대체
                retrieved_docs = self._web_search_fallback(query)
            elif evaluation_score == "모호함":
                # 모호할 경우 기존 문서를 유지하면서 웹 검색 결과를 추가 보완
                web_docs = self._web_search_fallback(query)
                retrieved_docs.extend(web_docs)
                
            if not retrieved_docs:
                fallback_msg = "죄송합니다. 현재 보관된 영상 자막과 최신 뉴스 내에서는 해당 질문에 대한 직접적인 정보를 찾기 어렵습니다."
                return {
                    'answer': fallback_msg,
                    'sources': [],
                    'followup_questions': self.generate_followup_questions(query, fallback_msg, temperature)
                }
            
            # 2. 답변 생성 (대화 히스토리 및 추가 컨텍스트 포함)
            answer = self.generate_answer(query, retrieved_docs, temperature, conversation_history, extra_context)
            
            # 3. 소스 정보 정리
            sources = []
            for doc in retrieved_docs:
                meta = doc['metadata']
                # Pinecone은 score(유사도), ChromaDB는 distance(거리)를 반환
                sim = doc.get('score')
                if sim is None:
                    sim = 1 - doc.get('distance', 1.0)
                sources.append({
                    '영상제목': meta.get('영상제목', 'N/A'),
                    '채널명': meta.get('채널명', 'N/A'),
                    '영상링크': meta.get('영상링크', 'N/A'),
                    '업로드일자': meta.get('업로드일자', 'N/A'),
                    '유사도': round(float(sim), 3)
                })
            
            # 4. 후속 질문 생성
            followup_questions = self.generate_followup_questions(query, answer, temperature)
            
            return {
                'answer': answer,
                'sources': sources,
                'followup_questions': followup_questions
            }
            
        except Exception as e:
            print(f"Error in chat: {type(e).__name__} - {str(e)}")
            return {
                'answer': f"""오류가 발생했습니다.

**오류 정보**: {type(e).__name__}

다시 시도해주시거나, 질문을 다르게 표현해보세요.""",
                'sources': [],
                'followup_questions': []
            }


if __name__ == "__main__":
    # 테스트 코드
    engine = RAGEngine()
    
    # 샘플 질문
    test_query = "삼성전자 주가 전망은?"
    
    print(f"질문: {test_query}\n")
    result = engine.chat(test_query, top_k=3)
    
    print("=== 답변 ===")
    print(result['answer'])
    
    print("\n=== 참고 소스 ===")
    for i, source in enumerate(result['sources']):
        print(f"\n[{i+1}] {source['영상제목']}")
        print(f"    채널: {source['채널명']}")
        print(f"    링크: {source['영상링크']}")
        print(f"    유사도: {source['유사도']}")
