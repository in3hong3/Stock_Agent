# -*- coding: utf-8 -*-
import sys, os
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.vector_store import VectorStore

def check_integrity():
    vs = VectorStore()
    
    # 1. 문서 수 확인
    s_count = vs.get_summary_collection_count()
    r_count = vs.get_raw_collection_count()
    print(f"Summaries: {s_count}, Raw Chunks: {r_count}")
    
    # 2. 모든 데이터 가져오기
    print("\nFetching all metadata for analysis...")
    all_summaries = vs.summary_collection.get(include=['metadatas', 'documents'])
    all_raw = vs.raw_collection.get(include=['metadatas'])
    
    s_metas = all_summaries['metadatas']
    r_metas = all_raw['metadatas']
    s_docs = all_summaries['documents']
    
    # 3. 중복 체크 (Video URL + Ticker combination)
    print("\nChecking for duplicates (URL + Ticker)...")
    summary_combos = []
    for meta in s_metas:
        combo = f"{meta.get('영상링크','URL 없음')} | {meta.get('ticker','?')}"
        summary_combos.append(combo)
    
    counter = Counter(summary_combos)
    duplicates = {k: v for k, v in counter.items() if v > 1}
    
    if duplicates:
        print(f"Found {len(duplicates)} duplicate entries (same video + ticker):")
        for k, v in list(duplicates.items())[:10]:
            print(f" - {k}: {v} times")
        if len(duplicates) > 10:
            print(" ... and more.")
    else:
        print("No duplicate video+ticker entries found in summaries.")
        
    # 4. 청크 내용 샘플링 (Naive vs Semantic 확인)
    print("\nAnalyzing Chunk Patterns (Preview)...")
    # 요약본이 단순 텍스트인지, 기업명 정보가 포함되어 있는지 확인
    for i in range(min(5, len(s_docs))):
        doc = s_docs[i]
        meta = s_metas[i]
        print(f"Sample {i+1} [{meta.get('ticker','?')}]:")
        print(f"  Doc preview: {doc[:150]}...")
        # 컨텍스트 주입 여부 확인 (작성자가 보낸 제안처럼 [종목명] 등이 들어있는지)
        has_context = f"[{meta.get('stock_name','')}]" in doc or f"({meta.get('ticker','')})" in doc
        print(f"  Has Context Header: {has_context}")

if __name__ == "__main__":
    check_integrity()
