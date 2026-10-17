"""Explicit failure injection for agentscout-validation only; Mock tasks only."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4
import httpx

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8081'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not args.apply:parser.error('This stops validation services; pass --apply explicitly')
    cmd=['docker','compose','--env-file',str(ROOT/'data/upgrade-local/validation.env'),'-p','agentscout-validation','-f','compose.yaml','-f','compose.test.yaml']
    def compose(*args):
        result=subprocess.run(cmd+list(args),cwd=ROOT,capture_output=True,text=True,timeout=90)
        if result.returncode:raise RuntimeError(result.stderr[-1500:])
    client=httpx.Client(base_url=BASE,timeout=25)
    def request(method,url,**kwargs):
        response=client.request(method,url,**kwargs)
        response.raise_for_status()
        return response.json()
    def submit(label):
        return request('POST','/api/v1/tasks',headers={'Idempotency-Key':str(uuid4())},json={'input_text':'LangGraph '+label,'mock':True})
    def wait(fn,seconds=100):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            try:
                value=fn()
                if value:return value
            except (httpx.HTTPError,ConnectionError):pass
            time.sleep(1)
        raise AssertionError('Timed out waiting for service state')
    def finished(tid):
        result=request('GET','/api/v1/tasks/'+tid)
        return result if result['current_attempt']['execution_status']=='succeeded' else None
    result={}
    try:
        config=subprocess.run(cmd+['config','--format','json'],cwd=ROOT,capture_output=True,text=True,check=True)
        settings=json.loads(config.stdout)
        for name in ('web','worker','reconciler'):
            env=settings['services'][name]['environment']
            assert not env.get('LLM_API_KEY') and not env.get('TAVILY_API_KEY')
            assert '/agentscout_test' in env['DATABASE_URL']
        compose('stop','worker','reconciler')
        queued=submit('queued cancellation')
        assert queued['current_attempt']['execution_status']=='queued'
        cancelled=request('POST','/api/v1/tasks/'+queued['id']+'/cancel')
        assert cancelled['execution_status']=='cancelled'
        retry=request('POST','/api/v1/tasks/'+queued['id']+'/retry')
        assert retry['current_attempt']['number']==2
        compose('start','worker','reconciler')
        success=wait(lambda:finished(queued['id']))
        attempts=request('GET','/api/v1/tasks/'+queued['id']+'/attempts')
        assert attempts[1]['execution_status']=='cancelled'
        result['queued_cancel_then_retry']=True
        print('Queued cancellation and retry passed.',flush=True)
        compose('stop','redis')
        start=time.monotonic()
        outage=submit('broker outage')
        assert outage['current_attempt']['execution_status']=='pending_dispatch'
        result['outage_submit_seconds']=round(time.monotonic()-start,3)
        compose('start','redis')
        print('Redis outage persisted pending_dispatch; waiting for normal compensator interval.',flush=True)
        recovered=wait(lambda:finished(outage['id']),150)
        result['redis_outage_recovered']=True
        result['recovered_dispatch_count']=recovered['current_attempt']['dispatch_count']
        aid=recovered['current_attempt']['id']
        before=request('GET','/api/v1/attempts/'+aid+'/report')
        assert before['quality_status']=='demo'
        compose('restart','web','worker','reconciler','mysql','redis')
        wait(lambda:client.get('/health/ready').status_code==200)
        after=request('GET','/api/v1/attempts/'+aid+'/report')
        assert before==after
        result['container_restart_preserved_report']=True
        result['task_id']=outage['id']
        result['paid_calls']=0
        (ROOT/'data/upgrade-local/service-faults.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result),flush=True)
    finally:
        compose('start','mysql','redis','web','worker','reconciler')
        client.close()

if __name__=='__main__':main()
