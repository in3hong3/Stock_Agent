# Streamlit → FastAPI + HTMX 점진 이전 계획

> 작성 2026-07-13. 방식: **스트랭글러 패턴** — 새 앱을 `web/`에 세우고 nginx `/v2/`로 병행 운영,
> 탭을 하나씩 옮긴 뒤 마지막에 Streamlit 종료(1GB VM RAM 확보).
> 원칙: `ui/pages/` **동결**(신규 기능 금지). `modules/`·`agents/`·`core/`·cron 로직은 그대로 재사용.
> 원칙2: **기능 보존이지 위젯 복제가 아니다.** Streamlit 고유 위젯을 억지로 흉내 내지 말고,
> 더 나은 웹 UX가 있으면 그걸로 추진한다. 결과·데이터·부수효과만 동일하면 개선은 환영.
> (상세: [migration_parity_checklist.md](migration_parity_checklist.md) "대조 원칙")

---

## 기술 스택 결정

| 요소 | 선택 | 이유 |
|---|---|---|
| 백엔드 | FastAPI + uvicorn | 가볍고(1GB VM 적합) 비동기·SSE 지원 |
| 템플릿 | Jinja2 | 서버 렌더, 학습 부담 최소 |
| 상호작용 | HTMX | JS 프레임워크 없이 부분 갱신 → Streamlit rerun 문제 해결 |
| 차트 | Plotly(기존 재사용, CDN JS) 또는 서버 PNG | 기존 fig 로직 그대로 |
| 인증 | itsdangerous 서명 쿠키 | 기존 `_auth_token` 재사용 |
| 세션/사용자 | `contextvars` + Depends | `st.session_state` 대체 |

---

## 공통 선행 작업 (로직에서 Streamlit 걷어내기)

이전 전에 로직 레이어의 Streamlit 의존을 제거. 이건 Streamlit 앱도 계속 잘 돌게 하면서 진행 가능:

- [ ] `utils/user_data.current_user()` — `st.session_state` 대신 `contextvars.ContextVar` 우선 조회로 변경 (Streamlit·FastAPI·cron 3곳 공용)
- [ ] `@st.cache_data` 걸린 순수함수(`ui/theme.get_realtime_market_summary`, `_meta.get_cached_signals` 등) → `cachetools.TTLCache` 래퍼로 분리, 두 앱이 공유
- [ ] `st.spinner/toast/rerun/warning`이 로직 함수(`_meta.auto_fill_missing_prices` 등) 안에 있는 것 → 값 반환으로 바꾸고 UI 표시는 호출부로

---

## 단계별 로드맵 (오늘 2026-07-13 기준)

### Phase 0 — 기반 (뼈대 + 로그인 + 레이아웃)
목표: `/v2/`에서 로그인하고 빈 대시보드 셸이 뜬다.
- FastAPI 앱 골격(`web/main.py`), 설정, uvicorn systemd 유닛(`stock-agent-v2`, 포트 8000)
- nginx에 `/v2/` → 127.0.0.1:8000 라우팅 추가 (기존 `/` Streamlit 유지)
- 로그인/로그아웃 + 서명 쿠키(`_auth_token` 재사용, `Secure` 플래그 — **HTTPS 선행 필요**)
- 베이스 레이아웃: 상단 티커테이프 + F&G 바 + 탭 내비 (`components.py`·`theme.py` 포팅)
- **산출물**: 껍데기 배포, 이후 모든 탭이 여기 얹힘
- 추정: **1~2 세션**

### Phase 1 — 읽기 전용 탭 (쉬운 것부터, 패턴 확립)
데이터를 읽어 렌더만 하는 탭. 폼·상태 없음 → 가장 값쌈. 여기서 "탭당 세션 실측" 확보.

| 순서 | 탭 | 파일 | 줄수 | 비고 |
|---|---|---|---|---|
| 1 | 🗞️ 데일리 | paper.py | 222 | daily_paper 읽어 마크다운 렌더 (파일럿 후보) |
| 2 | 🧠 AI 신호 | ml_signals.py | 252 | 표시 전용(메모리대로), predict 결과 읽기 |
| 3 | 🔥 핫 섹터 | hot_sectors.py | 197 | sector_scanner 결과 렌더 |
| 4 | 📅 주간 리포트 | weekly_report.py | 311 | 주차 선택 드롭다운(HTMX) |
| 5 | 🧪 백테스트 | backtest.py | 149 | 입력폼 → 계산 → 결과(약한 CRUD) |

- 추정: **2~3 세션**

### Phase 2 — CRUD 탭 (폼·저장, 제일 무거움)
개인 데이터(CSV/JSON) 읽기+쓰기. HTMX 폼, `current_user()` 추상화 필수.

| 순서 | 탭 | 파일 | 줄수 | 데이터 |
|---|---|---|---|---|
| 6 | 📒 매매일지 | journal.py | 110 | trade_journal.csv (제일 단순한 CRUD → 먼저) |
| 7 | 🔔 가격알림 | alerts.py | 194 | price_alert 설정 |
| 8 | 📌 내 종목 | tracker.py | 610 | tracked_tickers.json + 포트폴리오 스냅샷 |
| 9 | 💼 포트폴리오 | portfolio.py | 738 | portfolio.csv + meta, 가격갱신, 최적화 (최대 파일) |

- 추정: **4~6 세션**

### Phase 3 — 분석관 채팅 (SSE 스트리밍)
LLM 응답 스트리밍이라 별도 취급. RAG/기술/뉴스/종합/진입점검 5개 서브탭.
- SSE 엔드포인트로 토큰 스트리밍, HTMX SSE 확장 또는 순수 EventSource
- `agents/router.py`의 Streamlit 의존(있으면) 제거
- 추정: **2~3 세션**

### Phase 4 — 관리자 + 사이드패널 + 전환
- 🔧 관리자 탭(admin.py, 212줄), 사이드패널(sidebar.py, 372줄) 이전
- 전 탭 동작 확인 → nginx `/` 를 8000으로 전환, `/legacy/`로 Streamlit 임시 유지
- 문제 없으면 Streamlit systemd 중지 → **RAM 확보 완료**
- 추정: **1~2 세션**

---

## 총 추정

- **누적 세션: 10~16** (탭 실측 전 대략치. Phase 1 파일럿 후 재산정)
- Claude Pro 한도로 하루 1~2세션 → **달력상 2~4주** (붙는 날 기준)
- 각 Phase·각 탭이 독립 배포 가능 → 언제 멈춰도 앱은 정상 동작

---

## 진행 순서 요약

1. **HTTPS 먼저** (도메인+certbot) — Phase 0 서명 쿠키 `Secure`의 선행 조건
2. 공통 선행 작업(로직 디커플링) — Streamlit 앱 유지한 채 진행
3. Phase 0 → 1(파일럿 1탭으로 실측) → 2 → 3 → 4
