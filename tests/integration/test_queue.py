"""Real Linux worker + Redis + MySQL; never uses eager execution or paid APIs."""
import os
import subprocess
import sys
import time
from uuid import uuid4
import pytest
from celery import Celery
from config import Settings
from models.tasks import TaskRequest
from services.tasks import TaskService
from tests.integration.test_mysql import repo

pytestmark=pytest.mark.integration

def wait_for(fn,seconds=30):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        value=fn()
        if value:return value
        time.sleep(.2)
    raise AssertionError('Real worker did not reach expected state before timeout')

@pytest.fixture
def worker(repo,tmp_path):
    if sys.platform=='win32':pytest.skip('Celery process integration requires Linux')
    redis_url=os.getenv('TEST_REDIS_URL')
    if not redis_url:pytest.skip('TEST_REDIS_URL not set')
    from urllib.parse import urlsplit
    parsed=urlsplit(redis_url)
    if parsed.hostname not in {'localhost','127.0.0.1','redis'} or parsed.path!='/15':
        pytest.fail('Queue tests require isolated local Redis DB 15')
    env={**os.environ,'AGENTSCOUT_NO_DOTENV':'1','DATABASE_URL':os.environ['TEST_DATABASE_URL'],'REDIS_URL':redis_url,'LLM_API_KEY':'','TAVILY_API_KEY':'','EMBEDDING_API_KEY':''}
    name='test-'+uuid4().hex
    log=(tmp_path/'worker.log').open('w')
    process=subprocess.Popen([sys.executable,'-m','celery','-A','tests.integration.worker_app:celery_app','worker','--pool=solo','--concurrency=1','--queues='+name,'--hostname='+name+'@localhost','--loglevel=WARNING','--without-gossip','--without-mingle'],env=env,stdout=log,stderr=subprocess.STDOUT)
    client=Celery(name,broker=redis_url)
    try:
        wait_for(lambda:client.control.ping(destination=[name+'@localhost'],timeout=1),30)
        yield client,name,process
    finally:
        process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        client.close();log.close()

def test_real_queue_duplicate_and_cancelled_delivery(repo,worker):
    client,queue,process=worker
    def publish(aid):client.send_task('agentscout.research',args=[aid],queue=queue)
    service=TaskService(repo,publish,Settings())
    task=service.submit(TaskRequest(input_text='LangGraph',mock=True),str(uuid4()))
    aid=task['current_attempt']['id']
    publish(aid)
    wait_for(lambda:repo.get_attempt(aid)['execution_status'] in {'succeeded','failed'})
    assert repo.get_attempt(aid)['execution_status']=='succeeded'
    assert repo.report(aid)['quality_status']=='demo'
    assert len(repo.attempts(task['id']))==1
    tid=repo.create_task(TaskRequest(input_text='cancel me'),str(uuid4()),90000)
    cancelled=repo.get_task(tid)['current_attempt']['id']
    repo.cancel(tid);publish(cancelled)
    # Broker accepted a cancelled ID; fencing itself is asserted in MySQL tests.
    assert repo.get_attempt(cancelled)['execution_status']=='cancelled'

def test_real_worker_running_cancellation(repo,worker):
    client,queue,_=worker
    service=TaskService(repo,lambda aid:client.send_task('agentscout.research',args=[aid],queue=queue),Settings())
    task=service.submit(TaskRequest(input_text='integration:hold-worker',mock=True),str(uuid4()))
    aid=task['current_attempt']['id']
    wait_for(lambda:repo.get_attempt(aid)['execution_status']=='running')
    service.cancel(task['id'])
    wait_for(lambda:repo.get_attempt(aid)['execution_status']=='cancelled')
    assert repo.get_attempt(aid)['cancel_requested']

def test_killed_real_worker_cannot_overwrite_new_attempt(repo,worker):
    import signal
    from datetime import timedelta
    from storage.orm import Attempt,now
    from storage.repository import ExecutionStopped
    client,queue,process=worker
    service=TaskService(repo,lambda aid:client.send_task('agentscout.research',args=[aid],queue=queue),Settings())
    task=service.submit(TaskRequest(input_text='integration:hold-worker',mock=True),str(uuid4()))
    aid=task['current_attempt']['id']
    wait_for(lambda:repo.get_attempt(aid)['execution_status']=='running')
    os.kill(process.pid,signal.SIGSTOP)
    try:
        with repo.sessions.begin() as session:
            a=session.get(Attempt,aid)
            old_token=a.execution_token
            a.heartbeat_at=now()-timedelta(seconds=500)
        repo.stale(90)
        assert repo.get_attempt(aid)['error_code']=='worker_lost'
        new=repo.retry(task['id'],3)
        assert new!=aid
        with pytest.raises(ExecutionStopped):repo.save_snapshot(aid,old_token,{'execution_status':'finished'},True)
        repo.cancel(task['id'])
    finally:
        process.kill();process.wait(timeout=5)
