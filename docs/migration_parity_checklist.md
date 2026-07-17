# 탭별 기능 명세 & 이전 대조 체크리스트

> 작성 2026-07-13. 목적: Streamlit → FastAPI 이전 시 **기능 누락 0** 보장.
> 각 탭을 새 스택으로 옮긴 뒤, 아래 체크박스를 하나씩 대조하며 `[ ]` → `[x]` 로 채운다.
> 하나라도 비면 그 탭은 "이전 완료"가 아니다.
>
> 범례: 🔵읽기전용 · 🟢CRUD(저장) · 💬LLM채팅 · 💰LLM비용발생 · ⏱️캐시 · 🔑session_state

---

## ⭐ 대조 원칙 — "기능 보존"이지 "위젯 복제"가 아니다

이 체크리스트가 보장하려는 건 **사용자가 할 수 있던 일(기능)이 하나도 빠지지 않는 것**이지,
Streamlit 위젯의 생김새·조작법을 똑같이 재현하는 게 아니다.

- **더 나은 대안이 있으면 그걸로 추진한다.** Streamlit 고유 위젯(`data_editor`, `st.pills`,
  `st.data_editor`, `st.fragment` 등)을 HTMX/HTML로 억지로 흉내 내기보다, 웹에서 더 자연스럽고
  더 나은 UX가 있으면 **그쪽을 채택**한다. 예: 인라인 표 편집 → 행별 편집 모달/폼, 슬라이더 →
  숫자 입력+±버튼, pills 다중선택 → 체크박스 그룹 등. 웹 표준이 더 빠르고 접근성도 좋으면 개선이다.
- 체크 기준은 **"그 기능으로 달성하던 결과를 새 UI에서도 낼 수 있나"** 다. 조작 방식이 달라도
  결과가 같거나 더 좋으면 `[x]` 로 인정한다.
- 단, **결과·데이터·부수효과는 반드시 동일**해야 한다 (저장되는 CSV/JSON, 계산값, 트리거되는 cron·알림).
  UI는 바꿔도 되지만 뒤에서 일어나는 일은 바꾸지 않는다.
- 개선으로 대체한 항목은 해당 체크박스 옆에 `→ 대체: <무엇으로>` 를 적어 추적한다.

---

## 공통 인프라 (모든 탭이 의존 — Phase 0에서 먼저 이전)

### 레이아웃 / 셸 (app.py)
- [ ] 상단 고정 공지바(`top-announcement-bar`) — F&G 색상 연동
- [x] 티커테이프(`render_ticker_tape`) — F&G·다우·S&P·나스닥100·코스피·USD/KRW·BTC 7종, 한국식 색상(빨강↑/파랑↓), 반응형(900px→4열, 560px→2열) → 대체: `web/services/market.get_ticker_tape` + 템플릿
- [x] 페이지 타이틀 "📊 Stock Agent Terminal"
- [ ] 본문 7:3 컬럼 (좌 메인 탭 / 우 사이드패널)
- [ ] 탭 10개(admin이면 11개) + 분석관 내부 서브탭 5개
- [ ] 로딩 인디케이터(`stStatusWidget`) 커스텀 "로딩 중..." — FastAPI에선 HTMX 인디케이터로 대체
- [ ] 모바일 반응형 CSS(`ui/mobile.css`) 주입
- [ ] 테마: F&G 지수 기반 배경/포인트 색 동적 계산(`apply_theme`, `get_heatmap_color`, `get_point_color`)
- [ ] Fear&Greed 지수 캐시 로드(`get_cached_fear_greed_index`)

### 인증 (components.py) — 🔑
- [x] 로그인 페이지(다크 카드 UI, Pretendard 폰트) — id/pw → `web/templates/login.html`
- [x] 계정: env `APP_USERNAME`/`APP_PASSWORD`(admin) + `APP_PASSWORD_SONG`(song) — **다계정** → `web/auth.accounts`
- [x] 서명 토큰(`_auth_token`, sha256) — **동일 스킴 재사용, 쿠키 공유** → `web/auth.auth_token`
- [x] 로그인 쿠키 `sa_auth` 30일 유지(`set_login_cookie`) — Secure는 env `WEB_COOKIE_SECURE`(HTTPS 후 1)
- [x] 새로고침 시 쿠키로 세션 복원(`try_restore_session`) → 서버 쿠키 검증(`user_from_cookie`)
- [ ] 로그아웃(사이드바) — 계정별 캐시/상태 전부 클리어 + 쿠키 제거
- [ ] 최초 로그인 시 legacy→user 데이터 마이그레이션(`migrate_legacy_to_user`) (1회성, 이전 후엔 불필요할 수도)
- [ ] admin 계정만 관리자 탭 노출

### 사이드 패널 (sidebar.py) — 항상 우측 표시
- [ ] 현재 사용자 표시 + 로그아웃 버튼
- [x] 🌋 시장 심리 컴팩트 막대(`render_fear_greed_bar`) → 대시보드 상단 F&G 바(`market.get_fear_greed`) *(사이드바 위치는 Phase 4에서 조정)*
- [ ] 📅 다가오는 일정 (21일 이내, 최대 8개) — `get_upcoming_events`
- [ ] 🗓️ 월별 달력 expander — 이전/다음 달 네비, `build_calendar_html` ⏱️(21600s)
- [ ] 📝 일정 직접 추가/삭제 폼 — `add_custom_event`/`remove_custom_event` 🟢
- [ ] 💰 내 자산 미니 요약 카드 — 총자산(₩/$)·주식평가·평가손익·현금비중 + 종목별 평가액·수익률 리스트
- [ ] 자산 스냅샷 자동 기록(`record_asset_snapshot`) — 트래커 자산추이 차트 데이터 소스 (**하루 1회 기록 로직 이전 주의**)
- [ ] ✅ 오늘 할 일 카드 — `build_actions`, 보유+관심종목 매수신호 종합, 성향별
- [ ] 예측 기록+채점(`record_predictions`/`grade_predictions`) — 하루 1회 (**사이드 렌더에 묻어있음, cron/진입 훅으로 분리 이전**)
- [ ] 🎤 유튜버 타이밍 알림 카드 — `get_active_alerts`, 48h 지나면 자동 갱신(`refresh_alerts`) 💰
- [ ] FX 환율 캐시(`get_usdkrw_rate`) ⏱️(600s)

---

## Phase 1 — 읽기 전용 탭

### 1. 🗞️ 데일리 (paper.py) 🔵 — ✅ 이전 완료 (web/services/paper.py, templates/paper.html)
- [x] 신문 헤더 `株式日報` + 오늘 날짜(KST, `now_kst`)·요일
- [x] "🗞️ 오늘의 신문 발행/새 소식 반영" 버튼 💰 — 매크로+뉴스+SEC공시 종합, `publish_daily_paper`
- [x] 진행 배너(`ProgressBanner`) 5단계 → 대체: HTMX 인디케이터(hx-indicator, 발행 중 문구 1개). 세부 5단계는 웹에선 불필요로 판단
- [x] 발행 상태별 토스트: unchanged/updated/발행, 엔진 라벨(웹검색🔍) → 발행 응답 상단 `.toast`
- [x] 저장된 신문 로드(`get_saved_paper`) → GET 시 표시
- [ ] ⚠️ 첫 진입 시 **자동 발행 1회**(`_auto_paper_attempted`) — 비용 유발이라 **의도적 보류**. 발행은 버튼으로만(자동 LLM 트리거 최소화, 사용자 비용 우려 반영). 재검토 필요
- [ ] 📊 매크로 지표 상세 expander — `render_macro_grid`, 5열 그리드 + 미니 스파크라인 — **미이전**(스파크라인 차트는 후속. 시세판으로 핵심 수치는 커버)
- [x] 3열 레이아웃: 좌(시세판) · 중(1면 기사) · 우(이번주 일정 D-day)
- [x] 1면 기사 렌더(마크다운→HTML, `markdown` 라이브러리) + 발행시각 캡션
- [x] 종목별 상세 뉴스 2열 그리드 — 구글뉴스(`paper_news`) ⏱️(900s) → `<details>` 카드 그리드
- [x] SEC 공시(`paper_filings`) ⏱️(3600s) — 발행 입력으로 사용
- [x] 데이터: `market_overview.get_macro_data`, `daily_paper.*`, `event_calendar.*`, `issue_tracker.get_portfolio_holdings`
- 남은 것: 매크로 스파크라인 상세, 자동발행(보류). 그 외 기능 동등.

### 2. 🧠 AI 신호 (ml_signals.py) 🔵 — 표시 전용(서버 torch 금지) — ✅ 이전 완료 (web/services/ml.py, templates/ml.html)
- [x] 3개 서브탭: 데일리 판정 / 상승확률 / 패턴 감지 → 클라이언트 JS 토글(전부 서버 렌더, 데이터 싸서 한 번에)
- [x] **데일리 판정**: `data/market_scan.json`, verdict 색상별(🔴/🟡/🟢/info), 지수·보유종목 표
- [x] **상승확률(수익률 모델)**: `latest.json`, 상승확률 progress바 + 썸네일(base64 data URI), 보유매칭, 한국종목 제외 안내, AUC 메트릭, 미보유 expander
- [x] **패턴 감지**: `patterns_latest.json`, 패턴확률 카드 + 과거통계, 전체스캔 expander, 패턴통계 expander
- [x] "이 신호들은 어떻게 만들어지나요?" 설명 expander → `<details>`
- [x] 데이터: JSON 파일 3개만 읽음(추론 없음)

### 3. 🔥 핫 섹터 (hot_sectors.py) 🔵+💰 — ✅ 이전 완료 (web/services/hot.py, templates/hot.html)
- [x] "세부 테마 ETF 포함" 체크박스 + 새로고침 버튼 → GET 파라미터(themes/refresh), 체크박스 onchange 자동 제출
- [x] 섹터 모멘텀 스캔(`scan_sectors`) ⏱️(1800s) → 프로세스 TTL 캐시(themes별)
- [x] 🔥 핫 섹터 카드 그리드(상위) — 1개월 수익률·벤치대비
- [x] 전체 랭킹 표 — 1주/1개월/3개월%·vs벤치·모멘텀점수, 색상 스타일(빨강↑/파랑↓)
- [x] 🤖 AI 섹터 해설(fragment) — 드롭다운 + "AI 해설 생성" 💰, `explain_sector` → HTMX POST /t/hot/explain
- [x] 🏆 종목 스코어링(fragment) — 섹터/티커 입력 + "스코어링" 💰, `score_stocks` → HTMX POST /t/hot/score
- [x] **fragment 격리** → HTMX 부분 갱신으로 이전 (explain-out/score-out만 교체, 페이지 rerun 없음)

### 4. 📅 주간 리포트 (weekly_report.py) 🔵+💰 — ✅ 이전 완료 (web/services/weekly.py, templates/weekly.html)
- [x] 🧭 섹터 관심도 expander — `get_insights`, 섹터별 점수·Δ증감·top티커 → `<details>`
- [x] 🌡️ 시황·경계 관점 expander — market_view 타임라인(🔴경계/🟢기회/⚪중립) + 톤 요약
- [x] 🎯 유튜버 콜 트랙레코드 expander — `get_trackrecord`, 매수/주의 콜 적중률·알파, 종목별 표
- [x] 주차 선택 셀렉트박스(`list_reports`, onchange 자동제출) + "이번 주 다시 종합" 버튼 💰 → HTMX POST /t/weekly/regen
- [x] 리포트 본문(`_render_report`): 헤더·메트릭·내러티브(md)·급증·톤반전·언급 TOP15(감성막대)·내 보유종목 코멘트 → 발행 후 partial 재사용
- [x] 데이터: `weekly_youtube_report.*`, `youtuber_trackrecord`, `youtuber_insights`
- 검증: 빈 상태 + 합성 데이터 채워진 경로 양쪽 렌더 통과 (로컬엔 실 데이터 없음 — 서버/cron 생성분)
- 미이전: best/worst 콜(잘맞은/빗나간) — 서비스에 데이터는 담되 템플릿 표시 생략(후속). 그 외 동등.

### 5. 🧪 백테스트 (backtest.py) 🔵(계산 온디맨드)
- [ ] ℹ️ 백테스트 설명 expander (초보용)
- [ ] 🎯 실제 시그널 백테스트 — 보유기간 선택(5/10/20일) + 실행 버튼, `signal_backtest.run_backtest`, MAJORS 20종목+보유 유니버스, 표본/적중률/평균수익 + 셋업별 성과 🔑
- [ ] 📐 단순 전략 백테스트 — 티커/전략(RSI·MA크로스·볼린저)/기간/자본 입력, RSI는 매수·매도 슬라이더, `backtester.run_backtest` 🔑
- [ ] 성과 요약: 전략수익률(vs B&H)·CAGR·MDD·샤프·승률·거래횟수
- [ ] 자산곡선 라인차트 + 낙폭 area차트 + 거래내역 표

---

## Phase 2 — CRUD 탭

### 6. 📒 매매일지 (journal.py) 🟢
- [ ] 거래 입력 폼(clear_on_submit): 날짜·종목·구분(매수/매도)·수량·체결가·메모·포트폴리오 자동반영 체크
- [ ] 기록 시 `resolve_ticker`, `apply_to_portfolio`(옵션), `add_trade`, 실현손익 토스트
- [ ] 매매 성과 메트릭 5개: 총거래·실현손익합·승률·평균수익/손실·손익비
- [ ] 월별/종목별 실현손익 bar차트
- [ ] 거래 내역 표(역순, 매수🟢/매도🔴)
- [ ] 🗑️ 기록 삭제 expander — 행번호 선택 + 삭제(`delete_trade`)
- [ ] 데이터: `trade_journal.*` (trade_journal.csv)

### 7. 🔔 가격알림 (alerts.py) 🟢
- [ ] 알림 채널 상태: 이메일/카카오톡 연결 여부, 카카오 설정법 expander
- [ ] 📩 카카오 데일리 브리핑 ON/OFF 토글 — `save_meta(kakao_briefing_enabled)` 🟢
- [ ] 🎯 관심종목 매수 타이밍 섹션: 알림 토글, 관심종목 추가 폼(`add_to_watchlist`)/삭제, "지금 매수 타이밍 보기"(`detect_buy_timings`)
- [ ] 📍 수동 가격/RSI 알림 추가 폼 — 티커·조건(`CONDITION_TYPES`)·기준값, `add_alert`
- [ ] 등록된 알림 목록 — 상태아이콘·조건·기준·발송기록, 재활성화/삭제 버튼
- [ ] "📡 지금 바로 조건 체크 + 이메일 발송" — `run_alert_check`, 이메일/카카오 결과
- [ ] 데이터: `price_alert.*`, `watchlist.*`, `kakao_notify`, `_meta`

### 8. 📌 내 종목 (tracker.py) 🟢(대부분 읽기+일부 저장)
- [ ] 빈 가격 자동 채움(`auto_fill_missing_prices`) — 진입 시 1회, 실패 종목 "다시 시도" 버튼
- [ ] 📈 시그널 적중률 상단 카드(`get_accuracy_stats`) — 승률·매수평균수익·알파·베스트/워스트 셋업 (0건이면 숨김)
- [ ] 🧬 펀더멘탈 분석 카드 그리드 — 밸류판정·EPS·PEG·선행PER·기관보유·내부자매수 (밸류점수순)
- [ ] 📖 매수 기법 설명 expander
- [ ] 🎯 상세 매매 시그널 expander — 시장국면, 종목별 액션·밸류·지표·판단근거·매매플랜(진입/손절/목표/손익비)·포지션사이징·계단식청산·차트토글
- [ ] 📈 시그널 정확도 상세 expander — 셋업별 성적·최근 채점결과 표
- [ ] 📈 자산 추이 expander — `load_asset_history`, area/line 차트
- [ ] 🎤 이슈 브리핑(fragment) — 종목 pills 선택 + 브리핑 생성 💰(`summarize_all_issues`) 🔑, 시세/뉴스 새로고침
- [ ] 🎤 유튜버 집단지성 expander — `youtuber_consensus.*`, 기간선택, 컨센서스·톤전환·신규레이더 (LLM 0) ⏱️(1800s)
- [ ] 🤖 AI 보유종목 평가 — 성향 라디오 + 평가서 생성/강제재생성 💰(`get_or_create_eval`, Perplexity) 🔑
- [ ] 📰 종목별 최신 이슈 — 종목별 expander 뉴스 + 차트토글
- [ ] 데이터: `issue_tracker.*`, `signal_tracker`, `portfolio_advisor`, `youtuber_consensus`, `_meta` 시그널 캐시

### 9. 💼 포트폴리오 (portfolio.py) 🟢 — 가장 큼, 5개 서브탭
- [ ] 헤더에 현재 사용자명(`current_user()`) — **contextvars 추상화 핵심**
- [ ] 빈 포트폴리오 시 샘플 파일 생성 버튼
- [ ] ➕ 종목 일괄 추가 — data_editor(종목/수량/평단), `resolve_ticker`+yfinance 자동조회, 중복체크 🟢
- [ ] 메인 편집 표(data_editor) — 티커/종목명/수량/평단 직접입력, 현재가/평가금액 자동, 빈행 제거
- [ ] 💾 변경사항 저장 — unsaved 감지, 매도(수량감소/삭제) 감지 → `_pending_sells` 🔑
- [ ] 🗑️ 종목 삭제 expander — multiselect + 삭제, 전량매도 처리
- [ ] 📒 매도 감지 → 매매일지 기록 유도 폼(체결가 입력) / 건너뛰기
- [ ] 총자산 메트릭 4개(총자산/주식평가/현금/총매입) — FX 환산 ⏱️(600s), 빈가격 경고
- [ ] 💰 트레이딩 시드/리스크 설정 폼 — `save_meta(trading_seed, risk_pct)` 🟢
- [ ] 💵 보유 현금 입력 폼(원화/달러) — `save_meta(cash_krw, cash_usd)` 🟢
- [ ] 💵 현금 기준 실행 지시 — 투입비율 슬라이더, `build_action_plan`, 팔것/살것 목록 ⏱️(300s)
- [ ] 📡 가격 업데이트 버튼 — `PriceUpdater.update_portfolio_prices` 🟢
- [ ] 🚀 분석 실행 버튼 — `PortfolioAnalyzer` 💰 🔑
- [ ] 서브탭1 📋 종목상세 — 분석결과 메트릭 + 종목별 AI피드백 + RAG 관련영상
- [ ] 서브탭2 📊 시각화 — 섹터 파이/수익 바/트리맵/선버스트/섹터성과 (Plotly)
- [ ] 서브탭3 🔔 알림 — `PortfolioAlert` 💰
- [ ] 서브탭4 ⚖️ 리밸런싱 — `PortfolioRebalancer`, 3탭(분석/효율적투자선/비용시뮬) 💰
- [ ] 서브탭5 💬 개인화 챗봇 — `PersonalizedRAG`, 보유맥락, 관련종목·소스 💬💰 🔑

---

## Phase 3 — 분석관 채팅 (analysts.py) 💬

### 10-a. 🎯 진입 점검 (render_tab_entry_check) 🔵(규칙기반, LLM 0)
- [ ] 티커·성향·점검 버튼, `analyze_stock`+`decide_action` ⏱️(300s)
- [ ] 결론 카드(적극진입/분할/비추/관망), 종합해석(자연어), 4대관점 메트릭(타이밍/밸류/실적/스마트머니)
- [ ] 진입 플랜(진입/손절/목표/손익비), 판단이 바뀌는 조건, 판단근거 expander, 차트 토글

### 10-b. 🎥 영상분석 RAG (render_tab_rag) 💬💰🔑
- [ ] 채팅 입력, `agentic_router.rag_agent.process`, 대화이력 6개, 소스(참고영상), 추천 후속질문 버튼
- [ ] `rag_messages`, `pending_followup_question` 🔑

### 10-c. 📈 기술분석 (render_tab_tech) 💬💰🔑
- [ ] 실시간 캔들차트 expander — 티커/기간/MA/볼린저 옵션, `build_candlestick_chart` ⏱️(300s)
- [ ] 채팅, `tech_agent.process`, 지표요약(현재가·추세·RSI·MACD·볼린저·지지저항·52주·POC)
- [ ] `tech_messages` 🔑

### 10-d. 📰 뉴스분석 (render_tab_news) 💰🔑
- [ ] 티커·뉴스개수 입력 + 분석 버튼, `NewsAgent.process`
- [ ] 감성점수/시장감성/뉴스수 메트릭 + 감성 바 + 주요토픽 + AI분석 전문 + 뉴스목록
- [ ] `news_result` 🔑

### 10-e. 🔀 종합분석 (render_tab_comprehensive) 💬💰🔑
- [ ] 에이전트 선택 체크박스(RAG/퀀트/기술) + 채팅
- [ ] `agentic_router.route(force_agents=...)`, 참여에이전트 태그, 소스
- [ ] `comprehensive_messages` 🔑
- [ ] ⚠️ **밸류에이션 분석관(render_tab_quant)** — 코드엔 있으나 app.py 탭에 미연결. 이전 시 포함 여부 결정

---

## Phase 4 — 관리자 (admin.py) 🟢 — admin 전용

- [ ] 📊 시스템 상태 — Pinecone 벡터수(요약/원문), cron 로그 3종(마지막실행), 디스크/data폴더 크기
- [ ] 💸 API 비용 모니터 — 자동작업 추정비용 표
- [ ] 🎥 영상 수집 → Pinecone — 수집현황, 날짜범위, `DataPipeline.run_youtube_pipeline`(진행콜백) 💰
- [ ] 📅 공용 데이터 편집 — 커스텀 일정 추가/삭제, 시점 키워드(읽기전용)
- [ ] ⚙️ 강제 작업 — 데일리신문 강제재발행, 유튜버알림 강제갱신 💰, 캐시삭제 3종(평가서/매크로/시그널)

---

## 이전 시 반드시 처리할 "숨은 로직" (Streamlit 결합 지점)

- [ ] `current_user()` — `st.session_state` 의존 → contextvars ([[project-streamlit-migration]])
- [ ] `@st.cache_data` 전부 → TTLCache 래퍼 (paper/tracker/sidebar/hot_sectors/portfolio 등 다수)
- [ ] `st.session_state` 상태 키 — 서버 세션 or 클라이언트 저장으로 재설계 (특히 채팅 이력, 분석 결과 캐시)
- [ ] `st.rerun()` / `st.fragment` — HTMX 부분 갱신으로 대체
- [ ] `ProgressBanner` / `st.spinner` / `st.toast` — HTMX 로딩 인디케이터 + 토스트로 대체
- [ ] 사이드바에 묻힌 **부수효과**(자산 스냅샷 기록, 예측 기록/채점, 유튜버 자동갱신) → 명시적 진입 훅 or cron으로 분리
- [ ] `data_editor`(포트폴리오 표 편집) — HTMX 인라인 편집 or 폼으로 재구현 (가장 까다로움). **1:1 복제 대신 더 나은 웹 UX 채택 가능** — 행별 편집 모달, 또는 경량 표 편집 라이브러리(예: Tabulator/AG Grid 등) 검토. 결과(portfolio.csv)만 동일하면 됨. ([[project-streamlit-migration]] 대조 원칙 참고)
- [ ] 첫 진입 자동 발행(데일리 신문) — 무한 재발행 방지 가드 유지
