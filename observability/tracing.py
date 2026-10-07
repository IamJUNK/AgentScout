from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Any, Callable
from models.schemas import TraceEvent

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def run_traced_node(state: dict[str, Any], node_name: str, fn: Callable[[dict[str, Any]], dict[str, Any]], input_summary: str = "") -> dict[str, Any]:
    started = time.perf_counter()
    started_at = utc_now()
    before_llm, before_search = state.get("llm_call_count", 0), state.get("search_call_count", 0)
    traces = list(state.get("traces", []))
    traces.append(TraceEvent(run_id=state["run_id"], node_name=node_name, event_type="start", started_at=started_at, input_summary=input_summary[:500]).model_dump())
    state["traces"] = traces
    state.setdefault("node_status", {})[node_name] = "running"
    try:
        changes = fn(state) or {}
        state.update(changes)
        duration = int((time.perf_counter() - started) * 1000)
        state["node_status"][node_name] = "success"
        event = TraceEvent(run_id=state["run_id"], node_name=node_name, event_type="success", started_at=started_at, ended_at=utc_now(), duration_ms=duration, input_summary=input_summary[:500], output_summary="; ".join(f"{key}: {len(value) if isinstance(value, (list, dict)) else str(value)[:100]}" for key, value in changes.items() if not key.startswith("_") and key != "traces")[:500], token_usage=changes.get("_node_tokens"), estimated_cost=changes.get("_node_cost"))
        event.llm_calls = state.get("llm_call_count", 0) - before_llm
        event.search_calls = state.get("search_call_count", 0) - before_search
        state["traces"] = list(state.get("traces", [])) + [event.model_dump()]
        return state
    except Exception as exc:
        duration = int((time.perf_counter() - started) * 1000)
        state.setdefault("errors", []).append(f"{node_name}: {exc}")
        state["node_status"][node_name] = "error"
        state["traces"] = list(state.get("traces", [])) + [TraceEvent(run_id=state["run_id"], node_name=node_name, event_type="error", started_at=started_at, ended_at=utc_now(), duration_ms=duration, input_summary=input_summary[:500], error_message=str(exc)).model_dump()]
        raise
