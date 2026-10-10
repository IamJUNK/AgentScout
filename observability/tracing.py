from __future__ import annotations
import time
from models.schemas import TraceEvent, as_utc_iso

utc_now = as_utc_iso


def run_traced_node(state, node_name, fn, input_summary=""):
    started, stamp = time.perf_counter(), utc_now()
    counters = {key: state.get(key, 0) for key in ("llm_call_count", "search_call_count", "token_usage", "estimated_cost")}
    warning_count = len(state.get("warnings", []))
    state.setdefault("traces", []).append(TraceEvent(run_id=state["run_id"], node_name=node_name, event_type="start", started_at=stamp, input_summary=input_summary[:500]).model_dump())
    state.setdefault("node_status", {})[node_name] = "running"
    error, changes = None, {}
    try:
        changes = fn(state) or {}
        state.update(changes)
    except Exception as exc:
        error = exc
        state.setdefault("errors", []).append(f"{node_name}: {exc}")
        raise
    finally:
        status = "error" if error else ("warning" if len(state.get("warnings", [])) > warning_count else "success")
        state["node_status"][node_name] = status
        event = TraceEvent(run_id=state["run_id"], node_name=node_name, event_type=status, started_at=stamp, ended_at=utc_now(), duration_ms=int((time.perf_counter()-started)*1000), input_summary=input_summary[:500], error_message=str(error) if error else None, output_summary="; ".join(f"{k}: {len(v) if isinstance(v, (list, dict)) else str(v)[:100]}" for k, v in changes.items() if not k.startswith("_") and k != "traces")[:500], token_usage=state.get("token_usage", 0)-counters["token_usage"], estimated_cost=state.get("estimated_cost", 0)-counters["estimated_cost"], llm_calls=state.get("llm_call_count", 0)-counters["llm_call_count"], search_calls=state.get("search_call_count", 0)-counters["search_call_count"])
        state["traces"].append(event.model_dump())
    return state
