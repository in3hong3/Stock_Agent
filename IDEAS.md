# 💡 아이디어 보관함

> 떠오를 때마다 추가. 형식은 자유. 우선순위는 적당히 위/아래로 옮기면 됨.
> 작업 시작하면 줄 끝에 `→ 작업중` 또는 `→ 완료 (커밋 abc123)` 식으로 표시.

---

## 🚧 보류 중 (다음 작업 후보)

### 자동 배포 (GitHub push → Oracle 서버 자동 반영)
> 2026-06-17 추가
- **현재 흐름**: 로컬 변경 → git push → SSH 접속 → git pull → systemctl restart (수동)
- **목표**: push만 하면 Oracle 서버가 자동으로 pull + restart
- **선택지**:
  - A. GitHub Actions + SSH (webhook 트리거 → 서버에서 deploy 스크립트 실행) — 가장 흔함
  - B. 서버 cron으로 1분마다 `git pull` 체크 (변경 있으면 restart) — 가장 단순, 약간 lag
  - C. 서버에 `webhook` 받아서 즉시 실행하는 작은 endpoint 띄우기 — 빠르지만 추가 포트
- **권장**: A안 (.github/workflows/deploy.yml에 SSH로 한 줄 실행)
- 작업 시간 추정: 10~15분

### 모바일 전용 화면
> 2026-06-17 보류
- A안: `ui/mobile.css`에 `@media (max-width: 768px)` 추가 → 사이드패널 숨김, 카드 폭 확대, 폰트 조정
- B안 (권장): URL `?mobile=1` / UA 감지 → `ui/pages/mobile/` 새 폴더 → 카드 위주 UX (오늘 할 일 + 적중률 + 매매 시그널만)
- C안: PWA화 (manifest.json + service worker) → 홈화면 추가, 푸시 알림
- 결정 보류 이유: 데스크탑 풀기능 vs 모바일 압축형 두 벌 유지 부담

---

## 🌱 떠오른 아이디어

(여기 자유롭게 적기)

-

---

## ❌ 검토했으나 안 함

### saveticker.com 통합 (2026-06-17)
- 공식 API/RSS 없음, Next.js SPA라 정적 스크래핑 불가
- robots.txt: `Content-Signal: ai-train=no`
- 청크명 자주 바뀜 → 유지비용 ≫ 이득
- 대신 Perplexity의 `search_domain_filter`에 한국 매체(한경/매경/이데일리/머투/더벨/비즈포스트) 추가로 갈음

### 검색 LLM provider 변경 (2026-06-17)
- Claude Opus 4.8 (가장 신뢰성, 비쌈) vs Gemini 2.5 Flash (무료) 검토
- 결론: Perplexity 유지 + `search_recency_filter='week'` + 도메인 화이트리스트로 충분

---

## 🛠️ 하네스(자동화 틀) 로드맵 — 2026-06-18 추가
> "한 번에 다"가 아니라 하나씩 안전하게 자동화. 가성비 순으로 위→아래.
> 이미 cron(데일리신문/유튜버알림/가격알림)이 ①의 초보 버전으로 돌고 있음 (deploy/crontab.txt).

- [x] **1순위 — 시그널 검증 하네스** (완료) — signal_backtest.py + signal_tracker 채점
  - signal_tracker.py가 이미 '매일 시그널 기록 → 10일 후 채점' 절반 구현됨
  - 여기에 백테스트 연결: 과거 데이터에 시그널 로직을 자동으로 돌려 "이 로직이 돈 벌었나" 채점
  - 올랜도 킴식으로 바꾼 로직(EPS 엔진/RSI 예외)이 실제로 개선됐는지 숫자로 증명
- [x] **2순위 — 데이터 수집 하네스** (완료 2026-06-28) — market_cache + collect_market_data
  - 지금: 페이지 열 때 그 순간 yfinance 호출 → 느림(로딩)
  - 목표: 새벽 cron이 주가·뉴스·공시를 미리 긁어 파일/DB 저장 → 페이지는 즉시 읽기만
  - 효과: 로딩 거의 사라짐 + yfinance 차단 위험↓ + 데이터 안정
  - **구현**: `core/services/market_cache.py`(parquet 캐시 + 투명 라이브 fallback) +
    `scripts/collect_market_data.py`(새벽 cron, 전 사용자 보유/관심/추적+지수 수집).
    trade_signal의 history/info/지수 호출을 캐시 경유로 전환 → analyze_stock 3.5s→0.14s.
    캐시 콜드 시 기존과 100% 동일 동작(안전). 뉴스/공시 사전수집은 후속 과제로 남김.
- [ ] **3순위 — LLM 평가 하네스** (규모 중)
  - 데일리신문·스코어링·AI평가가 헛소리(환각·옛 가격)인지 자동 검사
  - 예: '데일리에 적힌 가격이 yfinance 실제가와 ±5% 넘게 다르면 경고/재생성'
- [ ] **4순위 — 모니터링 하네스** (규모 작음)
  - 서버·cron·API가 살아있나 자동 체크, 죽으면 알림 (운영 안정화)

---

## 📚 향후 발전 방향 (큰 그림)

- [ ] **스마트 머니 추적 (올랜도 킴식 삼각편대 마지막 퍼즐)** — 2026-06-18 보류
  - 현재 시그널은 ①실적엔진(EPS) + ③타이밍(RSI/MACD/ATR)만 봄. ②기관이 모으는지가 빠짐
  - 1단계(쉬움): yfinance `institutionalOwnership`/보유비율 변화 → 시그널 점수에 가산
  - 2단계(중간): SEC EDGAR Form 4(내부자 거래) 파싱 → "최근 3개월 임원 순매수" 신호
  - 3단계(어려움): 13F 분기 보고서, 다크풀 대량거래 (유료 데이터 많음)
  - 효과: "RSI 과열 + 내부자 순매수 + 기관비율 증가 → 강세 진짜" 판단 가능
- [ ] 시그널 적중률 데이터 누적 → ML 분류기 학습 (어떤 셋업이 잘 맞는지)
- [ ] 백테스트 결과를 실제 시그널 가중치에 반영 (자기 학습 루프)
- [ ] 매매일지 + 시그널 정확도 연결 — "지난주 시그널 따랐으면 +X%, 안 따라서 -Y%"
- [ ] 영상 알림 재설계 (90일치 재분석 → 영상 단위 1회 분석 누적) — 보류 중
