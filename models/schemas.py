from __future__ import annotations
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field


def as_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResearchBrief(BaseModel):
    original_request: str
    as_of: str = Field(default_factory=as_utc_iso)
    objective: str
    scope: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    time_scope: str = ""
    output_requirements: list[str] = Field(default_factory=list)
    freshness_required: bool = False
    allow_web_research: bool = True


class ResearchQuestion(BaseModel):
    id: str = ""
    text: str = Field(min_length=1)
    queries: list[str] = Field(min_length=1, max_length=3)


class ResearchPlan(BaseModel):
    questions: list[ResearchQuestion] = Field(min_length=1, max_length=8)


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""
    source: str = "unknown"
    source_id: str = ""
    question_ids: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    published_at: str | None = None


class SourceDocument(BaseModel):
    title: str
    url: str
    source_id: str = ""
    question_ids: list[str] = Field(default_factory=list)
    content: str = ""
    snippet: str = ""
    retrieved_at: str = Field(default_factory=as_utc_iso)
    published_at: str | None = None
    publication_date_source: str | None = None
    fetch_status: Literal["success", "partial", "failed", "snippet_only"] = "success"
    fetch_error: str | None = None
    content_type: str = ""
    download_truncated: bool = False
    cache_hit: bool = False
    mock: bool = False


class EvidenceChunk(BaseModel):
    id: str
    source_id: str
    url: str
    title: str
    text: str
    section: str = ""
    start: int
    end: int
    kind: Literal["body", "snippet", "mock", "user"]
    question_ids: list[str] = Field(default_factory=list)
    retrieved_at: str
    published_at: str | None = None
    download_truncated: bool = False


class QuestionAssessment(BaseModel):
    question_id: str
    status: Literal["supported", "partial", "missing", "conflicting"]
    evidence_ids: list[str] = Field(default_factory=list)
    explanation: str = Field(min_length=1)
    next_queries: list[str] = Field(default_factory=list, max_length=2)
    temporal_applicability: Literal["confirmed", "unknown", "not_applicable"] = "unknown"


class EvidenceAssessment(BaseModel):
    questions: list[QuestionAssessment]


class ReportReview(BaseModel):
    task_compliant: bool
    complete: bool
    supported: bool
    issues: list[str]


class CitationMetrics(BaseModel):
    total_sources: int = 0
    cited_sources: int = 0
    source_utilization: float = 0.0
    citation_coverage: float = 0.0
    claim_count: int = 0
    attributed_claim_count: int = 0
    invalid_citations: list[str] = Field(default_factory=list)
    uncited_claims: list[str] = Field(default_factory=list)


class TraceEvent(BaseModel):
    run_id: str
    node_name: str
    event_type: Literal["start", "success", "error", "warning", "skipped"]
    started_at: str = Field(default_factory=as_utc_iso)
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
    accuracy: float = Field(ge=0, le=1)
    completeness: float = Field(ge=0, le=1)
    citation_quality: float = Field(ge=0, le=1)
    overall: float = Field(ge=0, le=1)
    reasoning: str = Field(min_length=1)
