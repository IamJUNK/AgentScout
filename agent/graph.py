from __future__ import annotations
import time
from uuid import uuid4
from langgraph.graph import END, START, StateGraph
from agent.nodes import AgentNodes
from agent.state import AgentState
from config import load_settings, safe_error
from observability.tracing import run_traced_node, utc_now
from storage.database import RunStore

NODE_NAMES = ["prepare_research", "plan_research", "search_sources", "fetch_pages", "assess_evidence", "synthesize_report", "validate_citations", "finalize", "persist_run"]


def run_research(input_text, *, supplied_text="", mock=True, search_count=5, model="", prompt_variant="structured", force_refresh=False, settings=None, store=None, on_node=None):
    if not input_text.strip():
        raise ValueError("请输入研究需求。")
    if prompt_variant not in {"baseline", "structured"}:
        raise ValueError("Unknown report strategy")
    settings, store = settings or load_settings(), store or RunStore()
    options = {"mock": mock, "search_count": max(1, min(10, search_count)), "model": model or settings.llm_model, "prompt_variant": prompt_variant, "force_refresh": force_refresh}
    # Every execution gets its own identity; only immutable page content is cached.
    state = {"run_id": str(uuid4()), "created_at": utc_now(), "started_at": utc_now(), "input_text": input_text.strip(), "config": {**options, "settings": settings.model_dump()}, "traces": [], "node_status": {}, "errors": [], "warnings": [], "token_usage": 0, "estimated_cost": 0.0, "llm_call_count": 0, "search_call_count": 0, "report": "", "fetch_success_rate": 0.0, "status": "running", "execution_status": "running", "success": False, "budget_exhausted": False}
    started = time.perf_counter()
    state["supplied_text"] = supplied_text
    latest = {"state": state}
    nodes = AgentNodes(settings, options)
    if not mock and not nodes.client.available:
        state["warnings"].append("未配置云端模型：只能收集资料，无法完成语义评估和研究答案。")

    def wrapped(name):
        def execute(current):
            latest["state"] = current
            def action(s):
                try:
                    if on_node:
                        on_node(name)
                    changes = getattr(nodes, name)(s)
                    s.update(changes or {})
                    if name == "assess_evidence":
                        s["next_step"] = nodes.should_research_more(s)
                    return changes
                except Exception as exc:
                    raise RuntimeError(safe_error(exc, settings)) from None
            result = run_traced_node(current, name, action, current["input_text"][:200])
            # Checkpoint completed node snapshots; resume is deliberately not automatic.
            store.save_run(result)
            return result
        return execute

    graph = StateGraph(AgentState)
    for name in NODE_NAMES[:-1]:
        graph.add_node(name, wrapped(name))
    graph.add_edge(START, "prepare_research")
    graph.add_edge("prepare_research", "plan_research")
    graph.add_edge("plan_research", "search_sources")
    graph.add_edge("search_sources", "fetch_pages")
    graph.add_edge("fetch_pages", "assess_evidence")
    graph.add_conditional_edges("assess_evidence", lambda s: s["next_step"], {"search_sources": "search_sources", "synthesize_report": "synthesize_report"})
    graph.add_edge("synthesize_report", "validate_citations")
    graph.add_edge("validate_citations", "finalize")
    graph.add_edge("finalize", END)
    try:
        state = graph.compile().invoke(state, {"recursion_limit": 50})
    except Exception as exc:
        state = latest["state"]
        state["error_message"] = safe_error(exc, settings)
        if not state["errors"]:
            state["errors"].append(state["error_message"])
        state.update(status="failed", execution_status="failed", success=False)
    finally:
        state["ended_at"] = utc_now()
        state["total_duration_ms"] = int((time.perf_counter()-started)*1000)
        try:
            run_traced_node(state, "persist_run", lambda s: (store.save_run(s) or {"persisted": True}))
            state["total_duration_ms"] = int((time.perf_counter()-started)*1000)
            store.save_run(state)
        except Exception as exc:
            state["errors"].append("SQLite 保存失败：" + safe_error(exc, settings))
            state.update(status="failed", execution_status="failed", success=False)
    return state
