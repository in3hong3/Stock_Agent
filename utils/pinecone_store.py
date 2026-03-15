"""
Pinecone 벡터 스토어 관리 모듈
ChromaDB 대신 Pinecone 클라우드를 사용하여 데이터를 영구 저장하고 검색합니다.
"""
import os
import time
import logging
from typing import List, Dict, Any, Optional
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI
from dotenv import load_dotenv

from config.settings import (
    PINECONE_API_KEY,
    PINECONE_INDEX_NAME,
    PINECONE_NAMESPACE_SUMMARY,
    PINECONE_NAMESPACE_RAW,
    EMBEDDING_MODEL
)

load_dotenv()
logger = logging.getLogger(__name__)

class PineconeStore:
    """Pinecone 벡터 스토어 관리 클래스"""
    
    def __init__(self, index_name: str = PINECONE_INDEX_NAME):
        self.api_key = PINECONE_API_KEY
        if not self.api_key:
            raise ValueError("PINECONE_API_KEY not found in environment variables")
        
        self.index_name = index_name
        
        # OpenAI 클라이언트 초기화
        self.openai_client = OpenAI()
        
        # Pinecone 클라이언트 초기화
        self.pc = Pinecone(api_key=self.api_key)
        
        # 인덱스 존재 확인 및 생성 (없을 경우)
        if self.index_name not in self.pc.list_indexes().names():
            logger.info(f"Creating new Pinecone index: {self.index_name}")
            self.pc.create_index(
                name=self.index_name,
                dimension=1536, # text-embedding-3-small
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
            # 인덱스가 준비될 때까지 대기
            while not self.pc.describe_index(self.index_name).status['ready']:
                time.sleep(1)
        
        self.index = self.pc.Index(self.index_name)
        logger.info(f"Connected to Pinecone index: {self.index_name}")

    def get_embedding(self, text: str) -> List[float]:
        """OpenAI API를 사용하여 텍스트 임베딩 생성"""
        # Pinecone은 리스트 형태의 텍스트도 받을 수 있지만, 현재는 단일 텍스트 처리
        response = self.openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding

    def upsert_documents(
        self, 
        ids: List[str], 
        embeddings: List[List[float]], 
        metadatas: List[Dict[str, Any]], 
        namespace: str
    ):
        """문서 벡터를 Pinecone에 업로드 (Upsert)"""
        vectors = []
        for i in range(len(ids)):
            vectors.append({
                "id": ids[i],
                "values": embeddings[i],
                "metadata": metadatas[i]
            })
        
        # 100개씩 나눠서 업로드 (Batching)
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            self.index.upsert(vectors=batch, namespace=namespace)
        
        logger.info(f"Upserted {len(ids)} vectors to namespace: {namespace}")

    def add_json_documents_v2(self, json_data_list: List[Dict], metadatas: List[Dict]):
        """
        Multi-Vector Retriever 패턴으로 데이터 저장
        - Namespace: stock-summaries (요약본)
        - Namespace: stock-raw-chunks (원본 자막)
        """
        summary_ids, summary_embeddings, summary_metas = [], [], []
        raw_ids, raw_embeddings, raw_metas = [], [], []

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
                meta.update({'doc_id': doc_id, 'ticker': 'MARKET', 'text': chunk_text})
                
                summary_ids.append(doc_id)
                summary_embeddings.append(emb)
                summary_metas.append(meta)
                continue

            for j, stock in enumerate(stocks):
                ticker = stock.get('ticker', 'UNKNOWN')
                ticker_clean = ticker.replace('.', '_').replace('-', '_')
                
                # Pinecone ID는 ASCII 문자만 허용 (한글 티커/종목명 에러 방지)
                import urllib.parse
                ticker_safe = urllib.parse.quote(ticker_clean)
                doc_id = f"{video_id}_{ticker_safe}_{j}"
                
                stock_name = stock.get('name', 'Unknown')
                video_title = base_metadata.get('영상제목', 'Unknown Title')
                
                # 핵심 논지
                core_thesis = stock.get('core_thesis', [])
                thesis_text = "\n".join([f"- {t}" for t in core_thesis]) if core_thesis else stock.get('reasoning', '')

                # 1. 요약본 (Summary)
                rels = stock.get('relationships', [])
                rel_parts = [f"{r.get('related_company')} ({r.get('relation_type')})" for r in rels if r.get('related_company')]
                related_stocks_str = ", ".join(rel_parts)
                
                summary_text = (
                    f"[영상: {video_title}]\n"
                    f"[종목: {stock_name} ({ticker})]\n"
                    f"관점: {stock.get('sentiment','중립')}\n"
                    f"핵심 요약: {thesis_text}\n"
                    f"연관/수혜 종목(GraphRAG): {related_stocks_str}\n"
                    f"매매 전략: {stock.get('trading_strategy', '')}"
                )
                
                # 2. 원문 (Raw)
                raw_text = stock.get('raw_text')
                if not raw_text and raw_chunks:
                    # 백업 로직
                    source_ids = stock.get('source_chunk_ids', [])
                    parts = [f"[{raw_chunks[c]['start_time']:.0f}s] {raw_chunks[c]['text']}" 
                             for c in source_ids if c in raw_chunks]
                    raw_text = "\n".join(parts) if parts else summary_text
                
                # Context Header 추가
                raw_text_with_context = f"[영상: {video_title}]\n[종목: {stock_name}]\n\n{raw_text}"

                # 타임스탬프 링크
                ts = stock.get('timestamp')
                timestamp_url = f"{video_url}&t={int(ts)}s" if ts else video_url

                # 요약본 저장 준비
                s_meta = base_metadata.copy()
                s_meta.update({
                    'doc_id': doc_id,
                    'ticker': ticker,
                    'sentiment': stock.get('sentiment', '중립'),
                    'timestamp_url': timestamp_url,
                    'related_stocks': related_stocks_str, # GraphRAG 필드
                    'text': summary_text # Pinecone은 원문을 메타데이터에 저장하는 것이 검색 후 활용에 좋음
                })
                summary_ids.append(doc_id)
                summary_embeddings.append(self.get_embedding(summary_text))
                summary_metas.append(s_meta)

                # 원문 저장 준비
                r_meta = base_metadata.copy()
                r_meta.update({
                    'doc_id': doc_id,
                    'ticker': ticker,
                    'text': raw_text_with_context
                })
                raw_ids.append(doc_id)
                raw_embeddings.append(self.get_embedding(raw_text_with_context[:8000]))
                raw_metas.append(r_meta)

        # Upsert 실행
        if summary_ids:
            self.upsert_documents(summary_ids, summary_embeddings, summary_metas, PINECONE_NAMESPACE_SUMMARY)
        if raw_ids:
            self.upsert_documents(raw_ids, raw_embeddings, raw_metas, PINECONE_NAMESPACE_RAW)

    def search_summaries(self, query: str, k: int = 5, ticker: Optional[str] = None, date_filter: Optional[Dict] = None) -> List[Dict]:
        """요약본 레이어에서 검색"""
        qe = self.get_embedding(query)
        
        filter_dict = {}
        if ticker:
            filter_dict["ticker"] = ticker
            
        if date_filter and '업로드일자' in date_filter:
            # ex: date_filter = {"업로드일자": "2026-02-26"}
            filter_dict["업로드일자"] = date_filter["업로드일자"]

        results = self.index.query(
            vector=qe,
            top_k=k,
            namespace=PINECONE_NAMESPACE_SUMMARY,
            filter=filter_dict if filter_dict else None,
            include_metadata=True
        )
        
        formatted_results = []
        for match in results.get('matches', []):
            formatted_results.append({
                'id': match.get('id'),
                'score': match.get('score'),
                'metadata': match.get('metadata', {}),
                'text': match.get('metadata', {}).get('text', '')
            })
        return formatted_results

    def get_raw_text(self, doc_id: str) -> str:
        """doc_id로 원본 텍스트 가져오기"""
        result = self.index.fetch(ids=[doc_id], namespace=PINECONE_NAMESPACE_RAW)
        if doc_id in result['vectors']:
            return result['vectors'][doc_id]['metadata'].get('text', '')
        return ""

    def delete_all(self):
        """인덱스의 모든 데이터 삭제 (초기화용)"""
        self.index.delete(delete_all=True, namespace=PINECONE_NAMESPACE_SUMMARY)
        self.index.delete(delete_all=True, namespace=PINECONE_NAMESPACE_RAW)
        logger.info("Deleted all vectors from Pinecone index namespaces.")
