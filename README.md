---
title: Stock Agent
emoji: 📈
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.42.2
app_file: app.py
pinned: false
---

# 🚀 Stock Agent - 포트폴리오 통합 RAG 시스템

## 📋 최신 업데이트 (2026-02-13)

### ✨ 새로운 기능

#### 1. **실시간 가격 업데이트** 📡
- yfinance를 사용한 자동 가격 갱신
- 한국/미국/일본 주식 지원
- 원/달러 환율 자동 조회
- 배치 업데이트로 빠른 처리

#### 2. **포트폴리오 알림 시스템** 🔔
- **가격 변동 알림**: ±10% 이상 변동 시 자동 알림
- **뉴스 알림**: RAG 기반 중요 뉴스 자동 감지
- **손절/익절 알림**: -15% 손절, +30% 익절 기준 알림
- AI 기반 뉴스 중요도 자동 판단

#### 3. **포트폴리오 리밸런싱 제안** ⚖️
- 섹터별 비중 분석
- 집중도 리스크 평가
- RAG 기반 시장 인사이트 수집
- AI 기반 매도/보유/매수 제안

#### 4. **개인화 RAG 챗봇** 💬
- 보유 종목 정보 자동 활용
- 키워드 기반 종목 매칭
- 질문 증강 (Query Augmentation)
- 대화 메모리 통합

---

## 🎯 주요 기능

### 1. RAG 챗봇 (YouTube 기반)
- YouTube 영상 자막 기반 주식 정보 검색
- 대화 메모리 (최근 3턴 기억)
- 후속 질문 자동 제안
- Multi-Agent 시스템 (RAG, Technical, News)

### 2. 밸류에이션 분석
- P/E (주가수익비율) 방식
- DCF (현금흐름 할인) 방식
- SOTP (사업부문별 합산) 방식
- yfinance 자동 데이터 수집

### 3. 내 포트폴리오 (NEW!)
- **실시간 가격 업데이트**
- **알림 시스템**
- **리밸런싱 제안**
- **개인화 챗봇**
- 종목별 AI 투자 피드백
- RAG 기반 YouTube 분석

---

## 📦 설치 및 실행

### 1. 환경 설정

```bash
# 가상환경 생성
python -m venv .venv

# 가상환경 활성화 (Windows)
.venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 2. 환경 변수 설정 (`.env`)

```env
# OpenAI API
OPENAI_API_KEY=your_openai_api_key

# YouTube API
YOUTUBE_API_KEY=your_youtube_api_key

# Google Sheets (선택)
GOOGLE_SHEETS_CREDENTIALS_JSON=path/to/credentials.json
SPREADSHEET_URL=your_spreadsheet_url
```

### 3. 포트폴리오 파일 준비

`data/portfolio.csv` 파일을 생성하거나 Streamlit 앱에서 샘플 파일을 생성하세요.

```csv
ticker,name,quantity,avg_price,current_price
NVDA,엔비디아,48,258043,276409
GOOGL,알파벳 Class A,61,470480,452260
AMZN,아마존닷컴,19,342032,296814
```

### 4. 앱 실행

```bash
streamlit run app.py
```

---

## 🔧 사용 방법

### 포트폴리오 관리

#### 1. 가격 업데이트
```python
# CLI에서 실행
python utils/price_updater.py

# 또는 Streamlit 앱에서 "📡 가격 업데이트" 버튼 클릭
```

#### 2. 알림 확인
```python
# CLI에서 실행
python modules/portfolio_alert.py

# 또는 Streamlit 앱의 "🔔 알림" 탭에서 확인
```

#### 3. 리밸런싱 분석
```python
# CLI에서 실행
python modules/portfolio_rebalancer.py

# 또는 Streamlit 앱의 "⚖️ 리밸런싱" 탭에서 확인
```

#### 4. 개인화 챗봇
```python
# Python에서 사용
from core.personalized_rag import PersonalizedRAG
from core.rag_engine import RAGEngine

base_rag = RAGEngine()
personalized_rag = PersonalizedRAG(base_rag)

result = personalized_rag.chat(
    query="내가 보유한 AI 종목들 어때?",
    use_portfolio_context=True
)

print(result['answer'])
print(result['related_holdings'])
```

---

## 📁 프로젝트 구조

```
Stock-bot/
├── core/
│   ├── rag_engine.py              # 기본 RAG 엔진
│   ├── personalized_rag.py        # 개인화 RAG 엔진 (NEW)
│   ├── transcript_processor.py    # 자막 전처리
│   └── stock_extractor.py         # 종목 추출
├── modules/
│   ├── portfolio_analyzer.py      # 포트폴리오 분석기
│   ├── portfolio_alert.py         # 알림 시스템 (NEW)
│   ├── portfolio_rebalancer.py    # 리밸런싱 제안 (NEW)
│   └── report_writer.py           # 리포트 생성
├── utils/
│   ├── vector_store.py            # ChromaDB 벡터 스토어
│   └── price_updater.py           # 실시간 가격 업데이트 (NEW)
├── agents/
│   ├── rag_agent.py               # RAG 에이전트
│   ├── quant_agent.py             # 밸류에이션 에이전트
│   ├── technical_agent.py         # 기술적 분석 에이전트
│   └── news_agent.py              # 뉴스 분석 에이전트
├── data/
│   └── portfolio.csv              # 포트폴리오 데이터
├── docs/
│   └── portfolio_rag_guide.md     # 포트폴리오 RAG 가이드 (NEW)
├── tests/
│   ├── test_rag_conversation.py   # RAG 대화 테스트
│   └── test_personalized_rag.py   # 개인화 RAG 테스트 (NEW)
├── app.py                         # Streamlit 메인 앱
├── main.py                        # YouTube 데이터 수집
└── requirements.txt               # 의존성
```

---

## 🎨 Streamlit 앱 구조

### 탭 1: 💬 RAG 챗봇
- YouTube 영상 기반 주식 정보 검색
- 대화 메모리 및 후속 질문
- Multi-Agent 선택

### 탭 2: 📊 밸류에이션 분석
- P/E / DCF / SOTP 방식
- yfinance 자동 데이터 수집
- 적정가 밴드 계산

### 탭 3: 💼 내 포트폴리오
#### 서브탭 1: 📋 종목 상세
- 보유 종목 정보
- AI 투자 피드백
- RAG 기반 YouTube 분석

#### 서브탭 2: 🔔 알림
- 가격 변동 알림
- 뉴스 알림
- 손절/익절 알림

#### 서브탭 3: ⚖️ 리밸런싱
- 섹터별 비중 분석
- 집중도 리스크 평가
- AI 기반 매도/보유/매수 제안

#### 서브탭 4: 💬 개인화 챗봇
- 보유 종목 정보 활용
- 맞춤형 투자 조언
- 대화 메모리 통합

---

## 🔍 개인화 RAG 작동 원리

### 1. 질문 분석
```
사용자: "AI 반도체 시장 전망은?"
    ↓
키워드 추출: ["AI", "반도체"]
    ↓
보유 종목 매칭: NVDA, MU, TSM, ORCL
```

### 2. 질문 증강
```
원본: "AI 반도체 시장 전망은?"
증강: "AI 반도체 시장 전망은? NVDA MU TSM ORCL"
    ↓
RAG 검색 (top_k=10)
```

### 3. 답변 생성
```
RAG 검색 결과 (YouTube 영상)
    +
보유 종목 정보 (수량, 평균단가, 수익률)
    +
대화 히스토리 (이전 맥락)
    ↓
개인화된 AI 답변 생성
```

### 4. 후처리
```
AI 답변
    +
관련 보유 종목 정보 주입
    ↓
최종 답변 반환
```

---

## 📊 알림 시스템 기준

### 가격 변동 알림
- **급등/급락**: ±10% 이상 변동 시

### 기술적 알림
- **손절 기준**: -15% 이하
- **익절 기준**: +30% 이상
- **경고**: -10% ~ -15%

### 뉴스 알림 (AI 판단)
- 실적 발표, 어닝 서프라이즈
- 주요 계약 체결, M&A
- 규제 이슈, 소송
- 경영진 변동
- 급격한 주가 변동 원인

---

## 🧪 테스트

```bash
# 개인화 RAG 테스트
python tests/test_personalized_rag.py

# RAG 대화 메모리 테스트
python tests/test_rag_conversation.py

# 가격 업데이트 테스트
python utils/price_updater.py

# 알림 시스템 테스트
python modules/portfolio_alert.py

# 리밸런싱 테스트
python modules/portfolio_rebalancer.py
```

---

## 🚀 향후 개선 방향

### 단기 (1-2주)
- [ ] 포트폴리오 자동 백업
- [ ] 가격 업데이트 스케줄링
- [ ] 알림 이메일/슬랙 연동
- [ ] 리밸런싱 시뮬레이션

### 중기 (1-2개월)
- [ ] 포트폴리오 백테스팅
- [ ] AI 기반 종목 추천
- [ ] 리스크 분석 대시보드
- [ ] 다중 포트폴리오 관리

### 장기 (3개월+)
- [ ] 자동 매매 연동
- [ ] 포트폴리오 최적화 알고리즘
- [ ] 소셜 트레이딩 기능
- [ ] 모바일 앱 개발

---

## 📝 주요 변경 사항

### v2.0.0 (2026-02-13)
- ✨ 실시간 가격 업데이트 기능 추가
- ✨ 포트폴리오 알림 시스템 추가
- ✨ 리밸런싱 제안 기능 추가
- ✨ 개인화 RAG 챗봇 추가
- 📝 포트폴리오 RAG 가이드 문서 추가
- 🔧 Streamlit 앱 UI 개선 (서브탭 구조)

### v1.0.0 (2026-02-03)
- 🎉 초기 릴리스
- RAG 챗봇 구현
- 밸류에이션 분석 구현
- 기본 포트폴리오 관리 구현

---

## 🤝 기여

이슈 및 PR은 언제나 환영합니다!

---

## 📄 라이선스

MIT License

---

## 📧 문의

프로젝트 관련 문의사항은 이슈를 통해 남겨주세요.
