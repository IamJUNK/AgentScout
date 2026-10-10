import json
from copy import deepcopy
from unittest.mock import patch
import httpx
import pytest
from agent.llm import OpenAICompatibleClient, IncompleteResponse, extract_json
from agent.nodes import AgentNodes, BudgetExceeded
from agent.graph import run_research
from config import Settings,safe_error
from evals.judge import judge_report,attach_judge
from observability.tracing import run_traced_node
from storage.database import RunStore


def test_secret_redaction_and_config_serialization():
    settings=Settings(llm_api_key='secret-fixture',tavily_api_key='search-fixture')
    assert 'secret-fixture' not in settings.model_dump_json()
    assert 'search-fixture' not in repr(settings)
    assert safe_error(ValueError('secret-fixture search-fixture'),settings)=='[REDACTED] [REDACTED]'


def test_extract_json_fence():
    assert extract_json(chr(96)*3+'json\n{"a":1}\n'+chr(96)*3)=={'a':1}
    with pytest.raises(ValueError): extract_json('invalid')


def test_missing_judge_is_separate_skipped_review(tmp_path):
    store=RunStore(tmp_path/'skip.db')
    run=run_research('LangGraph',settings=Settings(),store=store)
    review=attach_judge(run,'LangGraph',Settings(),store=store)
    assert review['status']=='skipped' and review['usage']['calls']==0
    assert 'judge' not in run and len(store.list_reviews(run['run_id']))==1


def test_empty_judge_object_rejected_and_tokens_counted(monkeypatch):
    monkeypatch.setattr(OpenAICompatibleClient,'chat',lambda *a,**k:('{}',100))
    result,usage=judge_report('task','report',Settings(llm_api_key='fixture',llm_model='fixture',price_per_million_tokens=2))
    assert result is None and usage['tokens']==100 and usage['cost']==.0002


def test_model_truncation_and_empty_response_rejected(monkeypatch):
    for content,reason in [('unfinished','length'),('', 'stop'),('blocked','content_filter')]:
        response=httpx.Response(200,request=httpx.Request('POST','https://example.com'),json={'choices':[{'message':{'content':content},'finish_reason':reason}],'usage':{'total_tokens':5}})
        monkeypatch.setattr(httpx,'post',lambda *a,**k:response)
        with pytest.raises(IncompleteResponse) as error:
            OpenAICompatibleClient('https://example.com','fixture','fixture').chat([])
        assert error.value.tokens==5


def test_error_trace_retains_attempt_counters():
    state={'run_id':'x','search_call_count':0,'llm_call_count':0,'token_usage':0,'estimated_cost':0}
    def broken(s):
        s['search_call_count']+=4
        s['llm_call_count']+=1
        s['token_usage']+=7
        raise ValueError('failure')
    with pytest.raises(ValueError): run_traced_node(state,'search',broken)
    last=state['traces'][-1]
    assert last['search_calls']==4 and last['llm_calls']==1 and last['token_usage']==7


def test_empty_repair_preserves_report_and_original_constraints():
    nodes=AgentNodes(Settings(llm_api_key='fixture',llm_model='fixture'),{'mock':False,'prompt_variant':'baseline'})
    original='Claim [证据 Ebad](https://bad.example)'
    state={'input_text':'No career advice; research manufacturing only.', 'brief':{},'plan':{},'evidence':[{'id':'Egood','url':'https://example.com','text':'manufacturing evidence'}],'assessment':[], 'report':original,'report_kind':'model_answer','warnings':[], 'llm_call_count':0,'token_usage':0,'estimated_cost':0}
    captured=[]
    def chat(messages,**kwargs):
        captured.append(messages)
        if '对照 original_request' in messages[0]['content']:
            return json.dumps({'task_compliant':False,'complete':False,'supported':False,'issues':['bad citation']}),10
        return '',10
    with patch.object(nodes.client,'chat',side_effect=chat):
        result=nodes.validate_citations(state)
    assert state['report']==original and state['citation_repair_count']==1
    assert result['citation_warning']
    payload=json.loads(captured[1][1]['content'])
    assert payload['original_request']==state['input_text'] and payload['prompt_variant']=='baseline'


def test_context_budget_does_not_silently_trim_request():
    nodes=AgentNodes(Settings(llm_api_key='fixture',llm_model='fixture',context_token_budget=2000),{'mock':False})
    state={'llm_call_count':0,'token_usage':0,'estimated_cost':0}
    with pytest.raises(BudgetExceeded): nodes.call_llm(state,'system','中文'*10000)
    assert state['llm_call_count']==0


def test_transient_llm_error_retries_once_and_counts(monkeypatch):
    nodes=AgentNodes(Settings(llm_api_key='fixture',llm_model='fixture'),{'mock':False})
    state={'llm_call_count':0,'token_usage':0,'estimated_cost':0,'warnings':[]}
    with patch.object(nodes.client,'chat',side_effect=[httpx.ConnectError('temporary'),('answer',10)]):
        assert nodes.call_llm(state,'system','input')=='answer'
    assert state['llm_call_count']==2 and state['token_usage']==10


def test_deadline_stops_new_requests():
    nodes=AgentNodes(Settings(),{'mock':True})
    nodes.deadline=0
    state={'llm_call_count':0,'token_usage':0,'estimated_cost':0}
    with pytest.raises(BudgetExceeded): nodes.call_llm(state,'system','input')
    assert state['budget_exhausted'] and state['llm_call_count']==0
