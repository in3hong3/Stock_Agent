# Oracle Cloud Free Tier 배포 가이드

비용 0원으로 Stock Agent를 상시 운영하는 전체 과정입니다.

---

## 1. Oracle Cloud VM 생성

1. https://cloud.oracle.com 가입 (해외결제 가능한 카드 필요, 과금 안 됨)
2. **Compute → Instances → Create Instance**
3. 설정:
   - Image: **Ubuntu 22.04**
   - Shape: **VM.Standard.A1.Flex** (Always Free — ARM, 최대 4 OCPU / 24GB RAM)
   - 권장: 2 OCPU / 12GB RAM
4. SSH 키 다운로드 (`.key` 파일 — 잃어버리면 접속 불가!)
5. 생성 후 **공인 IP** 메모

### 방화벽 열기 (Oracle 콘솔)
**Networking → VCN → Security List → Ingress Rules**에 추가:
- `0.0.0.0/0` TCP **80** (HTTP)
- `0.0.0.0/0` TCP **443** (HTTPS)

---

## 2. 서버 초기 설정

```bash
# 로컬 PC에서 SSH 접속
ssh -i your-key.key ubuntu@<공인IP>

# Ubuntu 내부 방화벽도 열기
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save

# 필수 패키지
sudo apt update && sudo apt install -y python3-pip python3-venv nginx git
```

---

## 3. 앱 배포

```bash
cd ~
git clone <본인 GitHub 저장소 URL> stock-agent
cd stock-agent

# 가상환경 + 의존성
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 로그 디렉터리
mkdir -p logs

# .env 파일 생성 (⚠️ git에 올리지 말고 서버에서 직접 작성)
nano .env
# → API 키들, APP_USERNAME / APP_PASSWORD (강한 비밀번호!) 입력

# Google Sheets 인증 JSON도 직접 업로드
# 로컬 PC에서: scp -i your-key.key stock-bot-*.json ubuntu@<IP>:~/stock-agent/
```

---

## 4. systemd 서비스 등록 (상시 실행)

```bash
sudo cp deploy/stock-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now stock-agent

# 상태 확인
sudo systemctl status stock-agent
# 로그 확인
journalctl -u stock-agent -f
```

서버가 재부팅돼도 앱이 자동 시작되고, 죽으면 5초 후 자동 재시작됩니다.

---

## 5. Nginx + HTTPS

### 도메인이 있는 경우 (권장)
```bash
# 1. 도메인 DNS A 레코드 → 서버 공인 IP 연결
# 2. nginx 설정에서 yourdomain.com을 본인 도메인으로 수정
nano deploy/nginx-stock-agent.conf

sudo cp deploy/nginx-stock-agent.conf /etc/nginx/sites-available/stock-agent
sudo ln -s /etc/nginx/sites-available/stock-agent /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# HTTPS 무료 인증서 (자동 갱신됨)
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

> 도메인은 가비아/Cloudflare에서 연 1~2만원, 또는 [DuckDNS](https://www.duckdns.org) 무료 서브도메인 사용 가능

### 도메인 없이 IP로만 쓸 경우
`server_name _;`로 수정하고 certbot은 생략 (HTTP만 사용).
이 경우 로그인 비밀번호가 평문 전송되므로 **Tailscale 병행을 권장**합니다.

---

## 6. 데이터 자동 수집 (cron)

```bash
crontab -e
# → deploy/crontab.txt 내용 붙여넣기 (경로 확인!)

# 등록 확인
crontab -l
```

| 작업 | 주기 |
|------|------|
| 유튜브/시장 데이터 수집 | 매일 KST 07:00 |
| 미장 브리핑 이메일 | 매일 KST 07:30 |
| 가격 알림 체크 | 미국 장중 30분마다 |

---

## 7. 나만 접속 가능하게 하기

**이중 보안 적용:**

1. **앱 로그인** (이미 구현됨) — `.env`의 `APP_USERNAME` / `APP_PASSWORD`를 강한 값으로 설정
2. **HTTPS** — certbot으로 비밀번호 평문 전송 방지

**더 강하게 하고 싶다면 (선택):**

```bash
# Nginx Basic Auth 추가 (이중 로그인)
sudo apt install -y apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd myid
# nginx 설정 location / 블록에 추가:
#   auth_basic "Restricted";
#   auth_basic_user_file /etc/nginx/.htpasswd;
```

또는 **Tailscale** (가장 안전 — 외부 노출 0):
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# 핸드폰/PC에 Tailscale 앱 설치 → 같은 계정 로그인
# → http://<tailscale-ip>:8501 로 접속 (nginx 불필요)
```

---

## 8. 업데이트 배포

```bash
cd ~/stock-agent
git pull
source .venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart stock-agent
```

---

## 체크리스트

- [ ] `.env`가 `.gitignore`에 포함되어 있는지 확인
- [ ] **기존에 노출된 API 키 전부 재발급** (OpenAI, Pinecone, YouTube, 네이버 비밀번호)
- [ ] `APP_PASSWORD`를 admin이 아닌 강한 비밀번호로 변경
- [ ] HTTPS 적용 확인 (자물쇠 아이콘)
- [ ] 재부팅 테스트: `sudo reboot` 후 앱 자동 시작 확인
