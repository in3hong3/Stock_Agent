"""사용자별 portfolio_meta.json 읽기/쓰기 — ui.pages._meta의 load_meta/save_meta와 동일 로직.

_meta는 streamlit을 import하므로 FastAPI에선 이 경량 버전을 쓴다 (같은 파일 대상).
"""
import json
import os

from utils.user_data import portfolio_meta_path


def load_meta() -> dict:
    try:
        with open(portfolio_meta_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_meta(**updates) -> None:
    meta = load_meta()
    meta.update(updates)
    path = portfolio_meta_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
