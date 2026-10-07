from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    input_text: str
    input_type: str
    topic: str
    target_role: str | None
    classification: dict[str, Any]
    plan: dict[str, Any]
    search_results: list[dict[str, Any]]
    source_documents: list[dict[str, Any]]
    report: str
    citation_metrics: dict[str, Any]
    traces: list[dict[str, Any]]
    node_status: dict[str, str]
    errors: list[str]
    config: dict[str, Any]
    started_at: str
    ended_at: str | None
    total_duration_ms: int | None
    token_usage: int
    estimated_cost: float
    search_call_count: int
    fetch_success_rate: float
    search_counts: dict[str, int]
    llm_call_count: int
    citation_warning: str | None
    error_message: str | None

