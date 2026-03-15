"""
ChromaDB 벡터 스토어 관리 모듈
YouTube 요약 데이터를 임베딩하여 저장하고 검색합니다.
"""
import os
import chromadb
from chromadb.config import Settings
from openai import OpenAI
from dotenv import load_dotenv

from config.settings import (
    CHROMA_DB_PATH, 
    COLLECTION_NAME, 
    SUMMARY_COLLECTION_NAME, 
    RAW_COLLECTION_NAME,
    EMBEDDING_MODEL
)

load_dotenv()


class VectorStore:
    """ChromaDB 벡터 스토어 관리 클래스"""
    
    def __init__(self, collection_name=COLLECTION_NAME, persist_directory=CHROMA_DB_PATH):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        
        # OpenAI 클라이언트 초기화
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        self.openai_client = OpenAI(api_key=api_key)
        
        # ChromaDB 클라이언트 초기화
        self.client = chromadb.PersistentClient(path=persist_directory)
        
        # [기존] 메인 컬렉션 (하위 호환성 유지)
        try:
            self.collection = self.client.get_collection(name=collection_name)
            print(f"Loaded existing collection: {collection_name}")
        except:
            self.collection = self.client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            print(f"Created new collection: {collection_name}")
        
        # [신규] Multi-Vector Retriever용 컬렉션 2개
        try:
            self.summary_collection = self.client.get_collection(name=SUMMARY_COLLECTION_NAME)
            print(f"Loaded existing collection: {SUMMARY_COLLECTION_NAME}")
        except:
            self.summary_collection = self.client.create_collection(
                name=SUMMARY_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"}
            )
            print(f"Created new collection: {SUMMARY_COLLECTION_NAME}")
        
        try:
            self.raw_collection = self.client.get_collection(name=RAW_COLLECTION_NAME)
            print(f"Loaded existing collection: {RAW_COLLECTION_NAME}")
        except:
            self.raw_collection = self.client.create_collection(
                name=RAW_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"}
            )
            print(f"Created new collection: {RAW_COLLECTION_NAME}")
    
    def get_embedding(self, text):
        """
        OpenAI API를 사용하여 텍스트 임베딩 생성
        Args:
            text: 임베딩할 텍스트
        Returns:
            list: 임베딩 벡터
        """
        response = self.openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding
    
    def chunk_text(self, text, chunk_size=1000, overlap=200):
        """
        텍스트를 청크로 분할
        Args:
            text: 분할할 텍스트
            chunk_size: 청크 크기 (문자 수)
            overlap: 청크 간 겹침 크기
        Returns:
            list: 청크 리스트
        """
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            
            # 마지막 청크가 너무 작으면 이전 청크와 합침
            if end >= len(text):
                chunks.append(text[start:])
                break
            
            # 문장 경계에서 자르기 (마침표, 느낌표, 물음표)
            chunk = text[start:end]
            last_period = max(
                chunk.rfind('.'),
                chunk.rfind('!'),
                chunk.rfind('?'),
                chunk.rfind('\n')
            )
            
            if last_period > chunk_size * 0.5:  # 청크의 절반 이상이면 그곳에서 자름
                end = start + last_period + 1
            
            chunks.append(text[start:end])
            start = end - overlap  # 겹침 적용
        
        return chunks
    
    def add_json_documents(self, json_data_list, metadatas):
        """
        JSON 구조화 데이터를 종목별로 청킹하여 벡터 DB에 추가 (NEW)
        Args:
            json_data_list: TranscriptProcessor에서 생성된 JSON 데이터 리스트
            metadatas: 기본 메타데이터 (영상제목, 채널명, 업로드일자, 영상링크)
        """
        all_chunks = []
        all_embeddings = []
        all_metadatas = []
        all_ids = []
        
        for i, (json_data, base_metadata) in enumerate(zip(json_data_list, metadatas)):
            stocks = json_data.get('stocks', [])
            market_context = json_data.get('market_context', '')
            summary = json_data.get('summary', '')
            
            if not stocks:
                # 종목 정보가 없으면 전체 요약만 저장
                chunk_text = f"시장 상황: {market_context}\n\n요약: {summary}"
                embedding = self.get_embedding(chunk_text)
                
                chunk_metadata = base_metadata.copy()
                chunk_metadata['ticker'] = 'MARKET'
                chunk_metadata['sentiment'] = '중립'
                chunk_metadata['has_metrics'] = False
                
                video_id = base_metadata.get('영상링크', f'doc_{i}').split('=')[-1]
                chunk_id = f"{video_id}_market"
                
                all_chunks.append(chunk_text)
                all_embeddings.append(embedding)
                all_metadatas.append(chunk_metadata)
                all_ids.append(chunk_id)
                
                print(f"Document {i+1}: 1 market chunk (no stocks)")
                continue
            
            # 종목별로 청크 생성
            for j, stock in enumerate(stocks):
                # 청크 텍스트 구성 (검색 최적화 + 상세 분석)
                
                # 핵심 논지 포맷팅
                core_thesis = stock.get('core_thesis', [])
                thesis_text = "\n".join([f"  - {t}" for t in core_thesis]) if core_thesis else stock.get('reasoning', '')
                
                # 매매 전략
                trading_strategy = stock.get('trading_strategy', '')
                
                # 리스크 요인
                risk_factors = stock.get('risk_factors', [])
                risk_text = "\n".join([f"  - {r}" for r in risk_factors]) if risk_factors else "언급 없음"
                
                chunk_text = f"""{stock.get('name', 'Unknown')} ({stock.get('ticker', 'N/A')}) 투자 분석

관점: {stock.get('sentiment', '중립')}

핵심 논지:
{thesis_text}

주요 지표:
{self._format_metrics(stock.get('key_metrics', {}))}

매매 전략:
{trading_strategy if trading_strategy else '구체적 전략 언급 없음'}

리스크 요인:
{risk_text}

시장 맥락: {market_context}

영상 요약: {summary}
"""
                
                embedding = self.get_embedding(chunk_text)
                
                # 메타데이터 구성
                chunk_metadata = base_metadata.copy()
                chunk_metadata['ticker'] = stock.get('ticker', 'UNKNOWN')
                chunk_metadata['stock_name'] = stock.get('name', 'Unknown')
                chunk_metadata['sentiment'] = stock.get('sentiment', '중립')
                chunk_metadata['has_metrics'] = bool(stock.get('key_metrics'))
                chunk_metadata['chunk_index'] = j
                chunk_metadata['total_chunks'] = len(stocks)
                
                # ID 생성
                video_id = base_metadata.get('영상링크', f'doc_{i}').split('=')[-1]
                ticker_clean = stock.get('ticker', 'UNK').replace('.', '_').replace('-', '_')
                chunk_id = f"{video_id}_{ticker_clean}_{j}"
                
                all_chunks.append(chunk_text)
                all_embeddings.append(embedding)
                all_metadatas.append(chunk_metadata)
                all_ids.append(chunk_id)
            
            print(f"Document {i+1}: {len(stocks)} stock chunks created")
        
        # ChromaDB에 추가
        if all_chunks:
            self.collection.add(
                embeddings=all_embeddings,
                documents=all_chunks,
                metadatas=all_metadatas,
                ids=all_ids
            )
            print(f"Added {len(all_chunks)} chunks from {len(json_data_list)} documents to the collection")
    
    def _format_metrics(self, metrics: dict) -> str:
        """
        key_metrics 딕셔너리를 읽기 쉬운 텍스트로 변환
        """
        if not metrics:
            return "  구체적 수치 정보 없음"
        
        formatted = []
        for key, value in metrics.items():
            # 리스트인 경우 (예: entry_zone)
            if isinstance(value, list):
                value_str = " ~ ".join(str(v) for v in value)
                formatted.append(f"  - {key}: {value_str}")
            else:
                formatted.append(f"  - {key}: {value}")
        return "\n".join(formatted)

    
    def add_documents(self, documents, metadatas, ids=None):
        """
        문서를 청크로 분할하여 벡터 DB에 추가 (LEGACY - 하위 호환성)
        
        새로운 코드는 add_json_documents() 사용 권장
        
        Args:
            documents: 문서 텍스트 리스트
            metadatas: 메타데이터 딕셔너리 리스트 (채널명, 제목, 링크 등)
            ids: 문서 ID 리스트 (선택사항, 자동 생성됨)
        """
        all_chunks = []
        all_embeddings = []
        all_metadatas = []
        all_ids = []
        
        for i, (doc, metadata) in enumerate(zip(documents, metadatas)):
            # 텍스트 청킹
            chunks = self.chunk_text(doc, chunk_size=1500, overlap=300)
            
            print(f"Document {i+1}: {len(chunks)} chunks created (legacy mode)")
            
            for j, chunk in enumerate(chunks):
                # 임베딩 생성
                embedding = self.get_embedding(chunk)
                
                # 메타데이터에 청크 정보 추가
                chunk_metadata = metadata.copy()
                chunk_metadata['chunk_index'] = j
                chunk_metadata['total_chunks'] = len(chunks)
                chunk_metadata['chunking_method'] = 'legacy'  # 구분용
                
                # ID 생성 (영상링크_청크번호)
                video_id = metadata.get('영상링크', f'doc_{i}').split('=')[-1]
                chunk_id = f"{video_id}_chunk_{j}"
                
                all_chunks.append(chunk)
                all_embeddings.append(embedding)
                all_metadatas.append(chunk_metadata)
                all_ids.append(chunk_id)
        
        # ChromaDB에 추가
        if all_chunks:
            self.collection.add(
                embeddings=all_embeddings,
                documents=all_chunks,
                metadatas=all_metadatas,
                ids=all_ids
            )
            print(f"Added {len(all_chunks)} chunks from {len(documents)} documents to the collection")
    
    def search(self, query, top_k=5, filter_metadata=None, agent_filter=None):
        """
        유사도 기반 검색
        Args:
            query: 검색 쿼리
            top_k: 반환할 결과 개수
            filter_metadata: 메타데이터 필터 (예: {"채널명": "특정채널"})
            agent_filter: 에이전트 ID 리스트로 필터링 (현재 비활성화)
        Returns:
            dict: 검색 결과 (documents, metadatas, distances)
        """
        # 쿼리 임베딩 생성
        query_embedding = self.get_embedding(query)
        
        # 에이전트 필터 처리 - 현재 비활성화
        # 문제: agent_info['name']은 "올랜도킴"이지만 DB의 채널명은 "올랜도 킴 미국주식"
        # TODO: AGENT_REGISTRY에 실제 채널명 필드 추가 필요
        # if agent_filter:
        #     from config.settings import AGENT_REGISTRY
        #     channel_names = []
        #     for agent_id in agent_filter:
        #         agent_info = AGENT_REGISTRY.get(agent_id)
        #         if agent_info and agent_info.get('name'):
        #             channel_names.append(agent_info['name'])
        #     
        #     if channel_names:
        #         if filter_metadata is None:
        #             filter_metadata = {}
        #         filter_metadata["채널명"] = {"$in": channel_names}
        
        # 검색 수행
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter_metadata
        )
        
        return results
    
    def hybrid_search(self, query, top_k=5, channel_filter=None, date_filter=None):
        """
        하이브리드 검색 (벡터 검색 + 메타데이터 필터링)
        Args:
            query: 검색 쿼리
            top_k: 반환할 결과 개수
            channel_filter: 채널명 필터
            date_filter: 날짜 필터
        Returns:
            dict: 검색 결과
        """
        filter_dict = {}
        
        if channel_filter:
            filter_dict["채널명"] = channel_filter
        
        # 날짜 필터는 ChromaDB에서 직접 지원하지 않으므로 
        # 검색 후 필터링하거나 메타데이터에 날짜 범주를 추가해야 함
        
        return self.search(query, top_k, filter_metadata=filter_dict if filter_dict else None)
    
    # =========================================================================
    # Multi-Vector Retriever 패턴 (신규)
    # =========================================================================

    def add_json_documents_v2(self, json_data_list, metadatas):
        """
        Multi-Vector Retriever 패턴으로 데이터 저장
        - stock_summaries: 종목별 요약본 (빠른 벡터 검색용)
        - stock_raw_chunks: 원본 자막 텍스트 (LLM 답변 생성용)
        doc_id = "{video_id}_{ticker}_{j}" 가 두 컬렉션을 연결하는 핵심 키
        """
        summary_chunks, summary_embeddings, summary_metadatas, summary_ids = [], [], [], []
        raw_docs, raw_embeddings, raw_metadatas, raw_ids = [], [], [], []

        for i, (json_data, base_metadata) in enumerate(zip(json_data_list, metadatas)):
            stocks = json_data.get('stocks', [])
            market_context = json_data.get('market_context', '')
            summary = json_data.get('summary', '')
            raw_chunks = json_data.get('raw_chunks', {})

            video_url = base_metadata.get('영상링크', f'doc_{i}')
            video_id = video_url.split('=')[-1] if '=' in video_url else f'doc_{i}'

            if not stocks:
                doc_id = f"{video_id}_MARKET"
                chunk_text = f"시장 상황: {market_context}\n\n요약: {summary}"
                emb = self.get_embedding(chunk_text)
                meta = base_metadata.copy()
                meta.update({'doc_id': doc_id, 'ticker': 'MARKET', 'related_stocks': '', 'timestamp_url': video_url})
                summary_chunks.append(chunk_text)
                summary_embeddings.append(emb)
                summary_metadatas.append(meta)
                summary_ids.append(doc_id + "_summary")
                continue

            for j, stock in enumerate(stocks):
                ticker = stock.get('ticker', 'UNKNOWN')
                ticker_clean = ticker.replace('.', '_').replace('-', '_')
                doc_id = f"{video_id}_{ticker_clean}_{j}"

                # 1. 요약본(Summary) - 이미 Context Header가 포함된 버전 사용 시도
                summary_text = stock.get('summary')
                
                core_thesis = stock.get('core_thesis', [])
                thesis_text = "\n".join([f"  - {t}" for t in core_thesis]) if core_thesis else stock.get('reasoning', '')
                
                if not summary_text:
                    summary_text = (
                        f"관점: {stock.get('sentiment','중립')}\n"
                        f"핵심 요약: {thesis_text[:300]}...\n"
                        f"주요 지표: {self._format_metrics(stock.get('key_metrics',{}))}"
                    )

                # 2. 원문(Raw Text) - LLM이 정제한 Semantic Segment 우선 사용
                raw_text = stock.get('raw_text')
                if not raw_text:
                    # 백업: 기존 Time-aware Chunking 방식
                    source_ids = stock.get('source_chunk_ids', [])
                    if source_ids and raw_chunks:
                        parts = [
                            f"[{raw_chunks[c]['start_time']:.0f}s~{raw_chunks[c]['end_time']:.0f}s]\n{raw_chunks[c]['text']}"
                            for c in source_ids if c in raw_chunks
                        ]
                        raw_text = "\n\n".join(parts) if parts else summary_text
                    elif raw_chunks:
                        parts = [f"[{v['start_time']:.0f}s~{v['end_time']:.0f}s]\n{v['text']}" for v in raw_chunks.values()]
                        raw_text = "\n\n".join(parts)
                    else:
                        raw_text = summary_text

                # [Feature 1] Contextual Injection 
                # 각 청크의 맨 앞에 [영상 제목, 종목명, 핵심 주제] 강제 병합
                video_title = base_metadata.get('영상제목', 'Unknown Title')
                stock_name = stock.get('name', 'Unknown')
                context_header = f"[영상 제목: {video_title}]\n[다루는 종목명: {stock_name} ({ticker})]\n[핵심 주제: {thesis_text[:100].strip()}]\n\n"
                
                if "[영상 제목" not in summary_text and "[영상:" not in summary_text:
                    summary_text = context_header + summary_text
                
                if "[영상 제목" not in raw_text and "[영상:" not in raw_text:
                    raw_text = context_header + raw_text

                # 타임스탬프 링크
                ts = stock.get('timestamp')
                timestamp_url = f"{video_url}&t={int(ts)}s" if ts and isinstance(ts, (int, float)) else video_url

                s_meta = base_metadata.copy()
                s_meta.update({
                    'doc_id': doc_id, 'ticker': ticker,
                    'stock_name': stock_name,
                    'sentiment': stock.get('sentiment', '중립'),
                    'related_stocks': ",".join(stock.get('related_stocks', [])) if stock.get('related_stocks') else "",
                    'timestamp_url': timestamp_url,
                    'retriever_type': 'summary',
                })

                summary_chunks.append(summary_text)
                summary_embeddings.append(self.get_embedding(summary_text))
                summary_metadatas.append(s_meta)
                summary_ids.append(doc_id + "_summary")

                r_meta = base_metadata.copy()
                r_meta.update({'doc_id': doc_id, 'ticker': ticker, 'timestamp_url': timestamp_url, 'retriever_type': 'raw'})
                raw_docs.append(raw_text)
                raw_embeddings.append(self.get_embedding(raw_text[:8000])) # 임베딩 제한
                raw_metadatas.append(r_meta)
                raw_ids.append(doc_id + "_raw")

            print(f"Document {i+1}: {len(stocks)} stocks -> Contextual Semantic pairs created")

        if summary_chunks:
            self.summary_collection.add(
                embeddings=summary_embeddings, documents=summary_chunks,
                metadatas=summary_metadatas, ids=summary_ids
            )
            print(f"[stock_summaries] Added {len(summary_chunks)} docs")

        if raw_docs:
            self.raw_collection.add(
                embeddings=raw_embeddings, documents=raw_docs,
                metadatas=raw_metadatas, ids=raw_ids
            )
            print(f"[stock_raw_chunks] Added {len(raw_docs)} docs")

    def search_summaries(self, query, k=5, date_filter=None):
        """
        [Feature 3] Hybrid Search: stock_summaries에서 요약본을 벡터 검색 후 BM25로 재랭킹.
        """
        pool_size = max(50, k*3) # 더 넓은 풀에서 검색하여 BM25 적용
        qe = self.get_embedding(query)
        results = self.summary_collection.query(
            query_embeddings=[qe], n_results=pool_size, where=date_filter
        )
        
        docs = []
        if results.get('documents') and results['documents'][0]:
            try:
                from rank_bm25 import BM25Okapi
                
                docs_text = results['documents'][0]
                metadatas = results['metadatas'][0] if results.get('metadatas') else [{}] * len(docs_text)
                distances = results['distances'][0] if results.get('distances') else [1.0] * len(docs_text)
                
                # 토큰화 (단순 공백 기반)
                tokenized_corpus = [doc.lower().split() for doc in docs_text]
                tokenized_query = query.lower().split()
                
                bm25 = BM25Okapi(tokenized_corpus)
                bm25_scores = bm25.get_scores(tokenized_query)
                max_b = max(bm25_scores) if max(bm25_scores) > 0 else 1.0
                
                scored_docs = []
                for i in range(len(docs_text)):
                    v_score = 1.0 - distances[i]
                    b_score = bm25_scores[i] / max_b
                    # 벡터 유사도 60%, 키워드 매칭 40% 가중치
                    combined_score = 0.6 * v_score + 0.4 * b_score
                    
                    scored_docs.append({
                        'page_content': docs_text[i],
                        'metadata': metadatas[i],
                        'distance': distances[i], # original
                        'combined_score': combined_score
                    })
                
                scored_docs.sort(key=lambda x: x['combined_score'], reverse=True)
                docs = scored_docs[:k]
            except ImportError:
                # rank_bm25가 설치 안된 경우 fallback (기존 로직)
                print("  [Hybrid Search] rank_bm25 not found. Using distance only.")
                for i in range(min(k, len(results['documents'][0]))):
                    docs.append({
                        'page_content': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i] if results.get('metadatas') else {},
                        'distance': results['distances'][0][i] if results.get('distances') else 1.0
                    })
        return docs

    def get_raw_by_doc_id(self, doc_id: str) -> str:
        """doc_id로 stock_raw_chunks에서 원본 자막 fetch"""
        try:
            r = self.raw_collection.get(ids=[doc_id + "_raw"], include=['documents'])
            if r and r.get('documents') and r['documents']:
                return r['documents'][0]
        except Exception as e:
            print(f"  [get_raw_by_doc_id] Error: {e}")
        return ""

    def get_summary_collection_count(self) -> int:
        return self.summary_collection.count()

    def get_raw_collection_count(self) -> int:
        return self.raw_collection.count()

    def delete_collection(self):
        """모든 컬렉션 완전 삭제 (재구축 시 사용)"""
        try:
            self.client.delete_collection(name=self.collection_name)
            print(f"Deleted collection: {self.collection_name}")
        except Exception as e:
            pass
        
        try:
            self.client.delete_collection(name=SUMMARY_COLLECTION_NAME)
            print(f"Deleted collection: {SUMMARY_COLLECTION_NAME}")
        except Exception as e:
            pass
            
        try:
            self.client.delete_collection(name=RAW_COLLECTION_NAME)
            print(f"Deleted collection: {RAW_COLLECTION_NAME}")
        except Exception as e:
            pass
    
    def get_collection_count(self):
        """컬렉션의 문서 개수 반환"""
        return self.collection.count()


if __name__ == "__main__":
    # 테스트 코드
    store = VectorStore()
    
    print(f"Collection count: {store.get_collection_count()}")
    
    # 테스트 검색
    if store.get_collection_count() > 0:
        results = store.search("삼성전자 전망", top_k=3)
        print("\n=== Search Results ===")
        for i, (doc, meta) in enumerate(zip(results['documents'][0], results['metadatas'][0])):
            print(f"\n[{i+1}] {meta.get('영상제목', 'N/A')}")
            print(f"채널: {meta.get('채널명', 'N/A')}")
            print(f"요약: {doc[:200]}...")
