from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AppConfig:
    openai_api_key: str
    openai_model: str
    tavily_api_key: str
    embedding_model_name: str
    chunk_size: int
    chunk_overlap: int
    rag_top_k: int
    max_retry_rag: int
    max_retry_web: int
    max_retry_competitor: int
    max_retry_draft: int
    recent_days_limit: int

    @classmethod
    def from_env(cls) -> "AppConfig":
        openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        tavily_api_key = os.getenv("TAVILY_API_KEY", "").strip()

        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY가 필요합니다.")
        if not tavily_api_key:
            raise ValueError("TAVILY_API_KEY가 필요합니다.")

        return cls(
            openai_api_key=openai_api_key,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            tavily_api_key=tavily_api_key,
            embedding_model_name=os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-m3"),
            chunk_size=int(os.getenv("CHUNK_SIZE", "1200")),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "150")),
            rag_top_k=int(os.getenv("RAG_TOP_K", "6")),
            max_retry_rag=int(os.getenv("MAX_RETRY_RAG", "2")),
            max_retry_web=int(os.getenv("MAX_RETRY_WEB", "2")),
            max_retry_competitor=int(os.getenv("MAX_RETRY_COMPETITOR", "2")),
            max_retry_draft=int(os.getenv("MAX_RETRY_DRAFT", "2")),
            recent_days_limit=int(os.getenv("RECENT_DAYS_LIMIT", "540")),
        )