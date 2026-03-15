"""
테스트 스크립트: 새로운 데이터 수집 로직 검증
"""
import json

# 1. StockExtractor 테스트
print("=== Testing StockExtractor ===")
try:
    from core.stock_extractor import StockExtractor
    extractor = StockExtractor()
    
    test_transcript = """
    오늘은 삼성전자와 SK하이닉스의 실적에 대해 이야기해보겠습니다.
    엔비디아의 GPU 수요가 증가하면서 HBM 시장이 성장하고 있습니다.
    테슬라와 비트코인 가격도 상승세를 보이고 있습니다.
    """
    
    print("Extracting stocks from test transcript...")
    stocks = extractor.extract_stocks_from_transcript(test_transcript, "반도체 시장 전망")
    
    print(f"✅ Found {len(stocks)} stocks:")
    for stock in stocks:
        print(f"  - {stock['종목명']} ({stock['ticker']}) [{stock['market']}]")
    
except Exception as e:
    print(f"❌ StockExtractor test failed: {e}")

# 2. 타임스탬프 JSON 생성 테스트 (text 또는 utf8 필드 대응)
print("\n=== Testing Timestamp JSON ===")
try:
    # 다양한 필드명이 섞여있는 케이스 시뮬레이션
    test_raw_data = [
        {"start": 0.0, "duration": 3.5, "text": "안녕하세요"},
        {"start": 3.5, "duration": 4.0, "utf8": "오늘은 삼성전자 주가에 대해"},
        {"start": 7.5, "duration": 5.0, "text": "말씀드리겠습니다"}
    ]
    
    # 텍스트 추출 로직 (main.py와 동일)
    full_text = " ".join([t.get('text', t.get('utf8', '')) for t in test_raw_data])
    print(f"✅ Joined Text: {full_text}")
    
    test_timestamps = [
        {
            "start": t['start'],
            "duration": t.get('duration', 0),
            "text": t.get('text', t.get('utf8', ''))
        }
        for t in test_raw_data
    ]
    
    json_str = json.dumps(test_timestamps, ensure_ascii=False)
    print(f"✅ Timestamp JSON length: {len(json_str)} chars")
    
    # 파싱 테스트
    parsed = json.loads(json_str)
    print(f"✅ Parsed {len(parsed)} timestamp entries")
    for i, entry in enumerate(parsed):
        print(f"  [{i}] {entry['text']}")
    
except Exception as e:
    print(f"❌ Timestamp JSON test failed: {e}")

# 3. 50,000자 제한 테스트
print("\n=== Testing 50,000 char limit ===")
long_text = "테스트 " * 10000  # 약 60,000자
print(f"Original length: {len(long_text)} chars")

if len(long_text) > 50000:
    part1 = long_text[:50000]
    print(f"✅ Truncated to: {len(part1)} chars")
else:
    part1 = long_text
    print(f"✅ Within limit: {len(part1)} chars")

# 4. video_id 기반 중복 체크 시뮬레이션
print("\n=== Testing video_id duplicate check ===")
existing_video_ids = {"dQw4w9WgXcQ", "abc123", "xyz789"}
new_video_id = "dQw4w9WgXcQ"

if new_video_id in existing_video_ids:
    print(f"✅ Duplicate detected: {new_video_id} - SKIP")
else:
    print(f"✅ New video: {new_video_id} - ADD")

# 5. 새 스키마 row 생성 테스트
print("\n=== Testing new schema row ===")
sample_row = [
    "2026-02-04 17:30:00",  # 수집일시
    "dQw4w9WgXcQ",          # 영상ID
    "UCxxxxxxx",            # 채널ID
    "삼프로TV",             # 채널명
    "삼성전자 주가 전망",   # 영상제목
    "2026-02-03",           # 업로드일자
    "https://youtube.com/watch?v=dQw4w9WgXcQ",  # 영상링크
    1823,                   # 영상길이(초)
    "안녕하세요 오늘은...",  # 전체자막
    '[{"start":0,"text":"안녕하세요"}]'  # 타임스탬프JSON
]

print(f"✅ New schema row has {len(sample_row)} columns")
print(f"  Expected: 10 columns")
if len(sample_row) == 10:
    print("✅ Schema validation PASSED")
else:
    print("❌ Schema validation FAILED")

print("\n=== All Tests Complete ===")
