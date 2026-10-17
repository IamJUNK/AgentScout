"""Authorized live smoke: <=5 tasks, <=150k reserved model tokens, <=20 searches.

Reserve each task's entire budget before execution, including interrupted runs.
Results never overwrite earlier runs. Credentials are not serialized.
"""
import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import load_settings
from agent.graph import run_research
from storage.memory import MemoryRunStore

CASES = {
    'wal': ('根据 SQLite 官方文档，解释 WAL 是否允许多个写入者同时写入，以及开启 WAL 后 SQLITE_BUSY 是否仍可能发生。两问分别作答，引用原文。', ''),
    'material': ('仅根据提供材料，不要联网。分别回答：1. 服务最多允许多少个写入者？2. 网络断开是否意味着已经发出的调用没有费用？', '服务协议：同一资源同时最多允许一个写入者。读者可并发读取。网络连接断开不代表供应商未执行请求；已执行但响应未返回的调用可能产生费用，消耗暂时未知。'),
    'conflict': ('仅根据提供材料，不要联网。当前接口请求上限是多少？说明证据是否足够。', '文件 A（日期不详）：请求上限为每分钟 10 次。文件 B（日期不详）：请求上限为每分钟 5 次。两份材料均没有版本标识。'),
    'tail': ('仅根据提供材料，不要联网。设备 Falcon 的最高压力是多少？限制条件是什么？', '背景说明：此段不包含设备参数。\n' * 700 + '\n# Falcon 技术条件\n设备 Falcon 的最高压力是 12 MPa。该上限仅在环境温度低于 30 摄氏度且使用新密封圈时适用。其他条件下的上限未提供。'),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('case', choices=CASES)
    args = parser.parse_args()
    destination = ROOT / 'data' / 'upgrade-local'
    destination.mkdir(parents=True, exist_ok=True)
    lock = destination / 'live.lock'
    # O_EXCL lock intentionally survives a crash; inspect ledger before manual removal.
    with lock.open('x', encoding='utf-8') as f:
        f.write(args.case)
    try:
        ledger_path = destination / 'live-ledger.json'
        ledger = json.loads(ledger_path.read_text(encoding='utf-8')) if ledger_path.exists() else []
        if len(ledger) >= 5 or sum(r['reserved_tokens'] for r in ledger) + 30000 > 150000 or sum(r['reserved_searches'] for r in ledger) + 4 > 20:
            raise SystemExit('Authorized validation budget exhausted')
        ident = args.case + '-' + uuid4().hex[:10]
        entry = {'id': ident, 'case': args.case, 'reserved_tokens': 30000, 'reserved_searches': 4, 'status': 'started'}
        ledger.append(entry)
        ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding='utf-8')
        settings = load_settings().model_copy(update={'max_total_tokens':30000, 'max_search_calls':4, 'max_fetch_pages':4,
            'max_rounds':2, 'max_llm_calls':10, 'max_questions':4, 'research_timeout_seconds':240,
            'llm_timeout_seconds':45, 'context_token_budget':18000, 'evidence_token_budget':3500,
            'report_max_tokens':2600, 'review_max_tokens':2200, 'plan_max_tokens':1800,
            'official_source_prefixes':['https://sqlite.org/', 'https://www.sqlite.org/'], 'retrieval_mode':'hybrid' if args.case == 'tail' else 'bm25'})
        def progress(node):
            print(node, flush=True)
        request, material = CASES[args.case]
        result = run_research(request, supplied_text=material, settings=settings, mock=False, store=MemoryRunStore(), on_node=progress, force_refresh=True)
        result.pop('config', None)
        (destination / (ident + '-state.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        (destination / (ident + '-report.md')).write_text(result['report'],encoding='utf-8')
        entry.update(status=result['status'],execution=result['execution_status'],tokens=result['token_usage'],
            unknown_reservation=result.get('unaccounted_token_budget',0),searches=result['search_call_count'],llm_calls=result['llm_call_count'],
            duration_ms=result['total_duration_ms'],quality_errors=result.get('quality_errors',[]),warnings=result.get('warnings',[]))
        ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(entry,ensure_ascii=False,indent=2))
    finally:
        lock.unlink(missing_ok=True)

if __name__ == '__main__': main()
