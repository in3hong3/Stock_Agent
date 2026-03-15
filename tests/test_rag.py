"""RAG 시스템 진단 스크립트 - 파일 출력"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.rag_engine import RAGEngine

output = []
output.append("=" * 80)
output.append("RAG 시스템 진단")
output.append("=" * 80)

# RAG 엔진 초기화
engine = RAGEngine()

import sys

# 테스트 쿼리
if len(sys.argv) > 1:
    test_queries = [" ".join(sys.argv[1:])]
else:
    test_queries = [
        "엔비디아",
        "구글 전망 실적 수치",
    ]

for query in test_queries:
    output.append(f"\n\n[쿼리: {query}]")
    output.append("-" * 80)
    
    docs = engine.retrieve(query, top_k=5)
    
    output.append(f"검색 결과: {len(docs)}개\n")
    
    if docs:
        for i, doc in enumerate(docs):
            title = doc['metadata'].get('영상제목', 'N/A')
            date = doc['metadata'].get('업로드일자', 'N/A')
            similarity = 1 - doc['distance']
            
            output.append(f"{i+1}. {title}")
            output.append(f"   날짜: {date} | 유사도: {similarity:.3f}")
            output.append(f"   내용: {doc.get('page_content', '')[:200]}...")
            output.append("")
    else:
        output.append("⚠️ 검색 결과 없음!")

output.append("\n" + "=" * 80)
output.append("진단 완료")
output.append("=" * 80)

# 파일로 저장
with open("rag_diagnosis.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output))

print("진단 완료! rag_diagnosis.txt 파일을 확인하세요.")
