from __future__ import annotations
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class RunStore:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("AGENTSCOUT_DB") or Path(__file__).resolve().parents[1] / "data" / "agent_scout.db")
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
            db.execute("CREATE TABLE IF NOT EXISTS run_details (run_id TEXT PRIMARY KEY, state_json TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS run_index (run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, input_text TEXT NOT NULL, status TEXT NOT NULL, total_duration_ms INTEGER, token_usage INTEGER, estimated_cost REAL)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_run_index_created ON run_index(created_at DESC)")
            db.execute("CREATE TABLE IF NOT EXISTS reviews (review_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, created_at TEXT NOT NULL, review_json TEXT NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_reviews_run ON reviews(run_id, created_at)")

    def save_run(self, state):
        # Full state is authoritative. Index contains only list-view metadata.
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO run_details(run_id,state_json) VALUES (?,?)", (state["run_id"], json.dumps(state, ensure_ascii=False)))
            db.execute("INSERT OR REPLACE INTO run_index VALUES (?,?,?,?,?,?,?)", (state["run_id"], state.get("created_at", ""), state.get("input_text", ""), state.get("status", "legacy"), state.get("total_duration_ms", 0), state.get("token_usage", 0), state.get("estimated_cost", 0)))

    def list_runs(self, limit=50):
        with self._connect() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM run_index ORDER BY created_at DESC LIMIT ?", (limit,))]
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='runs'").fetchone():
                old = db.execute("SELECT run_id,created_at,input_text,total_duration_ms,token_usage,estimated_cost FROM runs WHERE run_id NOT IN (SELECT run_id FROM run_index) ORDER BY created_at DESC LIMIT ?", (limit,))
                rows.extend({**dict(r), "status": "legacy"} for r in old)
        return sorted(rows, key=lambda r: r["created_at"], reverse=True)[:limit]

    def get_run(self, run_id):
        with self._connect() as db:
            row = db.execute("SELECT state_json FROM run_details WHERE run_id=?", (run_id,)).fetchone()
            if row:
                value = json.loads(row["state_json"])
                value.setdefault("status", "legacy")
                return value
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='runs'").fetchone():
                return None
            old = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if old is None:
                return None
            value = dict(old)
            mapping = {"plan_json": "plan", "search_json": "search_results", "documents_json": "source_documents", "citation_json": "citation_metrics", "node_status_json": "node_status", "errors_json": "errors", "metrics_json": "evaluation_metrics"}
            for column, key in mapping.items():
                value[key] = json.loads(value.pop(column) or "null")
            value.update(status="legacy", traces=[])
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trace_events'").fetchone():
                value["traces"] = [json.loads(r[0]) for r in db.execute("SELECT event_json FROM trace_events WHERE run_id=? ORDER BY id", (run_id,))]
            return value

    def save_review(self, review):
        with self._connect() as db:
            db.execute("INSERT INTO reviews VALUES (?,?,?,?)", (review["review_id"], review["run_id"], review["created_at"], json.dumps(review, ensure_ascii=False)))

    def list_reviews(self, run_id):
        with self._connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT review_json FROM reviews WHERE run_id=? ORDER BY created_at", (run_id,))]
