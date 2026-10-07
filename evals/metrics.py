from __future__ import annotations
from statistics import mean

def keyword_recall(report: str, keywords: list[str]) -> float:
    unique = {word.strip().casefold() for word in keywords if word.strip()}
    return sum(word in report.casefold() for word in unique) / len(unique) if unique else 1.0

def evaluate_run(run: dict, task: dict, min_keyword_recall: float = 0.5) -> dict:
    citations = run.get("citation_metrics", {})
    recall = keyword_recall(run.get("report", ""), task.get("expected_keywords", []))
    sources = citations.get("cited_sources", 0)
    reasons = []
    if not run.get("report", "").strip(): reasons.append("empty report")
    if recall < task.get("min_keyword_recall", min_keyword_recall): reasons.append("keyword recall below threshold")
    if sources < task.get("required_source_count", 2): reasons.append("insufficient valid sources")
    if run.get("errors") or "error" in run.get("node_status", {}).values(): reasons.append("critical node error")
    return {"task_id": task["id"], "run_id": run["run_id"], "completed": not reasons, "keyword_recall": recall, "citation_coverage": citations.get("citation_coverage", 0.0), "source_count": sources, "latency_ms": run.get("total_duration_ms", 0), "cost": run.get("estimated_cost", 0.0), "tokens": run.get("token_usage", 0), "failure_reasons": reasons}

def summarize(rows: list[dict]) -> dict:
    return {"task_count": len(rows), "completion_rate": mean(r["completed"] for r in rows) if rows else 0.0, "avg_keyword_recall": mean(r["keyword_recall"] for r in rows) if rows else 0.0, "avg_citation_coverage": mean(r["citation_coverage"] for r in rows) if rows else 0.0, "avg_source_count": mean(r["source_count"] for r in rows) if rows else 0.0, "avg_latency_ms": mean(r["latency_ms"] for r in rows) if rows else 0.0, "avg_cost": mean(r["cost"] for r in rows) if rows else 0.0, "failed_tasks": sum(not r["completed"] for r in rows)}
