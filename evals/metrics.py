from statistics import mean
import re

ALIASES = {"state": ["状态"], "workflow": ["工作流"], "multi-agent": ["多智能体", "多代理"], "orchestration": ["编排"], "persistence": ["持久化"], "checkpointing": ["检查点"], "human-in-the-loop": ["人工介入", "人工审批"], "evaluation": ["评测", "评估"], "cost": ["成本"], "latency": ["延迟"], "accuracy": ["准确率", "准确性"], "bias": ["偏差", "偏见"], "testing": ["测试"], "debugging": ["调试"], "token": ["词元"], "observability": ["可观测性"], "validation": ["校验", "验证"], "timeouts": ["超时"], "cache": ["缓存"], "snippets": ["摘要"], "deduplicate": ["去重"]}


def keyword_recall(report, keywords):
    unique = {word.strip().casefold() for word in keywords if word.strip()}
    text = report.casefold()
    return sum(any(term in text for term in [word] + ALIASES.get(word, [])) for word in unique) / len(unique) if unique else 1.0


def evaluate_run(run, task, min_keyword_recall=.5):
    citations = run.get("citation_metrics", {})
    # Exclude echoed requests, headings, notices and bibliography from diagnostics.
    lines, bibliography = [], False
    for line in run.get("report", "").splitlines():
        if line.startswith("#"):
            bibliography = bool(re.search(r"来源列表|references|bibliography", line, re.I))
            continue
        if not bibliography and not line.startswith(">"):
            lines.append(line)
    recall = keyword_recall("\n".join(lines), task.get("expected_keywords", []))
    review = run.get("report_review", {})
    reasons = []
    if run.get("status") != "completed": reasons.append("research not completed: " + run.get("status", "unknown"))
    if not run.get("report", "").strip(): reasons.append("empty report")
    if not run.get("evidence"): reasons.append("no usable evidence")
    if citations.get("invalid_citations") or citations.get("uncited_claims"): reasons.append("unresolved citation issues")
    if not all(review.get(k) for k in ("task_compliant", "complete", "supported")) or review.get("issues"): reasons.append("semantic quality not verified")
    if run.get("errors"): reasons.append("critical node error")
    assessments = run.get("assessment", [])
    coverage = mean(a["status"] == "supported" for a in assessments) if assessments else 0.0
    if coverage != 1.0: reasons.append("question evidence gaps")
    return {"task_id": task["id"], "run_id": run["run_id"], "status": run.get("status"), "completed": not reasons, "execution_ok": run.get("execution_status") == "finished", "keyword_recall": recall, "question_coverage": coverage, "citation_coverage": citations.get("citation_coverage", 0), "source_utilization": citations.get("source_utilization", 0), "source_count": citations.get("cited_sources", 0), "latency_ms": run.get("total_duration_ms", 0), "cost": run.get("estimated_cost", 0), "tokens": run.get("token_usage", 0), "failure_reasons": reasons}


def summarize(rows):
    def average(key):
        return mean(row.get(key, 0) for row in rows) if rows else 0.0
    return {"task_count": len(rows), "completion_rate": average("completed"), "execution_rate": average("execution_ok"), "avg_question_coverage": average("question_coverage"), "avg_keyword_recall": average("keyword_recall"), "avg_citation_coverage": average("citation_coverage"), "avg_source_count": average("source_count"), "avg_latency_ms": average("latency_ms"), "avg_cost": average("cost"), "incomplete_tasks": sum(not row["completed"] for row in rows), "execution_failed_tasks": sum(not row.get("execution_ok", False) for row in rows), "expected_behavior_rate": mean(row["expected_behavior_ok"] for row in rows if "expected_behavior_ok" in row) if any("expected_behavior_ok" in row for row in rows) else None}
