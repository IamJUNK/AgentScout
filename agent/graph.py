from __future__ import annotations
import copy
import time
from typing import Any, Callable
from uuid import uuid4
from langgraph.graph import END, START, StateGraph
from agent.nodes import AgentNodes
from config import Settings, load_settings, safe_error
from observability.tracing import run_traced_node, utc_now
from storage.database import RunStore

NODE_NAMES = ["classify_input", "plan_research", "search_sources", "fetch_pages", "synthesize_report", "validate_citations", "persist_run"]
_RESULT_CACHE: dict[tuple, dict] = {}

def run_research(input_text: str, *, mock: bool = True, search_count: int = 5, model: str = "", input_mode: str = "auto", prompt_variant: str = "structured", use_cache: bool = False, settings: Settings | None = None, store: RunStore | None = None, on_node: Callable[[str], None] | None = None) -> dict[str, Any]:
    if not input_text.strip():
        raise ValueError("请输入研究主题或岗位描述。")
    settings, store = settings or load_settings(), store or RunStore()
    options = {"mock": mock, "search_count": max(1, min(10, search_count)), "model": model or settings.llm_model, "input_mode": input_mode, "prompt_variant": prompt_variant}
    key = (input_text.strip(), tuple(sorted(options.items())), settings.llm_base_url, str(store.path.resolve()))
    if use_cache and key in _RESULT_CACHE:
        cached = store.get_run(_RESULT_CACHE[key]["run_id"]) or copy.deepcopy(_RESULT_CACHE[key])
        cached["cache_hit"] = True
        return cached
    start = time.perf_counter()
    state = {"run_id": str(uuid4()), "created_at": utc_now(), "started_at": utc_now(), "input_text": input_text.strip(), "config": options, "traces": [], "node_status": {}, "errors": [], "warnings": [], "token_usage": 0, "estimated_cost": 0.0, "llm_call_count": 0, "search_call_count": 0, "report": "", "fetch_success_rate": 0.0}
    latest = {"state": state}
    nodes = AgentNodes(settings, options)
    if not mock and not nodes.client.available:
        state["warnings"].append(".env 缺少 LLM_API_KEY 或 LLM_MODEL，使用规则规划与摘要。")

    def persist(current):
        current["ended_at"], current["total_duration_ms"] = utc_now(), int((time.perf_counter() - start) * 1000)
        store.save_run(current)
        return {"persisted": True}

    def wrapped(name, action):
        def execute(current):
            latest["state"] = current
            if on_node:
                on_node(name)
            before_tokens, before_cost = current["token_usage"], current["estimated_cost"]
            def safe_action(s):
                try:
                    changes = action(s)
                    return {**(changes or {}), "_node_tokens": s["token_usage"] - before_tokens, "_node_cost": s["estimated_cost"] - before_cost}
                except Exception as exc:
                    raise RuntimeError(safe_error(exc, settings)) from None
            return run_traced_node(current, name, safe_action, current.get("topic", current["input_text"])[:200])
        return execute

    graph = StateGraph(dict)
    for name in NODE_NAMES:
        graph.add_node(name, wrapped(name, persist if name == "persist_run" else getattr(nodes, name)))
    graph.add_edge(START, NODE_NAMES[0])
    for previous, following in zip(NODE_NAMES, NODE_NAMES[1:]):
        graph.add_edge(previous, following)
    graph.add_edge(NODE_NAMES[-1], END)
    try:
        state = graph.compile().invoke(state)
    except Exception as exc:
        state = latest["state"]
        state["error_message"] = safe_error(exc, settings)
        if not state["errors"]:
            state["errors"].append(state["error_message"])
    finally:
        state["ended_at"], state["total_duration_ms"] = utc_now(), int((time.perf_counter() - start) * 1000)
        state["success"] = bool(state["report"]) and not state["errors"]
        # Persist the terminal event of the persistence node as well.
        try:
            store.save_run(state)
        except Exception as exc:
            state["errors"].append("SQLite 保存失败：" + safe_error(exc, settings))
            state["success"] = False
    if state["success"]:
        if len(_RESULT_CACHE) >= 32:
            _RESULT_CACHE.pop(next(iter(_RESULT_CACHE)))
        _RESULT_CACHE[key] = copy.deepcopy(state)
    return state
