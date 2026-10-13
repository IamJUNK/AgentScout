"""Run one bounded real research task and save diagnostics without credentials."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import load_settings, safe_error
from agent.graph import run_research
from storage.database import RunStore

OUT = ROOT / 'data' / 'live-validation-2026-10-13'
OUT.mkdir(parents=True, exist_ok=True)
tag = sys.argv[1] if len(sys.argv) > 1 else 'sqlite-wal'
if tag not in {'sqlite-wal', 'sqlite-wal-nonthinking', 'sqlite-wal-attributed'}:
    raise SystemExit('Unknown validation label')
s = load_settings().model_copy(update={
    'max_questions': 2, 'max_search_calls': 4, 'max_fetch_pages': 4,
    'max_rounds': 2, 'max_llm_calls': 10, 'max_total_tokens': 30000,
    'evidence_token_budget': 2500, 'context_token_budget': 12000,
    'plan_max_tokens': 1200, 'report_max_tokens': 2000,
    'review_max_tokens': 1800, 'llm_timeout_seconds': 45,
    'research_timeout_seconds': 180,
})
task = ('根据 SQLite 官方文档，解释 WAL 是否允许多个写入者同时写入，'
        '以及开启 WAL 后 SQLITE_BUSY 是否仍可能发生。两问分别作答，引用原文。')
print('Starting one real research task; token budget=30000; model=' + s.llm_model, flush=True)
try:
    state = run_research(task, mock=False, search_count=3, force_refresh=True,
                         settings=s, store=RunStore(OUT / 'runs.db'),
                         on_node=lambda name: print('node: ' + name, flush=True))
    # Settings.model_dump excludes both API keys. Also redact all string leaves.
    def redact(value):
        if isinstance(value, str):
            for secret in (s.llm_api_key, s.tavily_api_key):
                if secret:
                    value = value.replace(secret, '[REDACTED]')
            return value
        if isinstance(value, dict):
            return {k: redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [redact(v) for v in value]
        return value
    clean = redact(state)
    (OUT / (tag + '-state.json')).write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / (tag + '-report.md')).write_text(clean.get('report', ''), encoding='utf-8')
    summary = {k: clean.get(k) for k in ('run_id', 'status', 'execution_status', 'success',
               'total_duration_ms', 'token_usage', 'llm_call_count', 'search_call_count',
               'warnings', 'errors', 'budget_exhausted', 'stop_reason', 'citation_metrics',
               'report_review', 'assessment')}
    summary['documents'] = [{k: d.get(k) for k in ('url', 'fetch_status', 'fetch_error', 'download_truncated')}
                            for d in clean.get('source_documents', [])]
    (OUT / (tag + '-summary.json')).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=True), flush=True)
except Exception as exc:
    print('Run failed: ' + safe_error(exc, s), flush=True)
    raise SystemExit(1)
