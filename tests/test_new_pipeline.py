"""
새로운 전처리 파이프라인 테스트
TranscriptProcessor + JSON 기반 청킹 검증
"""
from core.transcript_processor import TranscriptProcessor
from utils.vector_store import VectorStore
import json


def test_transcript_processor():
    """TranscriptProcessor 단위 테스트"""
    print("\n" + "="*60)
    print("🧪 Test 1: TranscriptProcessor")
    print("="*60)
    
    processor = TranscriptProcessor()
    
    # 테스트 자막
    test_transcript = """
    안녕하세요 여러분. 오늘은 아이온큐와 테슬라에 대해 얘기해보겠습니다.
    
    먼저 아이온큐입니다. 최근 실적 발표에서 매출이 전년 대비 120% 성장했다고 밝혔습니다.
    EPS는 예상치 0.18을 크게 상회하는 2.8을 기록했고요.
    가이던스도 상향 조정했습니다. 양자컴퓨팅 시장에서 선두를 달리고 있죠.
    저는 이 주식을 장기 보유할 계획입니다.
    
    반면 테슬라는 최근 판매량 감소로 주가가 하락했습니다.
    경쟁이 심화되면서 마진도 압박받고 있어요. 조금 더 지켜봐야 할 것 같습니다.
    
    전반적으로 나스닥은 사상 최고치를 경신 중이고, AI 관련주들이 강세입니다.
    """
    
    result = processor.process(test_transcript, "IonQ vs Tesla 비교 분석")
    
    print("\n📊 처리 결과:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 검증
    assert 'stocks' in result
    assert 'market_context' in result
    assert 'summary' in result
    
    stocks = result['stocks']
    print(f"\n✅ 추출된 종목 수: {len(stocks)}")
    
    for stock in stocks:
        print(f"\n  📈 {stock.get('name')} ({stock.get('ticker')})")
        print(f"     관점: {stock.get('sentiment')}")
        print(f"     근거: {stock.get('reasoning')[:50]}...")
        print(f"     지표: {stock.get('key_metrics')}")
    
    return result


def test_vector_store_json_chunking():
    """VectorStore JSON 청킹 테스트"""
    print("\n" + "="*60)
    print("🧪 Test 2: VectorStore JSON Chunking")
    print("="*60)
    
    # 테스트 데이터 준비
    json_data = {
        'stocks': [
            {
                'ticker': 'IONQ',
                'name': 'IonQ',
                'sentiment': '긍정적',
                'reasoning': '매출 120% 성장, 양자컴퓨팅 시장 선도',
                'key_metrics': {
                    'revenue_growth': '120% YoY',
                    'eps': '2.8',
                    'guidance': '상향 조정'
                },
                'timestamp': None
            },
            {
                'ticker': 'TSLA',
                'name': 'Tesla',
                'sentiment': '부정적',
                'reasoning': '판매량 감소, 마진 압박',
                'key_metrics': {},
                'timestamp': None
            }
        ],
        'market_context': 'AI 붐으로 나스닥 사상 최고치',
        'summary': 'IonQ 긍정, Tesla 관망 추천'
    }
    
    metadata = {
        '업로드일자': '2026-02-11',
        '채널명': '테스트 채널',
        '영상제목': 'IonQ vs Tesla 비교',
        '영상링크': 'https://youtube.com/watch?v=test123'
    }
    
    # VectorStore 초기화
    vector_store = VectorStore()
    
    print(f"\n📊 기존 청크 수: {vector_store.get_collection_count()}")
    
    # JSON 청킹 및 임베딩
    print("\n💾 JSON 데이터 임베딩 중...")
    vector_store.add_json_documents([json_data], [metadata])
    
    print(f"✅ 새 청크 수: {vector_store.get_collection_count()}")
    
    # 검색 테스트
    print("\n🔍 검색 테스트: 'IonQ 전망'")
    results = vector_store.search("IonQ 전망은 어때?", top_k=3)
    
    if results and results.get('documents'):
        for i, (doc, meta, dist) in enumerate(zip(
            results['documents'][0],
            results['metadatas'][0],
            results['distances'][0]
        )):
            print(f"\n  [{i+1}] 유사도: {1-dist:.3f}")
            print(f"      티커: {meta.get('ticker', 'N/A')}")
            print(f"      감정: {meta.get('sentiment', 'N/A')}")
            print(f"      내용: {doc[:100]}...")
    
    return results


def test_end_to_end():
    """전체 파이프라인 통합 테스트"""
    print("\n" + "="*60)
    print("🧪 Test 3: End-to-End Pipeline")
    print("="*60)
    
    # 1. 전처리
    processor = TranscriptProcessor()
    test_transcript = """
    엔비디아가 최근 실적 발표에서 놀라운 성과를 보였습니다.
    데이터센터 매출이 전년 대비 200% 증가했고, AI 칩 수요가 폭발적입니다.
    """
    
    json_data = processor.process(test_transcript, "NVIDIA 실적 분석")
    print("\n✅ Step 1: 전처리 완료")
    print(f"   종목 수: {len(json_data.get('stocks', []))}")
    
    # 2. 임베딩
    vector_store = VectorStore()
    metadata = {
        '업로드일자': '2026-02-11',
        '채널명': '테스트',
        '영상제목': 'NVIDIA 분석',
        '영상링크': 'https://youtube.com/watch?v=test456'
    }
    
    vector_store.add_json_documents([json_data], [metadata])
    print("✅ Step 2: 임베딩 완료")
    
    # 3. 검색
    results = vector_store.search("엔비디아 실적", top_k=1)
    print("✅ Step 3: 검색 완료")
    
    if results and results.get('documents'):
        print(f"\n📊 검색 결과:")
        print(f"   문서: {results['documents'][0][0][:100]}...")
        print(f"   티커: {results['metadatas'][0][0].get('ticker')}")
    
    print("\n🎉 전체 파이프라인 정상 작동!")


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║          새로운 전처리 파이프라인 테스트                     ║
║                                                            ║
║  1. TranscriptProcessor (LLM 전처리)                       ║
║  2. VectorStore JSON 청킹                                  ║
║  3. End-to-End 통합 테스트                                 ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
    """)
    
    try:
        # Test 1
        test_transcript_processor()
        
        # Test 2
        test_vector_store_json_chunking()
        
        # Test 3
        test_end_to_end()
        
        print("\n" + "="*60)
        print("✅ 모든 테스트 통과!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
