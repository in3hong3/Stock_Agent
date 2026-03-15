"""
설정 관리 모듈
환경 변수 및 상수를 중앙 집중식으로 관리
"""
import os
from dotenv import load_dotenv

load_dotenv()

# API 키 및 인증 정보
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
GOOGLE_SHEETS_CREDENTIALS_JSON = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# YouTube 채널 설정
TARGET_CHANNEL_ID_LIST = os.getenv("TARGET_CHANNEL_ID_LIST", "").split(",")
ORLANDO_CHANNEL_ID = TARGET_CHANNEL_ID_LIST[0].strip() if TARGET_CHANNEL_ID_LIST else ""

# Pinecone 설정
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "stock-agent-index")
PINECONE_NAMESPACE_SUMMARY = "stock-summaries"
PINECONE_NAMESPACE_RAW = "stock-raw-chunks"

# ChromaDB 설정 (레거시 - 하위 호환성 유지)
CHROMA_DB_PATH = "./data/chroma_db"
COLLECTION_NAME = "youtube_transcripts"
SUMMARY_COLLECTION_NAME = "stock_summaries"
RAW_COLLECTION_NAME = "stock_raw_chunks"

# 벡터 스토어 타입 (chroma, pinecone)
VECTOR_DB_TYPE = os.getenv("VECTOR_DB_TYPE", "pinecone")

# LLM 모델 설정
LLM_MODEL_DEFAULT = "gpt-4o-mini"
LLM_MODEL_SMART = "gpt-4o"
EMBEDDING_MODEL = "text-embedding-3-small"

# 티커 오타 보정 매핑
TYPO_CORRECTIONS = {
    # 발음 오류
    "아이 옹크": "IonQ", "아이옹크": "IonQ", "아온큐": "IonQ", "아이온큐": "IonQ", 
    "아Q": "IonQ", "아이런": "IonQ", "아이랜": "IonQ", "아이렌": "IonQ", "아이언": "IonQ",
    # 한글 약어
    "삼전": "Samsung Electronics", "삼성": "Samsung Electronics",
    "하닉": "SK Hynix", "하이닉": "SK Hynix",
    "마소": "Microsoft", "엔비": "NVIDIA", "엔디비아": "NVIDIA",
    "테슬": "Tesla", "아마": "Amazon",
    # 영문 오타
    "Nvidia": "NVIDIA", "nvidia": "NVIDIA", "Tesla": "TSLA",
    "Apple": "AAPL", "Microsoft": "MSFT",
}

# 에이전트 레지스트리
AGENT_REGISTRY = {
    "orlando_kim": {
        "id": "orlando_kim",
        "name": "영상분석관",
        "description": "올랜도킴 채널의 주식 분석 정보",
        "channel_id": ORLANDO_CHANNEL_ID,
        "enabled": True,
        "type": "rag"
    },
    "technical_analyst": {
        "id": "technical_analyst",
        "name": "기술분석관",
        "description": "차트 지표 분석 및 매매 타이밍 제안 (MA, RSI, MACD, Bollinger Bands)",
        "enabled": True,
        "type": "technical"
    },
    "news_sentiment": {
        "id": "news_sentiment",
        "name": "뉴스분석관",
        "description": "최신 뉴스 수집 및 시장 감성 분석",
        "enabled": True,
        "type": "news"
    }
}

# RAG 설정
DEFAULT_TOP_K = 8
DEFAULT_TEMPERATURE = 0.3
MAX_TRANSCRIPT_LENGTH = 50000

# UI 설정
PAGE_TITLE = "Stock Agent - Multi-Agent"
PAGE_ICON = "📈"
