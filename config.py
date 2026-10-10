from __future__ import annotations

from pathlib import Path
from dotenv import dotenv_values
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent

class Settings(BaseModel):
    llm_provider: str = "openai_compatible"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = Field(default="", exclude=True, repr=False)
    llm_model: str = ""
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
    cache_ttl_seconds: float = Field(default=600, ge=0)
    context_token_budget: int = Field(default=16000, ge=2000)
    evidence_token_budget: int = Field(default=6500, ge=200)
    plan_max_tokens: int = Field(default=1800, ge=100)
    report_max_tokens: int = Field(default=4000, ge=100)
    review_max_tokens: int = Field(default=2400, ge=100)

def load_settings() -> Settings:
    values = dotenv_values(ROOT / ".env")
    # Centralized, validated budgets; secrets still come only from the local .env.
    return Settings(**{name: values[name.upper()] for name in Settings.model_fields if values.get(name.upper()) not in (None, "")})


def safe_error(exc: Exception, settings: Settings) -> str:
    message = str(exc)
    for secret in (settings.llm_api_key, settings.tavily_api_key):
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return message[:1000]
