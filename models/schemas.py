from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class InputClassification(BaseModel):
    input_type: Literal["research_question", "job_description"]
    topic: str
    target_role: str | None = None


class ResearchPlan(BaseModel):
    questions: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""
    source: str = "unknown"


class SourceDocument(BaseModel):
    title: str
    url: str
    content: str = ""
    retrieved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fetch_status: Literal["success", "failed", "snippet_only"] = "success"
    fetch_error: str | None = None


class CitationMetrics(BaseModel):
    total_sources: int = 0
    cited_sources: int = 0
    citation_coverage: float = 0.0
    invalid_citations: list[str] = Field(default_factory=list)
    uncited_claims: list[str] = Field(default_factory=list)


class TraceEvent(BaseModel):
    run_id: str
    node_name: str
    event_type: Literal["start", "success", "error"]
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended_at: str | None = None
    duration_ms: int | None = None
    input_summary: str = ""
    output_summary: str = ""
    error_message: str | None = None
    token_usage: int | None = None
    estimated_cost: float | None = None
    llm_calls: int = 0
    search_calls: int = 0


class JudgeResult(BaseModel):
    accuracy: float = 0.0
    completeness: float = 0.0
    citation_quality: float = 0.0
    overall: float = 0.0
    reasoning: str = ""


def as_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

