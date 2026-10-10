import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import httpx
import pytest
from agent.graph import NODE_NAMES, run_research
from agent.nodes import AgentNodes
from agent.llm import OpenAICompatibleClient
from config import Settings
from models.schemas import SearchResult
from storage.database import RunStore
from evals.judge import attach_judge


def cloud_settings(**kwargs):
    return Settings(llm_api_key="fixture", llm_model="fixture-model", tavily_api_key="fixture", **kwargs)


def model_answer(messages, **kwargs):
    system=messages[0]["content"]
    payload=json.loads(messages[1]["content"])
    if "questions" not in payload and "budget" in payload:
        return json.dumps({"questions":[{"text":"zircon isotope result", "queries":["zircon isotope result"]}]}), 100
    if "检查候选证据" in system:
        return json.dumps({"questions":[{"question_id":q["id"],"status":"supported","evidence_ids":[e["id"] for e in payload["evidence"] if q["id"] in e["question_ids"]],"explanation":"Direct result is present.","next_queries":[]} for q in payload["questions"]]}),100
    if "对照 original_request" in system:
        return json.dumps({"task_compliant":True,"complete":True,"supported":True,"issues":[]}),100
    e=payload["evidence"][0]
    return f"The zircon isotope result is 17 units. [证据 {e['id']}]({e['url']})",100


def network_body(*args):
    return {"content":"The zircon isotope result is 17 units.","published_at":"2026-10-01","retrieved_at":"2026-10-10T00:00:00+00:00","content_type":"text/html","download_truncated":False}


def test_mock_is_a_demo_not_completed_research(tmp_path):
    store=RunStore(tmp_path/'mock.db')
    run=run_research('LangGraph and CrewAI',settings=Settings(),store=store)
    assert run['status']=='demo' and not run['success']
    assert run['execution_status']=='finished' and run['evidence']
    assert 'classify_input' not in run['node_status']
    assert set(NODE_NAMES)==set(run['node_status'])
    assert store.get_run(run['run_id'])['report']==run['report']
    assert store.list_runs()[0]['status']=='demo'
    assert len(store.get_run(run['run_id'])['traces'])==len(run['traces'])


def test_empty_search_is_insufficient_not_success(tmp_path,monkeypatch):
    monkeypatch.setattr('tools.search.MockSearchProvider.search',lambda *a,**k:[])
    store=RunStore(tmp_path/'empty.db')
    run=run_research('test',settings=Settings(),store=store)
    assert run['status']=='insufficient_evidence' and not run['success']
    assert not run['evidence'] and store.get_run(run['run_id'])['status']==run['status']


def test_real_mode_end_to_end_quality_gates(tmp_path,monkeypatch):
    monkeypatch.setattr(OpenAICompatibleClient,'chat',lambda self,messages,**kw:model_answer(messages,**kw))
    monkeypatch.setattr('tools.search.TavilySearchProvider.search',lambda *a,**k:[SearchResult(title='zircon result',url='https://example.com/zircon')])
    monkeypatch.setattr('tools.webpage._fetch_content',network_body)
    run=run_research('zircon isotope result',mock=False,settings=cloud_settings(price_per_million_tokens=1),store=RunStore(tmp_path/'real.db'),force_refresh=True)
    assert run['success'], run
    assert run['status']=='completed' and run['round']==1
    assert run['llm_call_count']==4 and run['token_usage']==400
    assert run['estimated_cost']==pytest.approx(.0004)
    assert not run['citation_metrics']['uncited_claims']


def test_all_fetches_failed_never_complete(tmp_path,monkeypatch):
    monkeypatch.setattr('tools.search.TavilySearchProvider.search',lambda *a,**k:[SearchResult(title='zircon',url='https://example.com/failed')])
    monkeypatch.setattr('tools.webpage._fetch_content',lambda *a:(_ for _ in ()).throw(ValueError('unavailable')))
    run=run_research('zircon',mock=False,settings=Settings(),store=RunStore(tmp_path/'failed.db'),force_refresh=True)
    assert run['status']=='insufficient_evidence' and not run['success']
    assert not run['evidence'] and run['source_documents'][0]['fetch_status']=='failed'


def test_queries_are_interleaved_before_fetch_budget():
    nodes=AgentNodes(Settings(max_fetch_pages=4,max_rounds=1),{'mock':True,'search_count':5})
    state={'input_text':'topics'}
    state.update(nodes.prepare_research(state))
    state.update(plan={'questions':[{'id':f'q{i}','text':f'topic{i}','queries':[f'topic{i}']} for i in range(4)]},search_call_count=0,warnings=[])
    def search(query,**kwargs):
        return [SearchResult(title=query,url=f'https://example.com/{query}/{i}',snippet=query) for i in range(5)]
    with patch('tools.search.MockSearchProvider.search',side_effect=search):
        state.update(nodes.search_sources(state))
        state.update(nodes.fetch_pages(state))
    assert {d['question_ids'][0] for d in state['source_documents']}=={'q0','q1','q2','q3'}


def test_single_question_cloud_plan_is_accepted():
    nodes=AgentNodes(cloud_settings(),{'mock':False})
    state={'input_text':'zircon isotope result','warnings':[],'llm_call_count':0,'token_usage':0,'estimated_cost':0}
    state.update(nodes.prepare_research(state))
    with patch.object(nodes.client,'chat',side_effect=model_answer):
        plan=nodes.plan_research(state)['plan']
    assert len(plan['questions'])==1 and not state['warnings']


def test_no_web_research_uses_only_supplied_material(tmp_path,monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError('Search must not be called')
    monkeypatch.setattr('tools.search.TavilySearchProvider.search',forbidden)
    run=run_research('Only use the supplied material to explain zircon isotope results',supplied_text='zircon isotope result is 17 units',mock=False,settings=Settings(),store=RunStore(tmp_path/'material.db'))
    assert run['search_call_count']==0
    assert run['status']=='partial' and run['evidence'][0]['kind']=='user'
    assert run['evidence'][0]['url'].startswith('user://')


def test_each_run_has_independent_id_and_judge_does_not_mutate(tmp_path,monkeypatch):
    store=RunStore(tmp_path/'judge.db')
    original=run_research('LangGraph',settings=Settings(),store=store)
    snapshot=deepcopy(original)
    answer=json.dumps({'accuracy':.8,'completeness':.8,'citation_quality':.8,'overall':.8,'reasoning':'fixture'})
    monkeypatch.setattr(OpenAICompatibleClient,'chat',lambda *a,**k:(answer,100))
    first=attach_judge(original,'LangGraph',cloud_settings(),store=store)
    second=attach_judge(original,'LangGraph',cloud_settings(),store=store)
    assert original==snapshot
    assert first['review_id']!=second['review_id'] and len(store.list_reviews(original['run_id']))==2
    assert store.get_run(original['run_id'])['token_usage']==0
    another=run_research('LangGraph',settings=Settings(),store=store)
    assert another['run_id']!=original['run_id']


def test_strategies_use_identical_evidence_budget(tmp_path):
    store=RunStore(tmp_path/'strategies.db')
    first=run_research('LangGraph CrewAI',prompt_variant='baseline',settings=Settings(),store=store)
    second=run_research('LangGraph CrewAI',prompt_variant='structured',settings=Settings(),store=store)
    assert [e['id'] for e in first['evidence']]==[e['id'] for e in second['evidence']]


def test_gap_triggers_bounded_supplementary_search(tmp_path,monkeypatch):
    assess_calls=[]; queries=[]
    def answer(messages,**kwargs):
        payload=json.loads(messages[1]['content'])
        if '检查候选证据' in messages[0]['content']:
            assess_calls.append(1)
            return json.dumps({'questions':[{'question_id':'q1','status':'partial','evidence_ids':[e['id'] for e in payload['evidence']], 'explanation':'Needs independent confirmation','next_queries':[f'zircon followup {len(assess_calls)}']}]}),10
        return model_answer(messages,**kwargs)
    def search(self,query,**kwargs):
        queries.append(query)
        return [SearchResult(title='zircon',url=f'https://example.com/{len(queries)}')]
    monkeypatch.setattr(OpenAICompatibleClient,'chat',lambda self,messages,**kw:answer(messages,**kw))
    monkeypatch.setattr('tools.search.TavilySearchProvider.search',search)
    monkeypatch.setattr('tools.webpage._fetch_content',network_body)
    run=run_research('zircon isotope result',mock=False,settings=cloud_settings(max_rounds=2),store=RunStore(tmp_path/'loop.db'),force_refresh=True)
    assert len(queries)==2 and len(assess_calls)==2
    assert run['status']=='partial' and run['stop_reason']=='budget_exhausted'
    assert run['round']==2
