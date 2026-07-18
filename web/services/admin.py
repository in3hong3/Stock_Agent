"""관리자 탭 서비스 — ui/pages/admin.py를 FastAPI용으로 (admin 전용).

시스템 상태·비용·공용데이터 편집·강제작업. 외부 연동(Pinecone/Sheets)은 실패해도
죽지 않게 방어적으로. 영상 수집 파이프라인 '실행'은 무거워(수 분) 보류 — 상태만 표시.
"""
import datetime
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

# 자동 작업 추정 비용 (ui/pages/admin.py와 동일)
COST_ROWS = [
    ("🗞️ 데일리 신문 (Perplexity)", "매일 1회", "$0.05", "$1.5"),
    ("🎤 유튜버 알림 (gpt-4o)", "이틀 1회", "$0.07", "$1.0"),
    ("🔔 가격 알림 체크", "30분", "$0", "$0"),
    ("🤖 AI 평가서 (수동)", "필요 시", "$0.10", "변동"),
    ("💬 RAG 챗봇 (수동)", "질문당", "$0.03", "변동"),
]

CRON_JOBS = [
    ("🗞️ 데일리 신문 자동 발행", "auto_paper.log", "매일 KST 07:00"),
    ("🎤 유튜버 알림 갱신", "video_alerts.log", "이틀에 1회 (KST 06:00)"),
    ("🔔 가격 알림 체크", "alerts.log", "장중 30분마다"),
]


def get_context() -> dict:
    return {
        "pinecone": _pinecone(),
        "crons": _crons(),
        "disk": _disk(),
        "cost_rows": COST_ROWS,
        "pipeline_status": _pipeline_status(),
        "custom_events": _custom_events(),
        "time_keywords": _time_keywords(),
    }


def _pinecone() -> dict:
    try:
        from utils.pinecone_store import PineconeStore
        stats = PineconeStore().index.describe_index_stats()
        ns = stats.namespaces or {}
        return {"ok": True, "total": stats.total_vector_count,
                "summary": ns.get("stock-summaries").vector_count if ns.get("stock-summaries") else 0,
                "raw": ns.get("stock-raw-chunks").vector_count if ns.get("stock-raw-chunks") else 0}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def _crons() -> list:
    out = []
    log_dir = _ROOT / "logs"
    for name, fname, schedule in CRON_JOBS:
        log = log_dir / fname
        if log.exists():
            lines = log.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
            mtime = datetime.datetime.fromtimestamp(log.stat().st_mtime)
            out.append({"name": name, "schedule": schedule, "exists": True,
                        "mtime": mtime.strftime("%Y-%m-%d %H:%M"),
                        "last_line": (lines[-1][:120] if lines else "(빈 로그)")})
        else:
            out.append({"name": name, "schedule": schedule, "exists": False})
    return out


def _disk() -> dict:
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        data_size = sum(f.stat().st_size for f in Path("data").rglob("*") if f.is_file()) if Path("data").exists() else 0
        return {"ok": True, "used_gb": used / 1e9, "free_gb": free / 1e9, "data_mb": data_size / 1e6}
    except Exception as e:
        return {"ok": False, "error": str(e)[:80]}


def _pipeline_status() -> dict:
    try:
        from utils.sheet_loader import SheetDataLoader
        return SheetDataLoader().get_last_data_info()
    except Exception:
        return {"youtube_date": "N/A", "market_date": "N/A"}


def _custom_events() -> list:
    try:
        from modules.event_calendar import load_custom_events
        return load_custom_events()
    except Exception:
        return []


def _time_keywords() -> dict:
    try:
        from modules.video_timing import _TIME_KEYWORDS
        return {"sample": ", ".join(_TIME_KEYWORDS[:15]), "count": len(_TIME_KEYWORDS)}
    except Exception:
        return {"sample": "", "count": 0}


# ── 쓰기/강제 작업 ──
def add_event(date_str: str, title: str) -> str:
    from modules.event_calendar import add_custom_event
    if not (title or "").strip():
        return "⚠️ 일정 내용을 입력하세요."
    add_custom_event(date_str, title.strip())
    return f"➕ 일정 추가: {date_str} {title.strip()}"


def remove_event(index: int) -> str:
    from modules.event_calendar import remove_custom_event
    remove_custom_event(index)
    return "🗑️ 일정을 삭제했습니다."


def force_republish_paper() -> str:
    from modules.daily_paper import _save_paper_store
    _save_paper_store({})
    return "🗞️ 신문 캐시 삭제 — 데일리 탭에서 다시 발행하세요."


def clear_web_caches() -> str:
    """web 서비스들의 프로세스 TTL 캐시 초기화 (Streamlit st.cache_data.clear 대응)."""
    cleared = 0
    from web.services import market, paper, hot, tracker
    try:
        market._cache["rows"] = None; cleared += 1
    except Exception:
        pass
    for mod, attr in [(paper, "_cache"), (hot, "_scan_cache"),
                      (tracker, "_sig_cache"), (tracker, "_news_cache")]:
        try:
            getattr(mod, attr).clear(); cleared += 1
        except Exception:
            pass
    try:
        tracker._yt_cache["rows"] = None; cleared += 1
    except Exception:
        pass
    return f"🧹 서버 캐시 초기화 완료 ({cleared}개 그룹)"


def force_refresh_alerts() -> dict:
    """유튜버 영상 알림 강제 갱신 (LLM 비용). HTMX fragment."""
    from modules.video_timing import refresh_alerts
    try:
        result = refresh_alerts(days=90)
        return {"ok": True, "msg": f"✅ 갱신 완료: 영상 {result['video_count']}개 → 알림 {result['alert_count']}개"}
    except Exception as e:
        return {"ok": False, "msg": f"❌ {e}"}
