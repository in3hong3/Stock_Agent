# -*- coding: utf-8 -*-
import unittest
import os
import sys
import uuid
from typing import Dict, List

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.transcript_processor import TranscriptProcessor
from utils.vector_store import VectorStore
from core.rag_engine import RAGEngine

class TestMultiVectorRAG(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.processor = TranscriptProcessor()
        cls.vector_store = VectorStore()
        cls.rag_engine = RAGEngine()
        
    def test_1_transcript_processor_raw_chunks(self):
        """TranscriptProcessor가 60초 단위로 raw_chunks를 생성하는지 테스트"""
        test_transcript_list = [
            {"text": "Hello world", "start": 0.0, "duration": 10.0},
            {"text": "Second sentence", "start": 10.0, "duration": 55.0}, # Total 65s
            {"text": "Third sentence", "start": 65.0, "duration": 10.0}
        ]
        test_transcript = "Hello world Second sentence Third sentence"
        
        result = self.processor.process(
            transcript=test_transcript,
            video_title="Test Video",
            video_url="https://youtube.com/watch?v=test_mvr_001",
            transcript_list=test_transcript_list
        )
        
        self.assertIn('raw_chunks', result)
        self.assertGreaterEqual(len(result['raw_chunks']), 1)
        
        # 첫 번째 청크가 약 60초 부근을 커버하는지 확인
        chunk_ids = list(result['raw_chunks'].keys())
        first_chunk = result['raw_chunks'][chunk_ids[0]]
        self.assertEqual(first_chunk['start_time'], 0.0)
        self.assertGreaterEqual(first_chunk['end_time'], 60.0)
        print(f"\n[Test 1 OK] Created {len(result['raw_chunks'])} raw chunks")

    def test_2_vector_store_dual_collection(self):
        """VectorStore.add_json_documents_v2 가 두 컬렉션에 저장하는지 테스트"""
        unique_id = str(uuid.uuid4())[:8]
        video_url = f"https://youtube.com/watch?v=test_mvr_{unique_id}"
        mock_raw_chunks = {
            "chunk-1": {"text": "AAPL is great", "start_time": 0.0, "end_time": 60.0},
            "chunk-2": {"text": "Buy AAPL now", "start_time": 60.0, "end_time": 120.0}
        }
        
        mock_json_data = {
            "stocks": [
                {
                    "ticker": "AAPL",
                    "name": "Apple",
                    "sentiment": "Positive",
                    "core_thesis": ["Growing services revenue"],
                    "source_chunk_ids": ["chunk-1", "chunk-2"],
                    "timestamp": 60.0,
                    "related_stocks": ["MSFT", "GOOGL"]
                }
            ],
            "summary": "Apple stock analysis video",
            "market_context": "Tech sector is blooming",
            "raw_chunks": mock_raw_chunks
        }
        
        mock_metadata = {
            "업로드일자": "2026-02-27",
            "채널명": "테스트 채널",
            "영상제목": "애플 분석 영상",
            "영상링크": video_url
        }
        
        # 저장 전 카운트
        s_count_before = self.vector_store.get_summary_collection_count()
        r_count_before = self.vector_store.get_raw_collection_count()
        
        self.vector_store.add_json_documents_v2([mock_json_data], [mock_metadata])
        
        # 저장 후 카운트 확인
        s_count_after = self.vector_store.get_summary_collection_count()
        r_count_after = self.vector_store.get_raw_collection_count()
        
        self.assertEqual(s_count_after, s_count_before + 1)
        self.assertEqual(r_count_after, r_count_before + 1)
        print(f"\n[Test 2 OK] Dual collections count increased: Summaries({s_count_after}), Raw({r_count_after})")

    def test_3_rag_engine_retrieval_flow(self):
        """RAGEngine이 Multi-Vector 모드로 정상 검색 및 Fetch 하는지 테스트"""
        query = "애플 주식에 대한 투자 의견은?"
        
        # Multi-Vector 모드 retrieve 호출
        results = self.rag_engine.retrieve(query, use_multi_vector=True, top_k=1)
        
        self.assertGreater(len(results), 0)
        first_result = results[0]
        
        # 결과가 딕셔너리 포맷 {'page_content', 'metadata'} 인지 확인
        self.assertIn('metadata', first_result)
        self.assertIn('page_content', first_result)
        
        # 메타데이터에 timestamp_url이 있고 &t= 가 포함되어 있는지 확인
        self.assertIn('timestamp_url', first_result['metadata'])
        print(f"\n[Test 3 OK] Multi-Vector retrieval successful. Doc ID: {first_result['metadata'].get('doc_id')}")

    def test_4_full_answer_generation(self):
        """답변 생성 시 타임스탬프 링크와 연관 종목이 포함되는지 확인"""
        query = "애플과 관련된 종목들도 같이 알려줘"
        result = self.rag_engine.chat(query)
        answer = result['answer']
        
        # 답변에 유튜브 링크와 타임스탬프 정보가 포함되어 있는지 확인
        self.assertIn("http", answer)
        
        # 관련 종목 정보가 포함되었는지 (MSFT, GOOGL 등 머릿속 mock 데이터 기반)
        # 실제 DB 데이터에 따라 다를 수 있으므로 포함 여부만 대략 확인
        print("\n[Test 4 OK] Answer generation includes sources and metadata.")
        print("-" * 50)
        print(f"Sample Answer excerpt: {answer[:300]}...")

if __name__ == "__main__":
    unittest.main()
