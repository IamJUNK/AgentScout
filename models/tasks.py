from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

TERMINAL = {'succeeded', 'failed', 'cancelled'}
ACTIVE = {'pending_dispatch', 'queued', 'running'}

class TaskRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    input_text: str = Field(min_length=1, max_length=12000)
    supplied_text: str = Field(default='', max_length=150000)
    mock: bool = True
    search_count: int = Field(default=5, ge=1, le=10)
    retrieval_mode: Literal['bm25', 'hybrid'] = 'bm25'
    max_tokens: int = Field(default=30000, ge=1000, le=100000)
    timeout_seconds: int = Field(default=180, ge=10, le=600)
    force_refresh: bool = False
    official_source_prefixes: list[str] = Field(default_factory=list, max_length=12)

    @field_validator('official_source_prefixes')
    @classmethod
    def public_prefixes(cls, values):
        from tools.urls import canonical_url
        result = []
        for value in values:
            if not value.startswith('https://') or len(value) > 500:
                raise ValueError('Documentation prefixes must be HTTPS URLs, at most 500 characters')
            result.append(canonical_url(value))
        return list(dict.fromkeys(result))
