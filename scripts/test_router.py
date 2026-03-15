"""
AgenticRouter 분류(Intent Classification) 빠른 테스트
전체 에이전트 호출 없이 라우팅 결정만 테스트합니다.
"""
from agents.router import AgenticRouter

router = AgenticRouter()

tests = [
    ("A경로 예상 (RAG_ONLY)", "올랜도킴이 엔비디아를 어떻게 분석했어?"),
    ("B경로 예상 (QUANT_ONLY)", "NVDA 현재 주가 얼마야?"),
    ("C경로 예상 (BOTH)", "엔비디아 현재 주가랑 유튜버 목표가 비교해줘"),
    ("B경로 예상 (QUANT_ONLY)", "테슬라 PER 계산해줘"),
    ("A경로 예상 (RAG_ONLY)", "요즘 시장 분위기 어때?"),
]

print("\n" + "="*60)
print("AgenticRouter 의도 분류 테스트")
print("="*60)

for label, query in tests:
    intent = router._classify_intent(query)
    route = intent.get("route", "?")
    tickers = intent.get("tickers", [])
    reasoning = intent.get("reasoning", "")
    
    # 경로 기대값 체크
    expected = label.split("(")[1].rstrip(")")
    match = "OK" if expected in route else "MISMATCH"
    
    print(f"\n[{match}] {label}")
    print(f"  질문   : {query}")
    print(f"  경로   : {route}")
    print(f"  티커   : {tickers}")
    print(f"  이유   : {reasoning}")

print("\n" + "="*60)
print("테스트 완료!")
