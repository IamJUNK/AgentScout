from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    requirements: list[dict]
    structured_report: dict
    claim_review: dict
    quality_errors: list[str]
    external_calls: list[dict]
    run_id: str
    created_at: str
    started_at: str
    ended_at: str
    input_text: str
    supplied_text: str
    input_type: str
    topic: str
    brief: dict[str, Any]
    config: dict[str, Any]
    plan: dict[str, Any]
    search_results: list[dict]
    source_documents: list[dict]
    evidence: list[dict]
    evidence_selection: dict
    evidence_fingerprint: str
    evidence_round: int
    no_new_evidence: bool
    retrieval_metadata: dict
    assessment: list[dict]
    round: int
    searched_queries: list[str]
    attempted_urls: list[str]
    search_counts: dict
    next_step: str
    stop_reason: str
    budget_exhausted: bool
    report: str
    report_kind: str
    report_review: dict
    citation_metrics: dict
    citation_warning: str | None
    citation_repair_count: int
    duplicate_citation_urls: list[str]
    status: str
    execution_status: str
    success: bool
    errors: list[str]
    error_message: str
    warnings: list[str]
    traces: list[dict]
    node_status: dict
    token_usage: int
    estimated_cost: float
    llm_call_count: int
    search_call_count: int
    fetch_success_rate: float
    llm_usage: list[dict]
    usage_estimated: bool
    cost_incomplete: bool
    unaccounted_token_budget: int
    total_duration_ms: int
    persisted: bool
    evaluation_metrics: dict
