import pytest
from agent.citations import validate_report
from agent.graph import run_research
from agent.llm import extract_json
from config import Settings, safe_error
from evals.judge import attach_judge
from storage.database import RunStore

def test_nonstandard_link_is_detected():
    assert validate_report("[external](https://bad.example)", [{"url":"https://example.com"}]).invalid_citations == ["https://bad.example"]

def test_unsupported_percentage_is_flagged():
    metric = validate_report("## 关键发现\n- 保证成功，准确率 100% [来源 1](https://example.com)", [{"url":"https://example.com"}], [{"url":"https://example.com", "content":"a limited tool"}])
    assert metric.uncited_claims

def test_secrets_are_not_in_settings_serialization():
    settings = Settings(llm_api_key="fixture-secret", tavily_api_key="fixture-search")
    assert "fixture-secret" not in settings.model_dump_json()
    assert "fixture-search" not in repr(settings)
    assert safe_error(ValueError("fixture-secret fixture-search"), settings) == "[REDACTED] [REDACTED]"

def test_extract_json_fence():
    assert extract_json('```json\n{"a":1}\n```') == {"a":1}
    with pytest.raises(ValueError): extract_json("invalid")

def test_missing_judge_is_traced_and_persisted(tmp_path):
    store = RunStore(tmp_path / "judge.db")
    run = run_research("LangGraph", store=store, settings=Settings())
    attach_judge(run, "LangGraph", Settings())
    store.save_run(run)
    assert run["judge"] is None
    assert run["llm_call_count"] == 0
    assert len(store.get_run(run["run_id"])["traces"]) == 16

def test_planner_error_uses_fallback(monkeypatch):
    from agent.nodes import AgentNodes
    from agent.fallback import classify_input_fallback
    nodes = AgentNodes(Settings(llm_api_key="fixture-placeholder", llm_model="fixture"), {"mock":False})
    def broken(*args): raise ValueError("bad JSON")
    monkeypatch.setattr(nodes.client, "chat", broken)
    state = {"input_text":"LangGraph comparison", "classification": classify_input_fallback("LangGraph comparison").model_dump(), "warnings":[], "llm_call_count":0, "token_usage":0, "estimated_cost":0.0}
    plan = nodes.plan_research(state)["plan"]
    assert len(plan["questions"]) == 4
    assert state["warnings"]
    assert state["llm_call_count"] == 1

def test_citation_repair_once(monkeypatch):
    from agent.nodes import AgentNodes
    nodes = AgentNodes(Settings(llm_api_key="fixture-placeholder", llm_model="fixture"), {"mock":False})
    monkeypatch.setattr(nodes.client, "chat", lambda *args: ("## 关键发现\n- bad [来源 1](https://bad.example)", 5))
    state = {"report":"## 关键发现\n- bad [来源 1](https://bad.example)", "search_results":[{"url":"https://good.example"}], "source_documents":[{"url":"https://good.example","content":"good"}], "warnings":[], "llm_call_count":0, "token_usage":0, "estimated_cost":0.0}
    output = nodes.validate_citations(state)
    assert state["citation_repair_count"] == 1
    assert state["llm_call_count"] == 1
    assert output["citation_warning"]

def test_estimated_usage_for_chinese(monkeypatch):
    from agent.nodes import AgentNodes
    nodes = AgentNodes(Settings(llm_api_key="fixture-placeholder", llm_model="fixture", price_per_million_tokens=2), {"mock":False})
    monkeypatch.setattr(nodes.client, "chat", lambda *args: ("中文回答", None))
    state = {"llm_call_count":0, "token_usage":0, "estimated_cost":0.0}
    nodes.call_llm(state, "系统提示", "研究问题")
    assert state["token_usage"] == 6
    assert state["usage_estimated"]
    assert state["estimated_cost"] == 0.000012

def test_private_web_addresses_are_rejected():
    from tools.webpage import _check_public_host
    for address in ("http://127.0.0.1", "http://localhost", "http://192.168.1.1"):
        with pytest.raises(ValueError):
            _check_public_host(address)

def test_judge_invalid_json_still_counts_paid_tokens(monkeypatch):
    from evals.judge import judge_report
    monkeypatch.setattr("agent.llm.OpenAICompatibleClient.chat", lambda *args: ("malformed", 100))
    result, usage = judge_report("task", "report", Settings(llm_api_key="fixture-placeholder", llm_model="fixture", price_per_million_tokens=2))
    assert result is None
    assert usage["tokens"] == 100
    assert usage["cost"] == 0.0002

def test_cache_reuses_latest_persisted_trace(tmp_path):
    store = RunStore(tmp_path / "cache.db")
    original = run_research("cache LangGraph", store=store, settings=Settings())
    attach_judge(original, "cache LangGraph", Settings())
    store.save_run(original)
    cached = run_research("cache LangGraph", store=store, settings=Settings(), use_cache=True)
    assert cached["cache_hit"]
    assert cached["run_id"] == original["run_id"]
    assert len(cached["traces"]) == len(original["traces"])
