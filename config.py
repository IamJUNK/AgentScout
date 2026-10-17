from __future__ import annotations

from pathlib import Path
import json
import os
from typing import Literal
from dotenv import dotenv_values
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent

class Settings(BaseModel):
    database_url: str = Field(default='mysql+pymysql://agentscout:agentscout@127.0.0.1:3306/agentscout', exclude=True, repr=False)
    redis_url: str = Field(default='redis://127.0.0.1:6379/0', exclude=True, repr=False)
    ui_secret: str = Field(default='', exclude=True, repr=False)
    max_task_tokens: int = Field(default=120000, ge=1000)
    max_task_search_calls: int = Field(default=24, ge=1, le=200)
    max_task_attempts: int = Field(default=3, ge=1, le=5)
    dispatch_max_attempts: int = Field(default=10, ge=1, le=100)
    dispatch_interval_seconds: int = Field(default=60, ge=10)
    heartbeat_timeout_seconds: int = Field(default=90, ge=30)
    retrieval_mode: Literal['bm25', 'hybrid'] = 'bm25'
    embedding_base_url: str = ''
    embedding_provider: Literal['local', 'api'] = 'local'
    embedding_cache_dir: str = str(ROOT / 'data' / 'embedding-model')
    local_embedding_model: str = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
    embedding_model: str = ''
    embedding_api_key: str = Field(default='', exclude=True, repr=False)
    embedding_timeout_seconds: float = Field(default=20, gt=0, le=60)
    embedding_max_tokens: int = Field(default=16000, ge=1000)
    official_source_prefixes: list[str] = Field(default_factory=list)
    llm_provider: str = "openai_compatible"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = Field(default="", exclude=True, repr=False)
    llm_model: str = ""
    llm_thinking_mode: Literal["default", "enabled", "disabled"] = "default"
    search_provider: str = "mock"
    tavily_api_key: str = Field(default="", exclude=True, repr=False)
    price_per_million_tokens: float = Field(default=0.0, ge=0)
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    max_questions: int = Field(default=8, ge=1, le=8)
    max_search_calls: int = Field(default=12, ge=1, le=40)
    max_candidates: int = Field(default=30, ge=1, le=100)
    max_fetch_pages: int = Field(default=8, ge=1, le=30)
    max_rounds: int = Field(default=2, ge=1, le=4)
    max_llm_calls: int = Field(default=10, ge=1, le=20)
    max_total_tokens: int = Field(default=100000, ge=1000)
    max_cost_usd: float = Field(default=0, ge=0)
    research_timeout_seconds: float = Field(default=180, gt=0)
    max_download_bytes: int = Field(default=2_000_000, ge=1024)
    fetch_concurrency: int = Field(default=3, ge=1, le=8)
    cache_ttl_seconds: float = Field(default=600, ge=0)
    context_token_budget: int = Field(default=16000, ge=2000)
    evidence_token_budget: int = Field(default=6500, ge=200)
    plan_max_tokens: int = Field(default=1800, ge=100)
    report_max_tokens: int = Field(default=4000, ge=100)
    review_max_tokens: int = Field(default=2400, ge=100)

def load_settings() -> Settings:
    values = {} if os.getenv('AGENTSCOUT_NO_DOTENV') == '1' else dict(dotenv_values(ROOT / '.env'))
    values.update(os.environ)
    data = {name: values[name.upper()] for name in Settings.model_fields if values.get(name.upper()) not in (None, '')}
    if 'official_source_prefixes' in data:
        data['official_source_prefixes'] = json.loads(data['official_source_prefixes'])
    return Settings(**data)


def safe_error(exc: Exception, settings: Settings) -> str:
    message = str(exc)
    for secret in (settings.llm_api_key, settings.tavily_api_key, settings.embedding_api_key, settings.database_url, settings.redis_url, settings.ui_secret):
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return message[:1000]
