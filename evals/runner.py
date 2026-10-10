from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
from typing import Callable
from agent.graph import run_research
from config import ROOT, Settings, load_settings
from evals.judge import attach_judge
from evals.metrics import evaluate_run, summarize
from observability.tracing import utc_now
from storage.database import RunStore

def load_dataset(path: Path = ROOT / "evals" / "dataset.json") -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))

def run_evaluation(*, limit: int = 10, mock: bool = True, variant: str = "structured", model: str = "", judge: bool = False, settings: Settings | None = None, store: RunStore | None = None, on_progress: Callable | None = None) -> dict:
    settings, store = settings or load_settings(), store or RunStore()
    tasks, rows = load_dataset()[:max(1, min(limit, 20))], []
    for index, task in enumerate(tasks):
        started = time.perf_counter()
        run = run_research(task["input"], supplied_text=task.get("supplied_text", ""), mock=mock, model=model, prompt_variant=variant, settings=settings, store=store)
        review = attach_judge(run, task["input"], settings, model, store=store) if judge else None
        row = evaluate_run(run, task)
        if judge:
            row["review"] = review
        row["latency_ms"] = int((time.perf_counter() - started) * 1000)
        row.update(input=task["input"], expected_keywords=task.get("expected_keywords", []))
        expected_status = task.get("expected_mock_status") if mock else None
        if expected_status:
            row.update(expected_status=expected_status, expected_behavior_ok=run["status"] == expected_status)
        run["evaluation_metrics"] = row
        store.save_run(run)
        rows.append(row)
        if on_progress:
            on_progress(index + 1, len(tasks))
    return {"schema_version": 2, "created_at": utc_now(), "mock": mock, "variant": variant, "model": "local-rules" if mock else (model or settings.llm_model or "local-rules"), "settings": settings.model_dump(), "summary": summarize(rows), "results": rows, "runs": [store.get_run(row["run_id"]) for row in rows]}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--variant", choices=["baseline", "structured"], default="structured")
    parser.add_argument("--model", default="")
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "evals" / "results" / "latest.json")
    args = parser.parse_args()
    result = run_evaluation(limit=args.limit, mock=not args.real, variant=args.variant, model=args.model, judge=args.judge)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
