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

## 📚 향후 발전 방향 (큰 그림)

- [ ] 시그널 적중률 데이터 누적 → ML 분류기 학습 (어떤 셋업이 잘 맞는지)
- [ ] 백테스트 결과를 실제 시그널 가중치에 반영 (자기 학습 루프)
- [ ] 매매일지 + 시그널 정확도 연결 — "지난주 시그널 따랐으면 +X%, 안 따라서 -Y%"
- [ ] 영상 알림 재설계 (90일치 재분석 → 영상 단위 1회 분석 누적) — 보류 중
