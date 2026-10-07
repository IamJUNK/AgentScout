from __future__ import annotations
import json
import os
import sqlite3
from pathlib import Path
from typing import Any
from contextlib import contextmanager

DEFAULT_DB_PATH = Path(os.getenv("AGENTSCOUT_DB", Path(__file__).resolve().parents[1] / "data" / "agent_scout.db"))

class RunStore:
    def __init__(self, path: str | Path = DEFAULT_DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()
    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()
    def initialize(self):
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, input_text TEXT NOT NULL, input_type TEXT, topic TEXT,
                plan_json TEXT, search_json TEXT, documents_json TEXT, report TEXT, citation_json TEXT, total_duration_ms INTEGER,
                token_usage INTEGER, estimated_cost REAL, node_status_json TEXT, errors_json TEXT, metrics_json TEXT)""")
            db.execute("CREATE TABLE IF NOT EXISTS trace_events (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, event_json TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS run_details (run_id TEXT PRIMARY KEY, state_json TEXT NOT NULL)")
    def save_run(self, state: dict[str, Any]):
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO run_details VALUES (?, ?)", (state["run_id"], _json(state)))
            db.execute("INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                state["run_id"], state.get("created_at", ""), state.get("input_text", ""), state.get("input_type"), state.get("topic"),
                _json(state.get("plan")), _json(state.get("search_results", [])), _json(state.get("source_documents", [])), state.get("report", ""),
                _json(state.get("citation_metrics", {})), state.get("total_duration_ms", 0), state.get("token_usage", 0), state.get("estimated_cost", 0.0),
                _json(state.get("node_status", {})), _json(state.get("errors", [])), _json(state.get("evaluation_metrics", {}))))
            db.execute("DELETE FROM trace_events WHERE run_id = ?", (state["run_id"],))
            db.executemany("INSERT INTO trace_events(run_id, event_json) VALUES (?, ?)", [(state["run_id"], _json(x)) for x in state.get("traces", [])])
    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [_decode(row) for row in rows]
    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            detail = db.execute("SELECT state_json FROM run_details WHERE run_id = ?", (run_id,)).fetchone()
            events = db.execute("SELECT event_json FROM trace_events WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
        if row is None:
            return None
        value = json.loads(detail["state_json"]) if detail else _decode(row)
        value["traces"] = [json.loads(x["event_json"]) for x in events]
        return value

def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)

def _decode(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    mapping = {"plan_json": "plan", "search_json": "search_results", "documents_json": "source_documents", "citation_json": "citation_metrics", "node_status_json": "node_status", "errors_json": "errors", "metrics_json": "evaluation_metrics"}
    for column, key in mapping.items():
        raw = result.pop(column)
        result[key] = json.loads(raw) if raw else ({} if key in {"plan", "citation_metrics", "node_status", "evaluation_metrics"} else [])
    return result
