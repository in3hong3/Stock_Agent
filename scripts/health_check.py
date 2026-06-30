"""
health_check.py — 운영 모니터링 하네스 (로드맵 #4)

서버·cron·API가 살아있는지 가볍게(LLM 토큰 0) 점검하고, 문제가 있으면
카카오톡으로 1회 알림한다. 정상이면 조용히 넘어간다.

점검 항목:
  1) systemd 서비스(stock-agent) active 여부 (리눅스 한정)
  2) 데이터 수집 cron — market_cache 신선도 (오늘 수집됐나)
  3) 데일리신문 발행 — data/daily_paper.json date == 오늘(KST)
  4) yfinance 생존 — 지수 1회 호출 성공
  5) 검색 LLM 키 — 데일리신문 검색 provider 존재
  6) 카카오 토큰 — 캐시/refresh 존재 (알림 채널 자체 건강)
  7) 캐시 디스크 — data/cache 용량 (뉴스 누적 비대 감시)

스팸 방지: data/health_state.json에 직전 문제 집합/발송시각 저장.
  같은 문제는 재알림 안 함(REMIND_HOURS 지나면 한 번 더). 문제 해소되면 '회복' 1회 발송.

cron (예: 미장 마감 후/오전, 하루 2~3회):
  0 22,1,7 * * * cd ~/stock-agent && .venv/bin/python scripts/health_check.py >> logs/health.log 2>&1
"""
import os
import sys
import json
import time
import subprocess
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STATE = os.path.join(_BASE, "data", "health_state.json")
KST = timezone(timedelta(hours=9))

REMIND_HOURS = float(os.getenv("HEALTH_REMIND_H", "6"))
CACHE_WARN_MB = float(os.getenv("HEALTH_CACHE_WARN_MB", "500"))
SERVICE_NAME = os.getenv("HEALTH_SERVICE", "stock-agent")


def _today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


# ──────────────────────────────────────────────
# 개별 점검 (각자 (id, ok, detail) 반환)
# ──────────────────────────────────────────────
def check_service():
    """systemd 서비스 active 여부 (리눅스 한정, 그 외 스킵)."""
    try:
        r = subprocess.run(["systemctl", "is-active", SERVICE_NAME],
                           capture_output=True, text=True, timeout=10)
        state = (r.stdout or "").strip()
        if state == "active":
            return ("service", True, f"{SERVICE_NAME} active")
        return ("service", False, f"{SERVICE_NAME} = {state or 'unknown'} (서비스 다운)")
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return ("service", True, "systemctl 없음(로컬) — 스킵")


def check_data_collection():
    """data 수집 cron 동작 여부 — 캐시 신선도."""
    try:
        from core.services.market_cache import cache_status
        st = cache_status()
        if st["tickers"] == 0:
            return ("collect", False, "캐시 비어있음 — 수집 cron 미동작 의심")
        if st["fresh_history"] == 0:
            return ("collect", False,
                    f"신선 히스토리 0/{st['tickers']} — 새벽 수집 누락 의심(라이브 fallback 중)")
        return ("collect", True,
                f"신선 {st['fresh_history']}/{st['tickers']} · 뉴스 {st.get('news_articles', 0)}건")
    except Exception as e:
        return ("collect", False, f"캐시 상태 조회 실패: {e}")


def check_daily_paper():
    """데일리신문이 오늘 발행됐나 (사용자별 파일 — 누구든 1명 이상 오늘치면 OK)."""
    import glob
    today = _today_kst()
    paths = glob.glob(os.path.join(_BASE, "data", "users", "*", "daily_paper.json"))
    if not paths:
        return ("paper", False, "발행된 데일리신문 없음 (사용자 파일 0개)")
    published = []
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                store = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        uid = os.path.basename(os.path.dirname(p))
        if store.get("date") == today and store.get("front"):
            published.append(uid)
    if published:
        return ("paper", True, f"오늘 발행됨 — {', '.join(published)}")
    return ("paper", False, "오늘 발행된 사용자 신문 없음 — 발행 누락 의심")


def check_yfinance():
    """yfinance 생존 — 지수 1회 호출."""
    try:
        import yfinance as yf
        h = yf.Ticker("^GSPC").history(period="5d")
        if h is not None and not h.empty:
            return ("yfinance", True, f"^GSPC {float(h['Close'].iloc[-1]):,.0f} 조회 OK")
        return ("yfinance", False, "^GSPC 응답 비어있음 — yfinance 차단/장애 의심")
    except Exception as e:
        return ("yfinance", False, f"yfinance 호출 실패: {e}")


def check_search_llm():
    """데일리신문 검색 provider 키 존재."""
    try:
        from utils.web_llm import get_search_provider
        p = get_search_provider()
        if p:
            return ("search_llm", True, f"검색 provider = {p}")
        return ("search_llm", False, "검색 LLM 키 없음 — 데일리신문 검색 불가")
    except Exception as e:
        return ("search_llm", False, f"검색 provider 확인 실패: {e}")


def check_kakao_token():
    """카카오 알림 채널 건강 (토큰/refresh 존재)."""
    try:
        from modules.kakao_notify import is_configured, _load_cached_token
        if not is_configured():
            return ("kakao", False, "카카오 미설정 (키/refresh 없음) — 알림 불가")
        cache = _load_cached_token()
        exp = cache.get("expires_at", 0)
        if exp and exp < time.time():
            return ("kakao", True, "access token 만료 — 다음 발송 시 자동 갱신 예정")
        return ("kakao", True, "카카오 토큰 정상")
    except Exception as e:
        return ("kakao", False, f"카카오 상태 확인 실패: {e}")


def check_cache_disk():
    """캐시 디스크 용량 (뉴스 누적 비대 감시 — #2 후속)."""
    cache_dir = os.path.join(_BASE, "data", "cache")
    if not os.path.isdir(cache_dir):
        return ("disk", True, "캐시 폴더 없음")
    total = 0
    for root, _, files in os.walk(cache_dir):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    mb = total / (1024 * 1024)
    if mb > CACHE_WARN_MB:
        return ("disk", False, f"캐시 {mb:.0f}MB > {CACHE_WARN_MB:.0f}MB — 보관기간 컷 도입 검토")
    return ("disk", True, f"캐시 {mb:.1f}MB")


CHECKS = [check_service, check_data_collection, check_daily_paper,
          check_yfinance, check_search_llm, check_kakao_token, check_cache_disk]


# ──────────────────────────────────────────────
# 실행 + 알림
# ──────────────────────────────────────────────
def run_checks():
    results = []
    for fn in CHECKS:
        try:
            results.append(fn())
        except Exception as e:
            results.append((fn.__name__, False, f"점검 자체 오류: {e}"))
    return results


def _load_state():
    try:
        with open(_STATE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state):
    os.makedirs(os.path.dirname(_STATE), exist_ok=True)
    with open(_STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _format_alert(problems):
    lines = [f"🚨 Stock Agent 이상 감지 {len(problems)}건"]
    for _id, _ok, detail in problems:
        lines.append(f"• [{_id}] {detail}")
    lines.append(f"\n점검 시각 {datetime.now(KST).strftime('%m-%d %H:%M')} KST")
    return "\n".join(lines)


def main():
    results = run_checks()
    problems = [(i, ok, d) for (i, ok, d) in results if not ok]
    prob_keys = sorted(i for (i, ok, d) in problems)

    print(f"=== health_check {datetime.now(KST).strftime('%Y-%m-%d %H:%M')} KST ===")
    for _id, ok, detail in results:
        print(f"  {'✅' if ok else '❌'} [{_id}] {detail}")

    state = _load_state()
    last_keys = state.get("problem_keys", [])
    last_sent = state.get("last_sent_ts", 0)
    now = time.time()

    try:
        from modules.kakao_notify import send_kakao_memo, is_configured
        can_alert = is_configured()
    except Exception:
        can_alert = False

    if not problems:
        # 직전에 문제가 있었으면 '회복' 1회 발송
        if last_keys and can_alert:
            send_kakao_memo("✅ Stock Agent 정상 회복 — 이전 이상 항목 모두 해소됨.")
            print("  → 회복 알림 발송")
        _save_state({"problem_keys": [], "last_sent_ts": now})
        print("=== 정상 ===")
        return

    # 문제 있음 — 새 문제이거나 REMIND_HOURS 경과 시 발송
    changed = set(prob_keys) != set(last_keys)
    stale = (now - last_sent) > REMIND_HOURS * 3600
    sent = False
    if can_alert and (changed or stale):
        sent = send_kakao_memo(_format_alert(problems))
        print(f"  → 카카오 알림 {'발송' if sent else '발송 실패'} ({'새 문제' if changed else '재알림'})")
    else:
        reason = "카카오 미설정" if not can_alert else "동일 문제 최근 발송됨 — 스킵"
        print(f"  → 알림 생략 ({reason})")

    _save_state({"problem_keys": prob_keys,
                 "last_sent_ts": now if sent else last_sent})
    print(f"=== 이상 {len(problems)}건 ===")


if __name__ == "__main__":
    main()
