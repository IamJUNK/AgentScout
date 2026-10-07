from agent.graph import NODE_NAMES, run_research
from config import Settings
from evals.judge import judge_report
from storage.database import RunStore

def test_complete_mock_and_sqlite(tmp_path):
    store = RunStore(tmp_path / "test.db")
    run = run_research("比较 LangGraph 和 CrewAI", settings=Settings(), store=store)
    assert run["success"]
    assert run["citation_metrics"]["cited_sources"] >= 2
    assert run["token_usage"] == 0
    assert len(run["traces"]) == 14
    assert next(event for event in run["traces"] if event["node_name"] == "search_sources" and event["event_type"] == "success")["search_calls"] == 4
    assert set(run["node_status"]) == set(NODE_NAMES)
    saved = store.get_run(run["run_id"])
    assert saved["report"] == run["report"]
    assert saved["search_call_count"] == 4
    assert len(saved["traces"]) == 14
    assert store.list_runs()[0]["run_id"] == run["run_id"]

def test_empty_search_is_persisted(monkeypatch, tmp_path):
    monkeypatch.setattr("tools.search.MockSearchProvider.search", lambda *args, **kwargs: [])
    store = RunStore(tmp_path / "empty.db")
    run = run_research("test", settings=Settings(), store=store)
    assert not run["success"]
    assert run["node_status"]["search_sources"] == "error"
    assert "可切换 Mock" in run["error_message"]
    assert store.get_run(run["run_id"])["errors"]

def test_real_search_failure_is_readable(tmp_path):
    run = run_research("test", mock=False, settings=Settings(), store=RunStore(tmp_path / "fail.db"))
    assert not run["success"]
    assert "TAVILY_API_KEY" in run["error_message"]

def test_judge_optional():
    result, usage = judge_report("task", "report", Settings())
    assert result is None
    assert usage["tokens"] == 0

def test_api_client_real_mode_adapter(monkeypatch, tmp_path):
    from agent.llm import OpenAICompatibleClient
    from models.schemas import SearchResult
    import httpx
    def fake_post(url, **kwargs):
        system = kwargs["json"]["messages"][0]["content"]
        if system.startswith("Classify"):
            text = '{"input_type":"research_question","topic":"agent","target_role":null}'
        elif "questions" in system:
            text = '{"questions":["agent 1","agent 2","agent 3"],"search_queries":["agent 1","agent 2","agent 3"]}'
        else:
            text = '# agent\n## 关键发现\n- source [来源 1](https://example.com/1)\n- source [来源 2](https://example.com/2)'
        return httpx.Response(200, request=httpx.Request("POST", url), json={"choices":[{"message":{"content":text}}],"usage":{"total_tokens":100}})
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("tools.search.TavilySearchProvider.search", lambda *args, **kwargs: [SearchResult(title=str(i), url=f"https://example.com/{i}", snippet="agent") for i in (1, 2)])
    monkeypatch.setattr("tools.webpage._fetch_content", lambda *args: "agent source")
    run = run_research("agent", mock=False, settings=Settings(llm_api_key="fixture-placeholder", llm_model="fixture-model", tavily_api_key="fixture-placeholder", price_per_million_tokens=1), store=RunStore(tmp_path / "api.db"))
    assert run["success"]
    assert run["llm_call_count"] == 3
    assert sum(event.get("llm_calls", 0) for event in run["traces"]) == 3
    assert run["token_usage"] == 300
    assert abs(run["estimated_cost"] - 0.0003) < 1e-10

def test_prompt_comparison_changes_report_coverage(tmp_path):
    store = RunStore(tmp_path / "prompts.db")
    baseline = run_research("compare LangGraph CrewAI AutoGen", prompt_variant="baseline", store=store, settings=Settings())
    structured = run_research("compare LangGraph CrewAI AutoGen", prompt_variant="structured", store=store, settings=Settings())
    assert baseline["citation_metrics"]["cited_sources"] == 2
    assert structured["citation_metrics"]["cited_sources"] == 5
