# 보유계좌 정보의 RAG 활용 가이드

## 📋 개요

보유 포트폴리오 정보를 RAG 시스템에 통합하여 **개인화된 투자 조언**을 제공하는 시스템입니다.

## 🎯 핵심 기능

### 1. **자동 종목 매칭**
사용자 질문에서 키워드를 추출하여 보유 종목을 자동으로 식별합니다.

**예시:**
```
질문: "AI 반도체 시장 전망은?"
→ 자동 매칭: NVDA, MU, TSM, ORCL (보유 중인 AI 관련 종목)
```

**키워드 매핑:**
- `AI`: NVDA, GOOGL, META, AMZN, ORCL, IONQ
- `반도체`: NVDA, MU, TSM, SKYT
- `빅테크`: GOOGL, AMZN, META, ORCL
- `클라우드`: GOOGL, AMZN, ORCL
- `양자컴퓨팅`: IONQ
- `태양광`: FSLR
- `일본`: 1497.T, 9984.T
- `은행`: KRE
- `헬스케어`: XLV

### 2. **질문 증강 (Query Augmentation)**
사용자 질문에 관련 종목 티커를 자동으로 추가하여 검색 정확도를 높입니다.

**예시:**
```
원본 질문: "반도체 전망은?"
증강된 질문: "반도체 전망은? NVDA MU TSM SKYT"
```

### 3. **보유 종목 정보 표시**
답변과 함께 관련 보유 종목의 현재 상태를 표시합니다.

**출력 예시:**
```
💼 보유 중인 관련 종목

- NVDA (엔비디아)
  - 보유: 48주
  - 평균단가: 258,043원
  - 현재가: 276,409원
  - 수익률: 7.1%

- MU (마이크론 테크놀로지)
  - 보유: 26주
  - 평균단가: 489,172원
  - 현재가: 596,798원
  - 수익률: 22.0%
```

### 4. **대화 메모리 통합**
이전 대화 맥락과 포트폴리오 정보를 함께 활용합니다.

**예시:**
```
사용자: "내가 보유한 반도체 종목들 어때?"
AI: [NVDA, MU, TSM 분석...]

사용자: "그 종목들 중에서 지금 추가 매수하면 좋을 종목은?"
AI: [이전 대화 맥락 + 보유 정보를 활용한 답변]
```

## 🚀 사용 방법

### 기본 사용

```python
from core.personalized_rag import PersonalizedRAG
from core.rag_engine import RAGEngine

# 초기화
base_rag = RAGEngine()
personalized_rag = PersonalizedRAG(base_rag)

# 개인화된 질문
result = personalized_rag.chat(
    query="AI 반도체 시장 전망은?",
    top_k=10,
    temperature=0.7,
    use_portfolio_context=True  # 포트폴리오 컨텍스트 사용
)

# 결과 확인
print(result['answer'])  # AI 답변
print(result['related_holdings'])  # 관련 보유 종목
print(result['sources'])  # 참고 소스
print(result['followup_questions'])  # 후속 질문
```

### 대화 메모리와 함께 사용

```python
conversation_history = []

# 첫 번째 질문
result1 = personalized_rag.chat(
    query="내가 보유한 빅테크 종목들 어때?",
    conversation_history=None,
    use_portfolio_context=True
)

# 대화 히스토리에 추가
conversation_history.append({"role": "user", "content": "내가 보유한 빅테크 종목들 어때?"})
conversation_history.append({"role": "assistant", "content": result1['answer']})

# 두 번째 질문 (맥락 참조)
result2 = personalized_rag.chat(
    query="그 종목들 중에서 지금 매도하면 좋을 종목은?",
    conversation_history=conversation_history,
    use_portfolio_context=True
)
```

### 포트폴리오 요약

```python
summary = personalized_rag.get_portfolio_summary()

print(f"총 종목 수: {summary['summary']['total_stocks']}")
print(f"총 평가금액: {summary['summary']['total_evaluation']:,.0f}원")
print(f"평균 수익률: {summary['summary']['average_profit_rate']:.2f}%")
```

## 📁 파일 구조

```
core/
├── rag_engine.py           # 기본 RAG 엔진
├── personalized_rag.py     # 개인화 RAG 엔진 (NEW)
└── __init__.py

modules/
└── portfolio_analyzer.py   # 포트폴리오 분석기

data/
└── portfolio.csv           # 보유 포트폴리오 데이터

tests/
├── test_rag_conversation.py
└── test_personalized_rag.py  # 개인화 RAG 테스트 (NEW)
```

## 🔧 포트폴리오 데이터 형식

`data/portfolio.csv` 파일 형식:

```csv
ticker,name,quantity,avg_price,current_price
NVDA,엔비디아,48,258043,276409
GOOGL,알파벳 Class A,61,470480,452260
AMZN,아마존닷컴,19,342032,296814
```

**필수 컬럼:**
- `ticker`: 종목 티커 (예: NVDA, GOOGL)
- `name`: 종목명 (예: 엔비디아, 알파벳)
- `quantity`: 보유 수량
- `avg_price`: 평균 매수가
- `current_price`: 현재가

**자동 계산 컬럼:**
- `eval_amount`: 평가금액 = quantity × current_price
- `profit_loss`: 평가손익 = eval_amount - (quantity × avg_price)
- `profit_rate`: 수익률 = (profit_loss / (quantity × avg_price)) × 100

## 🎨 Streamlit 앱 통합 예시

```python
import streamlit as st
from core.personalized_rag import PersonalizedRAG
from core.rag_engine import RAGEngine

# 세션 상태 초기화
if 'personalized_rag' not in st.session_state:
    base_rag = RAGEngine()
    st.session_state.personalized_rag = PersonalizedRAG(base_rag)

if 'conversation_history' not in st.session_state:
    st.session_state.conversation_history = []

# 사이드바: 포트폴리오 요약
with st.sidebar:
    st.header("📊 내 포트폴리오")
    
    summary = st.session_state.personalized_rag.get_portfolio_summary()
    if summary.get('status') == 'success':
        st.metric("총 종목", f"{summary['summary']['total_stocks']}개")
        st.metric("평균 수익률", f"{summary['summary']['average_profit_rate']:.2f}%")
        st.metric("총 손익", f"{summary['summary']['total_profit_loss']:,.0f}원")

# 메인: 채팅 인터페이스
st.title("💬 개인화 투자 조언 챗봇")

user_query = st.chat_input("질문을 입력하세요...")

if user_query:
    # 사용자 메시지 표시
    st.chat_message("user").write(user_query)
    
    # AI 답변 생성
    with st.spinner("분석 중..."):
        result = st.session_state.personalized_rag.chat(
            query=user_query,
            conversation_history=st.session_state.conversation_history,
            use_portfolio_context=True
        )
    
    # AI 답변 표시
    st.chat_message("assistant").write(result['answer'])
    
    # 관련 보유 종목 표시
    if result.get('related_holdings'):
        with st.expander("💼 관련 보유 종목"):
            for stock in result['related_holdings']:
                col1, col2, col3 = st.columns(3)
                col1.write(f"**{stock['name']}**")
                col2.write(f"{stock['quantity']:,}주")
                col3.write(f"{stock['profit_rate']:.1f}%")
    
    # 후속 질문 표시
    if result.get('followup_questions'):
        st.write("**💡 추천 질문:**")
        for q in result['followup_questions']:
            if st.button(q, key=q):
                st.rerun()
    
    # 대화 히스토리 업데이트
    st.session_state.conversation_history.append({
        "role": "user", 
        "content": user_query
    })
    st.session_state.conversation_history.append({
        "role": "assistant", 
        "content": result['answer']
    })
```

## 🔍 작동 원리

### 1. 질문 분석 단계
```
사용자 질문: "AI 반도체 시장 전망은?"
    ↓
키워드 추출: ["AI", "반도체"]
    ↓
보유 종목 매칭: NVDA, MU, TSM, ORCL
```

### 2. 검색 증강 단계
```
원본 질문: "AI 반도체 시장 전망은?"
    ↓
티커 추가: "AI 반도체 시장 전망은? NVDA MU TSM ORCL"
    ↓
RAG 검색 (top_k=10)
```

### 3. 답변 생성 단계
```
RAG 검색 결과 (YouTube 영상 분석)
    +
보유 종목 정보 (수량, 평균단가, 수익률)
    +
대화 히스토리 (이전 맥락)
    ↓
개인화된 AI 답변 생성
```

### 4. 후처리 단계
```
AI 답변
    +
관련 보유 종목 정보 주입
    ↓
최종 답변 반환
```

## 📊 예상 효과

### Before (기본 RAG)
```
질문: "AI 반도체 시장 전망은?"
답변: "AI 반도체 시장은 성장세입니다. NVIDIA, AMD, Intel 등이 
      주요 플레이어입니다..."
```

### After (개인화 RAG)
```
질문: "AI 반도체 시장 전망은?"
답변: "AI 반도체 시장은 성장세입니다. 특히 귀하가 보유 중인 
      NVDA(48주, +7.1%), MU(26주, +22.0%), TSM(29주, +22.6%)은 
      모두 수익 중이며, 최근 전문가들은..."

💼 보유 중인 관련 종목
- NVDA (엔비디아): 48주, 수익률 7.1%
- MU (마이크론): 26주, 수익률 22.0%
- TSM (TSMC): 29주, 수익률 22.6%
```

## 🛠️ 커스터마이징

### 키워드 매핑 추가

`personalized_rag.py`의 `_get_related_holdings` 메서드에서 키워드 매핑을 수정할 수 있습니다:

```python
keyword_map = {
    'ai': ['NVDA', 'GOOGL', 'META', 'AMZN', 'ORCL', 'IONQ'],
    '반도체': ['NVDA', 'MU', 'TSM', 'SKYT'],
    # 새로운 키워드 추가
    '전기차': ['TSLA', 'RIVN'],
    '우주': ['SPCE', 'RKLB'],
}
```

### 포트폴리오 파일 경로 변경

```python
personalized_rag = PersonalizedRAG(
    rag_engine=base_rag,
    portfolio_path="custom/path/to/portfolio.csv"
)
```

## 🧪 테스트

```bash
# 개인화 RAG 테스트
python tests/test_personalized_rag.py

# 대화 메모리 테스트
python tests/test_rag_conversation.py
```

## 📝 주의사항

1. **포트폴리오 파일 필수**: `data/portfolio.csv` 파일이 없으면 일반 RAG로 동작합니다.
2. **현재가 업데이트**: `current_price`는 수동으로 업데이트해야 합니다 (향후 자동화 가능).
3. **키워드 매칭 한계**: 새로운 종목이나 카테고리는 수동으로 키워드 맵에 추가해야 합니다.

## 🚀 향후 개선 방향

1. **실시간 가격 연동**: yfinance 등을 활용한 자동 가격 업데이트
2. **AI 기반 종목 매칭**: 키워드 맵 대신 임베딩 기반 유사도 검색
3. **포트폴리오 리밸런싱 제안**: AI가 포트폴리오 조정을 자동 제안
4. **알림 기능**: 보유 종목 관련 중요 뉴스 발생 시 알림
5. **백테스팅**: 과거 RAG 조언과 실제 수익률 비교
