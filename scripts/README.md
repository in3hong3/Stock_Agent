# Scripts 폴더

이 폴더에는 테스트, 검증, 유틸리티 스크립트들이 포함되어 있습니다.

## 📁 파일 목록

### ChromaDB 관련
- `rebuild_chromadb.py` - ChromaDB 재구축
- `rechunk_chromadb.py` - 청킹 재처리
- `build_index.py` - 인덱스 빌드
- `summarize_collection.py` - 컬렉션 요약

### 검증 스크립트
- `check_chunks.py` - 청킹 상태 확인
- `check_dates.py` - 날짜 확인
- `check_missing_tickers.py` - 누락된 티커 확인
- `check_transcripts.py` - 자막 확인
- `simple_chunk_check.py` - 간단한 청크 확인

### 테스트 스크립트
- `test_rag.py` - RAG 엔진 테스트
- `test_valuation.py` - 밸류에이션 테스트
- `test_sheet.py` - Google Sheets 테스트
- `test_enhanced_pipeline.py` - 향상된 파이프라인 테스트
- `test_new_pipeline.py` - 새 파이프라인 테스트
- `test_new_schema.py` - 새 스키마 테스트
- `test_subs.py` - 자막 테스트

### 디버깅
- `debug_captions.py` - 자막 디버깅
- `inspect_api.py` - API 검사
- `get_desc.py` - 설명 가져오기

### 결과 파일
- `chunk_status.txt` - 청킹 상태 결과
- `valuation_test_results.txt` - 밸류에이션 테스트 결과

## 사용 방법

```bash
# 프로젝트 루트에서 실행
python scripts/rebuild_chromadb.py
python scripts/test_rag.py
```
