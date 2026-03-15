"""
강화된 전처리 파이프라인 테스트
"""
from core.transcript_processor import TranscriptProcessor
import json


def test_enhanced_processor():
    """강화된 TranscriptProcessor 테스트"""
    print("\n" + "="*60)
    print("🧪 강화된 전처리 파이프라인 테스트")
    print("="*60)
    
    processor = TranscriptProcessor()
    
    # 상세한 테스트 자막
    test_transcript = """
    안녕하세요 여러분. 오늘은 NVIDIA에 대해 깊이 있게 분석해보겠습니다.
    
    먼저 핵심 논지를 말씀드리면, AI 데이터센터 수요가 폭발적으로 증가하면서
    GPU 공급이 부족한 상황입니다. H100 칩 납품이 지연되면서 프리미엄 가격을
    유지하고 있고요. 경쟁사 대비 기술적 우위도 최소 2년 이상 앞서 있습니다.
    
    구체적인 수치를 보면, 매출 성장률이 전년 대비 200% 증가했습니다.
    EPS는 25.5로 예상되고 있고요. 현재 주가는 850달러 수준인데,
    목표가는 1200달러까지 상승 여력이 있다고 봅니다.
    
    매매 전략을 말씀드리면, 800달러에서 850달러 구간에서
    3회 분할 매수를 추천합니다. 추격 매수는 절대 금지입니다.
    손절가는 750달러로 설정하시면 됩니다.
    
    다만 리스크도 있습니다. 중국 시장 규제 리스크가 있고,
    AMD와의 경쟁이 심화되고 있습니다. 그리고 PER이 45배로
    밸류에이션 부담이 있다는 점도 주의하셔야 합니다.
    
    전반적으로 나스닥은 사상 최고치를 경신 중이고,
    AI 관련 섹터 전체가 강세입니다.
    """
    
    result = processor.process(test_transcript, "NVIDIA 심층 분석")
    
    print("\n📊 처리 결과:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 검증
    if result['stocks']:
        stock = result['stocks'][0]
        print("\n✅ 추출 성공!")
        print(f"\n종목: {stock.get('name')} ({stock.get('ticker')})")
        print(f"감정: {stock.get('sentiment')}")
        
        # 핵심 논지
        if 'core_thesis' in stock:
            print(f"\n핵심 논지:")
            for thesis in stock['core_thesis']:
                print(f"  - {thesis}")
        
        # 주요 지표
        if 'key_metrics' in stock:
            print(f"\n주요 지표:")
            for key, value in stock['key_metrics'].items():
                print(f"  - {key}: {value}")
        
        # 매매 전략
        if 'trading_strategy' in stock:
            print(f"\n매매 전략:")
            print(f"  {stock['trading_strategy']}")
        
        # 리스크 요인
        if 'risk_factors' in stock:
            print(f"\n리스크 요인:")
            for risk in stock['risk_factors']:
                print(f"  - {risk}")
    else:
        print("\n❌ 종목 추출 실패")
    
    return result


if __name__ == "__main__":
    test_enhanced_processor()
