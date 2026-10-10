import json
import sqlite3
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from agent.evidence import select_evidence
from agent.fallback import prepare_brief
from agent.graph import run_research
from agent.llm import OpenAICompatibleClient
from agent.nodes import AgentNodes, BudgetExceeded
from config import Settings
from evals.judge import judge_report
from models.schemas import SearchResult, SourceDocument
from storage.database import RunStore
from tools.webpage import _clean_html, clear_page_cache, fetch_page


def state_for(nodes, request='zircon isotope result'):
    state = {'input_text': request, 'llm_call_count': 0, 'search_call_count': 0,
             'token_usage': 0, 'estimated_cost': 0, 'warnings': []}
    state.update(nodes.prepare_research(state))
    state.update(nodes.plan_research(state))
    return state


@pytest.mark.parametrize('settings', [Settings(max_total_tokens=1000),
    Settings(max_cost_usd=.001, price_per_million_tokens=100),
    Settings(max_cost_usd=1, price_per_million_tokens=0)])
def test_budget_rejection_prevents_billable_request(settings):
    nodes = AgentNodes(settings, {'mock': False})
    state = {'llm_call_count': 0, 'token_usage': 0, 'estimated_cost': 0}
    with patch.object(nodes.client, 'chat') as chat:
        with pytest.raises(BudgetExceeded):
            nodes.call_llm(state, 'system', 'input')
    chat.assert_not_called()
    assert state['llm_call_count'] == 0


def test_unknown_failed_usage_reserves_budget_before_retry():
    nodes = AgentNodes(Settings(max_total_tokens=2500), {'mock': False})
    state = {'llm_call_count': 0, 'token_usage': 0, 'estimated_cost': 0, 'warnings': []}
    with patch.object(nodes.client, 'chat', side_effect=httpx.ConnectError('temporary')) as chat:
        with pytest.raises(BudgetExceeded):
            nodes.call_llm(state, 'system', 'input')
    assert chat.call_count == 1
    assert state['cost_incomplete'] and state['unaccounted_token_budget'] > 0
    assert state['token_usage'] == 0  # reservation is not reported as billed usage


@pytest.mark.parametrize('kwargs', [{'max_total_tokens': -1}, {'max_cost_usd': -1},
    {'max_rounds': 0}, {'max_questions': 9}])
def test_invalid_budgets_fail_configuration(kwargs):
    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_optional_judge_honors_its_own_budget(monkeypatch):
    chat = lambda *a, **k: pytest.fail('Over-budget Judge must not call model')
    monkeypatch.setattr(OpenAICompatibleClient, 'chat', chat)
    result, usage = judge_report('task', 'report', Settings(llm_api_key='fixture',
        llm_model='fixture', max_total_tokens=1000))
    assert result is None and usage['calls'] == 0


@pytest.mark.parametrize('assessment_status,temporal,expected', [
    ('supported', 'unknown', 'partial'),
    ('supported', 'confirmed', 'supported'),
    ('conflicting', 'confirmed', 'conflicting')])
def test_temporal_or_conflicting_evidence_cannot_silently_complete(assessment_status, temporal, expected):
    nodes = AgentNodes(Settings(), {'mock': False})
    state = state_for(nodes, 'zircon isotope result in 2026')
    state['source_documents'] = [SourceDocument(title='zircon result',
        url='https://example.com/zircon', source_id='S1', content='zircon isotope result is 17 units',
        published_at='2026-10-01').model_dump()]
    nodes.client.api_key, nodes.client.model = 'fixture', 'fixture'
    def answer(messages, **kwargs):
        payload = json.loads(messages[1]['content'])
        return json.dumps({'questions': [{'question_id': 'q1', 'status': assessment_status,
            'evidence_ids': [payload['evidence'][0]['id']], 'explanation': 'Direct result',
            'next_queries': [], 'temporal_applicability': temporal}]}), 20
    with patch.object(nodes.client, 'chat', side_effect=answer):
        state.update(nodes.assess_evidence(state))
    assert state['assessment'][0]['status'] == expected
    state.update(report_kind='model_answer', citation_metrics={},
        report_review={'task_compliant': True, 'complete': True, 'supported': True, 'issues': []})
    assert nodes.finalize(state)['status'] == ('completed' if expected == 'supported' else 'partial')


def test_followup_query_can_replace_full_stale_candidate_pool():
    nodes = AgentNodes(Settings(max_candidates=2), {'mock': True, 'search_count': 2})
    state = state_for(nodes)
    state.update(round=1, assessment=[{'question_id': 'q1', 'status': 'partial',
        'next_queries': ['zircon measured result']}],
        search_results=[SearchResult(title='old', url=f'https://example.com/old{i}',
        question_ids=['q1']).model_dump() for i in range(2)],
        attempted_urls=['https://example.com/old0', 'https://example.com/old1'])
    with patch('tools.search.MockSearchProvider.search', return_value=[
        SearchResult(title='zircon measured result', url='https://example.com/new')]):
        result = nodes.search_sources(state)
    assert any(r['url'].endswith('/new') for r in result['search_results'])
    assert len(result['search_results']) <= 2


def test_generic_summary_selects_supplied_material_without_keyword_overlap(tmp_path):
    run = run_research('仅根据提供的材料总结，不要联网。', supplied_text='zircon isotope result is 17 units',
        settings=Settings(), mock=False, store=RunStore(tmp_path / 'material.db'))
    assert run['search_call_count'] == 0 and run['evidence'][0]['kind'] == 'user'
    assert run['status'] == 'partial'


def test_selection_discloses_omitted_relevant_material():
    doc = SourceDocument(title='material', url='user://material/example', source_id='S1',
        content='\n'.join(f'zircon {i} result ' + 'details ' * 80 for i in range(15))).model_dump()
    evidence, metadata = select_evidence([doc], [{'id': 'q1', 'text': 'summarize', 'queries': ['summarize']}], 700)
    assert evidence and metadata['omitted_relevant_chunks'] > 0
    assert metadata['estimated_tokens'] <= 700


def test_html_cleaner_keeps_separate_articles_tables_and_appendix():
    content = _clean_html('<body><article><p>introduction</p></article><article><h2>zircon</h2>'
        '<table><tr><td>isotope</td><td>17</td></tr></table></article><aside><p>appendix result</p></aside></body>')
    assert all(x in content for x in ['introduction', 'zircon', 'isotope | 17', 'appendix result'])


def test_exact_download_boundary_does_not_mean_truncated(monkeypatch):
    clear_page_cache()
    client = httpx.Client
    monkeypatch.setattr('tools.webpage._check_public_host', lambda url: None)
    transport = httpx.MockTransport(lambda req: httpx.Response(200,
        headers={'content-type': 'text/plain'}, content=b'a' * 1024))
    monkeypatch.setattr('tools.webpage.httpx.Client', lambda **kwargs: client(transport=transport, **kwargs))
    doc = fetch_page(SearchResult(title='exact', url='https://example.com/exact'), max_bytes=1024)
    assert doc.fetch_status == 'success' and not doc.download_truncated


def test_cache_expires_without_rewriting_acquisition_time(monkeypatch):
    clear_page_cache()
    clock = [100.0]
    calls = []
    monkeypatch.setattr('tools.webpage.time.monotonic', lambda: clock[0])
    def fetch(*args):
        calls.append(1)
        return {'content': f'zircon {len(calls)}', 'published_at': None,
                'retrieved_at': str(clock[0]), 'content_type': 'text/html', 'download_truncated': False}
    monkeypatch.setattr('tools.webpage._fetch_content', fetch)
    item = SearchResult(title='cache', url='https://example.com/ttl')
    first = fetch_page(item, cache_ttl=10)
    clock[0] = 105
    cached = fetch_page(item, cache_ttl=10)
    clock[0] = 111
    expired = fetch_page(item, cache_ttl=10)
    assert cached.cache_hit and cached.retrieved_at == first.retrieved_at
    assert not expired.cache_hit and expired.content != first.content and len(calls) == 2


def test_relative_time_is_recorded_and_explicit_search_exclusion_retained():
    brief = prepare_brief('截至今天的研究结果，不要搜索，仅根据提供材料。')
    assert brief.as_of and brief.time_scope and brief.freshness_required
    assert not brief.allow_web_research


def test_legacy_sqlite_records_remain_readable(tmp_path):
    path = tmp_path / 'legacy.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE runs (run_id TEXT, created_at TEXT, input_text TEXT, total_duration_ms INTEGER, '
            'token_usage INTEGER, estimated_cost REAL, report TEXT, plan_json TEXT, search_json TEXT, '
            'documents_json TEXT, citation_json TEXT, node_status_json TEXT, errors_json TEXT, metrics_json TEXT)')
        db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ('old', '2026-10-01T00:00:00+00:00', 'old task', 1, 0, 0, 'old report', '{}', '[]', '[]', '{}', '{}', '[]', '{}'))
        db.execute('CREATE TABLE trace_events (id INTEGER PRIMARY KEY, run_id TEXT, event_json TEXT)')
        db.execute('INSERT INTO trace_events VALUES (?,?,?)', (1, 'old', json.dumps({'node_name': 'legacy-node'})))
    store = RunStore(path)
    assert store.get_run('old')['report'] == 'old report'
    assert store.get_run('old')['traces'][0]['node_name'] == 'legacy-node'
    assert store.list_runs()[0]['status'] == 'legacy'
    run = run_research('LangGraph', settings=Settings(), store=store)
    assert len(store.list_runs()) == 2 and store.get_run(run['run_id'])['status'] == 'demo'
