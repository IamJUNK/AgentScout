from __future__ import annotations

from pathlib import Path
from dotenv import dotenv_values
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
MAX_SEARCH_RESULTS, MAX_FETCH_PAGES, MAX_PAGE_CHARS = 10, 5, 8000
REQUEST_TIMEOUT_SECONDS, MAX_PLAN_QUESTIONS = 10, 5

class Settings(BaseModel):
    llm_provider: str = "openai_compatible"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = Field(default="", exclude=True, repr=False)
    llm_model: str = ""
    search_provider: str = "mock"
    tavily_api_key: str = Field(default="", exclude=True, repr=False)
    price_per_million_tokens: float = Field(default=0.0, ge=0)
    llm_timeout_seconds: float = Field(default=30.0, gt=0)

def load_settings() -> Settings:
    values = dotenv_values(ROOT / ".env")
    return Settings(llm_provider=values.get("LLM_PROVIDER") or "openai_compatible", llm_base_url=values.get("LLM_BASE_URL") or "https://api.openai.com/v1", llm_api_key=values.get("LLM_API_KEY") or "", llm_model=values.get("LLM_MODEL") or "", search_provider=values.get("SEARCH_PROVIDER") or "mock", tavily_api_key=values.get("TAVILY_API_KEY") or "", price_per_million_tokens=float(values.get("PRICE_PER_MILLION_TOKENS") or 0), llm_timeout_seconds=float(values.get("LLM_TIMEOUT_SECONDS") or 30))

def safe_error(exc: Exception, settings: Settings) -> str:
    message = str(exc)
    for secret in (settings.llm_api_key, settings.tavily_api_key):
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return message[:1000]
