"""Run ONLY against a disposable database named agentscout_test."""
import os
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url
from storage.repository import Repository, Conflict, ExecutionStopped
from storage.orm import Base, Attempt, now
from models.tasks import TaskRequest

pytestmark = pytest.mark.integration

@pytest.fixture(scope='module')
def repo():
    url = os.getenv('TEST_DATABASE_URL')
    if not url: pytest.skip('TEST_DATABASE_URL not set; MySQL integration not run')
    if make_url(url).database != 'agentscout_test':
        pytest.fail('Integration tests require an isolated agentscout_test database')
    repository = Repository(url)
    from alembic.config import Config
    from alembic import command
    prior=os.environ.get('DATABASE_URL')
    os.environ['DATABASE_URL']=url
    try:
        command.upgrade(Config('alembic.ini'),'head')
        command.check(Config('alembic.ini'))
    finally:
        if prior is None:os.environ.pop('DATABASE_URL',None)
        else:os.environ['DATABASE_URL']=prior
    yield repository
    repository.engine.dispose()

def submit(repo):
    tid=repo.create_task(TaskRequest(input_text='LangGraph'),str(uuid4()),90000)
    return tid,repo.get_task(tid)['current_attempt']['id']

def test_concurrent_idempotent_create(repo):
    key=str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as executor:
        ids=list(executor.map(lambda _:repo.create_task(TaskRequest(input_text='same'),key,90000),range(4)))
    assert len(set(ids)) == 1
    with pytest.raises(Conflict): repo.create_task(TaskRequest(input_text='different'),key,90000)

def test_duplicate_claim_and_late_write_are_rejected(repo):
    tid,aid=submit(repo)
    with ThreadPoolExecutor(max_workers=4) as executor:
        claims=list(executor.map(lambda _:repo.claim(aid),range(4)))
    winners=[c for c in claims if c]
    assert len(winners)==1
    token=winners[0][0]
    repo.fail(aid,token,'test_failure')
    with pytest.raises(ExecutionStopped): repo.save_snapshot(aid,token,{},True)
    new=repo.retry(tid,3)
    assert new != aid and len(repo.attempts(tid))==2

def test_cancel_races_are_terminal(repo):
    tid,aid=submit(repo)
    repo.cancel(tid)
    assert repo.claim(aid) is None
    assert repo.get_attempt(aid)['execution_status']=='cancelled'

def test_final_report_and_quality_are_atomic(repo):
    tid,aid=submit(repo)
    token,_,_=repo.claim(aid)
    repo.save_snapshot(aid,token,{'execution_status':'finished','status':'partial','report':'insufficient evidence'},final=True)
    assert repo.get_attempt(aid)['execution_status']=='succeeded'
    assert repo.report(aid)['quality_status']=='partial'
    assert repo.claim(aid) is None

def test_stale_worker_fences_and_preserves_unknown_cost(repo):
    _,aid=submit(repo)
    token,_,limit=repo.claim(aid)
    with repo.sessions.begin() as session:
        attempt=session.get(Attempt,aid)
        attempt.heartbeat_at=now()-timedelta(seconds=500)
    assert repo.stale(90)>=1
    assert repo.get_attempt(aid)['reserved_tokens']==limit
    assert not repo.heartbeat(aid,token)

def test_report_failure_rolls_back_execution_terminal(repo):
    from sqlalchemy.exc import IntegrityError
    _,aid=submit(repo)
    token,_,_=repo.claim(aid)
    state={'execution_status':'finished','status':'completed','report':'answer','evidence':[{'id':'duplicate'},{'id':'duplicate'}]}
    with pytest.raises(IntegrityError):repo.save_snapshot(aid,token,state,final=True)
    assert repo.get_attempt(aid)['execution_status']=='running'
    from storage.repository import NotFound
    with pytest.raises(NotFound):repo.report(aid)
    repo.fail(aid,token,'expected_rollback')

def test_running_cancel_cannot_be_saved_as_success(repo):
    tid,aid=submit(repo)
    token,_,_=repo.claim(aid)
    repo.cancel(tid)
    assert not repo.heartbeat(aid,token)
    with pytest.raises(ExecutionStopped):repo.save_snapshot(aid,token,{},False)
    repo.save_snapshot(aid,token,{'execution_status':'finished','status':'completed'},True)
    assert repo.get_attempt(aid)['execution_status']=='cancelled'
    assert repo.report(aid)['quality_status']=='unassessed'

def test_retry_cannot_reset_total_search_budget(repo):
    tid=repo.create_task(TaskRequest(input_text='web research'),str(uuid4()),90000,2,2)
    aid=repo.get_task(tid)['current_attempt']['id']
    token,request,_=repo.claim(aid)
    assert request['_search_limit']==2
    repo.save_snapshot(aid,token,{'execution_status':'finished','status':'partial','search_call_count':2},True)
    with pytest.raises(Conflict,match='搜索预算'):repo.retry(tid,3)

def test_dispatch_gap_and_duplicate_reservations(repo):
    from services.tasks import TaskService
    from config import Settings
    from unittest.mock import Mock
    publisher=Mock(side_effect=ConnectionError('broker offline'))
    service=TaskService(repo,publisher,Settings())
    task=service.submit(TaskRequest(input_text='LangGraph'),str(uuid4()))
    aid=task['current_attempt']['id']
    assert repo.get_attempt(aid)['execution_status']=='pending_dispatch'
    with repo.sessions.begin() as session:session.get(Attempt,aid).dispatch_after=now()-timedelta(seconds=1)
    publisher.side_effect=None
    service.reconcile()
    assert repo.get_attempt(aid)['execution_status']=='queued'
    service.dispatch(aid)
    assert sum(call.args==(aid,) for call in publisher.call_args_list)==2
    repo.cancel(task['id'])

def test_legacy_import_is_idempotent_and_does_not_recertify(repo):
    from storage.legacy import import_records
    run_id=str(uuid4())
    rows=[{'run_id':run_id,'content_hash':'a'*64,'reviews':[],'state':{'input_text':'old','status':'completed','report':'old'}}]
    assert import_records(repo,rows)=={'imported':1,'skipped':0}
    assert import_records(repo,rows)=={'imported':0,'skipped':1}
    from storage.orm import Report
    with repo.sessions() as session:
        assert session.scalar(select(Report).where(Report.quality_status=='legacy')).review['legacy_status']=='completed'

def test_idempotency_keys_are_case_sensitive(repo):
    key=str(uuid4())
    a=repo.create_task(TaskRequest(input_text='same'),key.lower(),90000)
    b=repo.create_task(TaskRequest(input_text='same'),key.upper(),90000)
    assert a!=b
