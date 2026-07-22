# Claude 운영 규칙 — Stock Agent

> 이 프로젝트에서 작업하는 모든 세션에서 Claude가 자동으로 따라야 하는 규칙.
> 사용자가 매번 확인·승인을 명시적으로 하지 않아도 아래 흐름을 그대로 실행한다.

---

## 🚀 작업 완료 시 자동 배포 (default ON)

**코드 변경을 마칠 때마다 다음 5단계를 자동으로 수행한다.** 사용자가 별도로 `ㄱㄱ` / `배포해줘` / `push해` 등을 말하지 않아도 매 작업의 끝에서 이 흐름을 끝까지 돌린다.

### 1. 로컬 검증
- 변경된 파일 syntax 체크 (`python -c "import ast; ast.parse(...)"`)
- 가능하면 import 한 번 (`from ... import ...` 단순 확인)
- 실패하면 **여기서 중단**하고 사용자에게 보고

### 2. git commit
- `git add` 는 **변경한 파일만 명시적으로** (절대 `git add .` 또는 `git add -A` 금지 — 시크릿/실수 파일 차단)
- 커밋 메시지는 한국어. 핵심 변경 3-5줄 bullet + Co-Authored-By 트레일러
- 시크릿(`.env`, `*.json`, `*.key`)이 staging에 들어가면 절대 커밋하지 말고 사용자에게 경고

### 3. git push origin main
- 동기 push (`git push origin main` 로 끝까지 대기)
- 실패하면 사용자에게 즉시 보고

### 4. Oracle 서버 반영 (SSH)
```
ssh -i "C:/Users/gg951/Downloads/ssh-key-2026-06-12 (1).key" \
    -o StrictHostKeyChecking=accept-new \
    -o ConnectTimeout=15 \
    ubuntu@161.33.6.231 \
    "cd ~/stock-agent && git pull && sudo systemctl restart stock-agent-v2 && sleep 2 && sudo systemctl status stock-agent-v2 --no-pager | head -8"
```
- 출력에 `Active: active (running)` 확인되면 성공
- pull 충돌·서비스 실패하면 사용자에게 보고하고 더 진행하지 않음

### 5. 사용자에게 한 줄 보고
형식:
> ✅ 배포 완료 — commit `abc1234` · 서버 active (running) · https://in3stock.duckdns.org/
> 변경 핵심: <한 줄 요약>

---

## ❌ 자동 배포를 건너뛰는 예외

다음 중 하나라도 해당되면 자동 배포를 멈추고 사용자에게 확인 요청:
- 로컬에서 syntax/import가 실패
- 변경 사항이 **데이터 파일** (`data/`, `*.csv`, `*.json`)만 — 코드 변경 아님
- 변경 사항이 **문서/메모 전용** (`*.md`만)이고 사용자가 push 의사를 명시 안 한 경우
- 시크릿 파일이 staging 에 들어간 정황 발견
- 사용자가 명시적으로 "로컬에서만", "push 하지 마", "검증만" 등 의사 표명

---

## 🔧 작업 시 자주 쓰는 정보

| 항목 | 값 |
|---|---|
| GitHub origin | `https://github.com/in3hong3/Stock_Agent` |
| 운영 도메인 | `https://in3stock.duckdns.org` (nginx → uvicorn 8000, Let's Encrypt HTTPS) |
| Oracle VM IP | `161.33.6.231` (http:80 → 301 https 도메인 리다이렉트) |
| SSH 키 | `C:/Users/gg951/Downloads/ssh-key-2026-06-12 (1).key` |
| SSH 사용자 | `ubuntu` |
| 서버 앱 경로 | `~/stock-agent` |
| 서비스 이름 | `stock-agent-v2` (systemd, FastAPI/uvicorn:8000) — 운영 앱 |
| 옛 Streamlit | `stock-agent` 서비스는 **중지+비활성화**됨. 필요 시 SSH 터널 `-L 8501:127.0.0.1:8501` 후 `sudo systemctl start stock-agent` |
| 로컬 dev 포트 | 8503 (config.toml `runOnSave=true`) |

---

## 🧠 컨텍스트가 헷갈리지 않도록

- 사용자가 "되는데" / "안 되는데" 보고할 때, **그가 보고 있는 화면이 로컬(localhost:8503)인지 Oracle(161.33.6.231)인지 항상 먼저 확인**. 둘은 다른 서버이고, 자동 배포 흐름이 끝나기 전이면 다른 코드를 돌고 있다.
- "oracle" 단어가 나오면 무조건 **Oracle Cloud VM (이 프로젝트의 운영 서버)** 으로 해석. 모델명 "Opus"의 오타로 해석하지 말 것.
- 사용자가 "토큰 많이 써서" 같이 비용 우려를 말하면, 자동 LLM 호출(데일리 신문 발행, 유튜버 알림 갱신) 트리거가 늘었는지 먼저 점검.

---

## 📝 메모

- 자동 배포 규칙은 [IDEAS.md](IDEAS.md) "자동 배포" 항목의 1차 구현. 더 발전된 GitHub Actions / webhook 흐름은 그 항목 참고.
- 이 규칙을 바꾸고 싶으면 이 파일을 직접 편집. 메모리·세션과 무관하게 다음 세션부터 즉시 적용된다.
