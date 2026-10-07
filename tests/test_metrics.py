from evals.metrics import evaluate_run, keyword_recall, summarize

def test_keyword_recall():
    assert keyword_recall("State workflow", ["state", "workflow", "multi-agent", "cost"]) == 0.5

def test_empty_keywords():
    assert keyword_recall("", []) == 1

def test_completion_checks_critical_errors():
    run = {"run_id": "a", "report": "workflow", "citation_metrics": {"cited_sources": 2}, "errors": ["search failed"]}
    row = evaluate_run(run, {"id": "1", "expected_keywords": ["workflow"], "required_source_count": 2})
    assert not row["completed"]
    assert "critical node error" in row["failure_reasons"]

def test_empty_report_fails():
    row = evaluate_run({"run_id": "a", "report": ""}, {"id": "1", "expected_keywords": ["state"], "required_source_count": 2})
    assert not row["completed"]
    assert len(row["failure_reasons"]) == 3

def test_summary_empty():
    assert summarize([])["completion_rate"] == 0
