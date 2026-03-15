# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.vector_store import VectorStore

vs = VectorStore()

TARGET_DATE = "2026-02-27"

print("=== ChromaDB Collection Status ===")
print(f"[OLD] youtube_summaries : {vs.get_collection_count()} docs")
print(f"[NEW] stock_summaries   : {vs.get_summary_collection_count()} docs")
print(f"[NEW] stock_raw_chunks  : {vs.get_raw_collection_count()} docs")

# 27일 데이터만 필터링해서 확인
print(f"\n=== stock_summaries - filter date={TARGET_DATE} ===")
try:
    r = vs.summary_collection.get(
        where={"업로드일자": TARGET_DATE},
        include=['documents', 'metadatas']
    )
    docs = r.get('documents', [])
    metas = r.get('metadatas', [])
    print(f"Found: {len(docs)} docs from {TARGET_DATE}")
    for i, (doc, meta) in enumerate(zip(docs, metas)):
        print(f"\n[{i+1}] ticker       : {meta.get('ticker','?')}")
        print(f"     stock_name   : {meta.get('stock_name','?')}")
        print(f"     channel      : {meta.get('채널명','?')}")
        print(f"     video_title  : {meta.get('영상제목','?')[:50]}")
        print(f"     related      : {meta.get('related_stocks','(none)')}")
        print(f"     timestamp_url: {meta.get('timestamp_url','(none)')[:80]}")
        print(f"     summary      : {doc[:100]}...")
except Exception as e:
    print(f"Error: {e}")

# raw chunks도 확인
print(f"\n=== stock_raw_chunks - filter date={TARGET_DATE} ===")
try:
    r2 = vs.raw_collection.get(
        where={"업로드일자": TARGET_DATE},
        include=['documents', 'metadatas']
    )
    docs2 = r2.get('documents', [])
    metas2 = r2.get('metadatas', [])
    print(f"Found: {len(docs2)} docs from {TARGET_DATE}")
    for i, (doc, meta) in enumerate(zip(docs2, metas2)):
        print(f"\n[{i+1}] ticker        : {meta.get('ticker','?')}")
        print(f"     doc_id        : {meta.get('doc_id','?')}")
        print(f"     timestamp_url : {meta.get('timestamp_url','(none)')[:80]}")
        print(f"     raw_len       : {len(doc)} chars")
        # 시간 구간 태그 포함 여부 확인
        has_ts = '[' in doc and 's~' in doc
        print(f"     has_time_tags : {has_ts}")
        print(f"     preview       : {doc[:120]}...")
except Exception as e:
    print(f"Error: {e}")
