"""Read old SQLite files without running initializers or issuing writes."""
from contextlib import closing
from pathlib import Path
import hashlib
import json
import sqlite3


def read_legacy(path):
    path = Path(path).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        records = {}
        if 'run_details' in tables:
            for row in db.execute('SELECT run_id,state_json FROM run_details ORDER BY run_id'):
                state = json.loads(row['state_json'])
                if not isinstance(state,dict): raise ValueError('Legacy state must be an object')
                records[row['run_id']] = state
        if 'runs' in tables:
            for row in db.execute('SELECT * FROM runs ORDER BY run_id'):
                if row['run_id'] not in records:
                    state = dict(row)
                    mapping={'plan_json':'plan','search_json':'search_results','documents_json':'source_documents','citation_json':'citation_metrics','node_status_json':'node_status','errors_json':'errors','metrics_json':'evaluation_metrics'}
                    for key in list(state):
                        if key.endswith('_json'):
                            state[mapping.get(key,key[:-5])] = json.loads(state.pop(key) or 'null')
                    state['status']='legacy'
                    state['traces']=[]
                    if 'trace_events' in tables:
                        state['traces']=[json.loads(r[0]) for r in db.execute('SELECT event_json FROM trace_events WHERE run_id=? ORDER BY id',(row['run_id'],))]
                    records[row['run_id']] = state
        if not tables.intersection({'run_details','runs'}):
            raise ValueError('Unsupported legacy database: no run_details or runs table')
        result=[]
        for run_id,state in records.items():
            # Historical config may contain credentials. Do not export/import it.
            state.pop('config',None)
            state.pop('settings',None)
            reviews=[]
            if 'reviews' in tables:
                reviews=[json.loads(r[0]) for r in db.execute('SELECT review_json FROM reviews WHERE run_id=? ORDER BY created_at',(run_id,))]
            digest=hashlib.sha256(json.dumps(state,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            result.append({'run_id':run_id,'state':state,'reviews':reviews,'content_hash':digest})
        return result


def import_records(repo, records):
    from storage.orm import ResearchTask, Attempt, Report
    from storage.repository import uid, Conflict
    from sqlalchemy import select
    counts={'imported':0,'skipped':0}
    for record in records:
        key='legacy:'+hashlib.sha256(record['run_id'].encode()).hexdigest()
        state=record['state']
        with repo.sessions.begin() as session:
            prior=session.scalar(select(ResearchTask).where(ResearchTask.idempotency_key==key))
            if prior:
                if prior.request_hash!=record['content_hash']:
                    raise Conflict('Legacy run ID already imported with different content')
                counts['skipped']+=1
                continue
            tid,aid=uid(),uid()
            request={'input_text':state.get('input_text') or '[历史记录]', 'supplied_text':'', 'mock':True, 'max_tokens':1000}
            session.add(ResearchTask(id=tid,idempotency_key=key,request_hash=record['content_hash'],request=request,current_attempt_id=aid,max_tokens=0,max_search_calls=0))
            session.flush()
            snapshot={'legacy_state':state,'legacy_reviews':record['reviews'],'legacy_run_id':record['run_id']}
            session.add(Attempt(id=aid,task_id=tid,number=1,execution_status='succeeded',quality_status='legacy',token_limit=0,search_limit=0,snapshot=snapshot))
            session.flush()
            session.add(Report(attempt_id=aid,markdown=state.get('report',''),structured={},review={'legacy_status':state.get('status','unknown'),'notice':'历史原始状态，不使用新版质量门槛重新认证'},quality_status='legacy'))
            counts['imported']+=1
    return counts
