"""
사용자별 데이터 경로 관리
포트폴리오/매매일지/자산추이/AI평가서 등 개인 데이터를
사용자 ID별 폴더에 분리 저장한다.

공용 데이터(데일리 신문, 일정, RAG 등)는 data/ 루트에 그대로 둠.
"""
import os
import shutil
from typing import List

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_BASE_DIR, "data")
_USERS_DIR = os.path.join(_DATA_DIR, "users")

# 개인별로 보관할 파일 목록 (data/ 루트에서 data/users/{uid}/ 로 이동)
PRIVATE_FILES = [
    "portfolio.csv",
    "portfolio_meta.json",
    "asset_history.csv",
    "trade_journal.csv",
    "portfolio_eval.json",
    "signal_predictions.csv",
    "tracked_tickers.json",
]


def current_user() -> str:
    """현재 로그인한 사용자 ID.
    우선순위: streamlit 세션 > 환경변수 STOCK_AGENT_USER > 'default'.
    (cron/스크립트는 세션이 없으므로 STOCK_AGENT_USER로 대상 사용자 지정)
    """
    try:
        import streamlit as st
        uid = st.session_state.get("user_id")
        if uid:
            return uid
    except Exception:
        pass
    return os.getenv("STOCK_AGENT_USER", "default")


def user_dir(user_id: str = None) -> str:
    """사용자 데이터 폴더 경로 (자동 생성)."""
    uid = user_id or current_user()
    p = os.path.join(_USERS_DIR, uid)
    os.makedirs(p, exist_ok=True)
    return p


def user_file(filename: str, user_id: str = None) -> str:
    """사용자별 파일 경로."""
    return os.path.join(user_dir(user_id), filename)


# ──────────────────────────────────────────────
# 편의 함수 (자주 쓰는 파일들)
# ──────────────────────────────────────────────
def portfolio_path(user_id: str = None) -> str:
    return user_file("portfolio.csv", user_id)


def portfolio_meta_path(user_id: str = None) -> str:
    return user_file("portfolio_meta.json", user_id)


def asset_history_path(user_id: str = None) -> str:
    return user_file("asset_history.csv", user_id)


def trade_journal_path(user_id: str = None) -> str:
    return user_file("trade_journal.csv", user_id)


def portfolio_eval_path(user_id: str = None) -> str:
    return user_file("portfolio_eval.json", user_id)


def signal_predictions_path(user_id: str = None) -> str:
    return user_file("signal_predictions.csv", user_id)


# ──────────────────────────────────────────────
# 기존 단일 사용자 → 멀티유저 마이그레이션
# ──────────────────────────────────────────────
def migrate_legacy_to_user(user_id: str = "admin") -> List[str]:
    """
    data/*.csv,*.json 중 개인용 파일을 data/users/{user_id}/ 로 이동.
    이미 사용자 폴더에 같은 이름이 있으면 건드리지 않는다 (재실행 안전).
    Returns: 이동된 파일명 리스트
    """
    if not os.path.isdir(_DATA_DIR):
        return []
    target = user_dir(user_id)
    moved = []
    for filename in PRIVATE_FILES:
        src = os.path.join(_DATA_DIR, filename)
        dst = os.path.join(target, filename)
        if os.path.isfile(src) and not os.path.exists(dst):
            try:
                shutil.move(src, dst)
                moved.append(filename)
            except Exception as e:
                print(f"마이그레이션 실패 {filename}: {e}")
    return moved
