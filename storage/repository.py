from __future__ import annotations
from copy import deepcopy
from datetime import timedelta, datetime
import hashlib
import json
from uuid import uuid4
from sqlalchemy import create_engine, select, update, func, text, and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from storage.orm import ResearchTask, Attempt, Source, Evidence, Report, Event, ExternalCall, now
from models.tasks import TERMINAL

class NotFound(LookupError): pass
class Conflict(ValueError): pass
class ExecutionStopped(RuntimeError): pass

def uid(): return str(uuid4())
def stamp(value): return value.isoformat() + 'Z' if value else None

def attempt_dict(a):
    return {k: getattr(a,k) for k in ('id','task_id','number','execution_status','quality_status','cancel_requested','dispatch_count','error_code','token_usage','reserved_tokens','token_limit','search_usage','search_limit')} | {
        k: stamp(getattr(a,k)) for k in ('created_at','updated_at','started_at','ended_at','heartbeat_at')}

class Repository:
    def __init__(self, url):
        if not url.startswith('mysql+pymysql://'):
            raise ValueError('Service requires DATABASE_URL=mysql+pymysql://...; SQLite is legacy-only')
        self.engine = create_engine(url, pool_pre_ping=True, pool_recycle=1800, connect_args={'connect_timeout':5})
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def healthy(self):
        with self.sessions() as s:
            s.execute(text('SELECT 1'))
            s.execute(select(ResearchTask.id).limit(1))

    def create_task(self, request, key, max_task_tokens, max_task_search_calls=24, max_search_calls=12):
        payload = request.model_dump()
        digest = hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with self.sessions.begin() as s:
            prior = s.scalar(select(ResearchTask).where(ResearchTask.idempotency_key == key))
            if prior:
                if prior.request_hash != digest: raise Conflict('幂等键已用于不同请求')
                return prior.id
            tid, aid = uid(), uid()
            task = ResearchTask(id=tid,idempotency_key=key,request_hash=digest,request=payload,current_attempt_id=aid,max_tokens=max_task_tokens,max_search_calls=max_task_search_calls)
            s.add(task)
            try:
                s.flush()
                s.add(Attempt(id=aid,task_id=tid,number=1,token_limit=min(request.max_tokens,max_task_tokens),search_limit=min(max_search_calls,max_task_search_calls)))
                s.flush()
            except IntegrityError:
                # Resolve the concurrent unique-key winner in a fresh transaction.
                s.rollback()
                with self.sessions() as lookup:
                    prior = lookup.scalar(select(ResearchTask).where(ResearchTask.idempotency_key == key))
                    if not prior or prior.request_hash != digest: raise Conflict('幂等提交冲突')
                    return prior.id
            return tid

    def get_task(self, task_id):
        with self.sessions() as s:
            t = s.get(ResearchTask,task_id)
            if not t: raise NotFound('任务不存在')
            a = s.get(Attempt,t.current_attempt_id)
            return {'id':t.id,'request':t.request,'created_at':stamp(t.created_at),'current_attempt':attempt_dict(a),'max_tokens':t.max_tokens,'max_search_calls':t.max_search_calls}

    def list_tasks(self, limit=20, before=None, status=None, since=None, until=None):
        with self.sessions() as s:
            q = select(ResearchTask,Attempt).join(Attempt,ResearchTask.current_attempt_id==Attempt.id)
            if before:
                anchor = s.get(ResearchTask,before)
                if not anchor: raise NotFound('分页游标不存在')
                q = q.where(or_(ResearchTask.created_at<anchor.created_at,and_(ResearchTask.created_at==anchor.created_at,ResearchTask.id<anchor.id)))
            if status: q=q.where(Attempt.execution_status==status)
            if since: q=q.where(ResearchTask.created_at>=datetime.combine(since,datetime.min.time()))
            if until: q=q.where(ResearchTask.created_at<datetime.combine(until+timedelta(days=1),datetime.min.time()))
            rows = s.execute(q.order_by(ResearchTask.created_at.desc(),ResearchTask.id.desc()).limit(limit+1)).all()
            return {'items':[{'id':t.id,'input_text':t.request['input_text'],'created_at':stamp(t.created_at),'current_attempt':attempt_dict(a)} for t,a in rows[:limit]],'next_cursor':rows[limit-1][0].id if len(rows)>limit else None}

    def attempts(self, task_id):
        self.get_task(task_id)
        with self.sessions() as s:
            return [attempt_dict(a) for a in s.scalars(select(Attempt).where(Attempt.task_id==task_id).order_by(Attempt.number.desc()))]

    def get_attempt(self, aid):
        with self.sessions() as s:
            a=s.get(Attempt,aid)
            if not a: raise NotFound('执行记录不存在')
            return attempt_dict(a)

    def retry(self, task_id, max_attempts, max_search_calls=12):
        with self.sessions.begin() as s:
            t=s.scalar(select(ResearchTask).where(ResearchTask.id==task_id).with_for_update())
            if not t: raise NotFound('任务不存在')
            old=s.get(Attempt,t.current_attempt_id)
            if old.execution_status not in TERMINAL: raise Conflict('当前尝试尚未结束')
            if old.number>=max_attempts: raise Conflict('达到尝试次数上限')
            used=s.scalar(select(func.coalesce(func.sum(Attempt.token_usage+Attempt.reserved_tokens),0)).where(Attempt.task_id==task_id))
            remaining=t.max_tokens-used
            if remaining<1000: raise Conflict('任务总 Token 预算不足')
            searches=s.scalar(select(func.coalesce(func.sum(Attempt.search_usage),0)).where(Attempt.task_id==task_id))
            search_remaining=max(0,t.max_search_calls-searches)
            from agent.fallback import prepare_brief
            if not search_remaining and prepare_brief(t.request['input_text']).allow_web_research:
                raise Conflict('任务累计搜索预算已耗尽；不能通过重试绕过')
            aid=uid()
            s.add(Attempt(id=aid,task_id=task_id,number=old.number+1,token_limit=min(t.request['max_tokens'],remaining),search_limit=min(max_search_calls,search_remaining)))
            t.current_attempt_id=aid
            return aid

    def cancel(self, task_id):
        with self.sessions.begin() as s:
            t=s.scalar(select(ResearchTask).where(ResearchTask.id==task_id).with_for_update())
            if not t: raise NotFound('任务不存在')
            a=s.scalar(select(Attempt).where(Attempt.id==t.current_attempt_id).with_for_update())
            if a.execution_status not in TERMINAL:
                a.cancel_requested=True
                if a.execution_status!='running':
                    a.execution_status='cancelled'; a.ended_at=now(); a.execution_token=None
                a.updated_at=now()
            return attempt_dict(a)

    def reserve_dispatch(self, aid, max_count, interval):
        with self.sessions.begin() as s:
            result=s.execute(update(Attempt).where(Attempt.id==aid,Attempt.execution_status.in_(['pending_dispatch','queued']),Attempt.cancel_requested==False,Attempt.dispatch_after<=now(),Attempt.dispatch_count<max_count).values(dispatch_count=Attempt.dispatch_count+1,dispatch_after=now()+timedelta(seconds=interval),updated_at=now()))
            return result.rowcount==1

    def mark_queued(self, aid):
        with self.sessions.begin() as s:
            s.execute(update(Attempt).where(Attempt.id==aid,Attempt.execution_status=='pending_dispatch').values(execution_status='queued',updated_at=now()))

    def due_dispatch(self, max_count, limit=100):
        with self.sessions.begin() as s:
            s.execute(update(Attempt).where(Attempt.execution_status.in_(['pending_dispatch','queued']),Attempt.dispatch_after<=now(),Attempt.dispatch_count>=max_count).values(execution_status='failed',error_code='dispatch_exhausted',ended_at=now(),updated_at=now()))
            return list(s.scalars(select(Attempt.id).where(Attempt.execution_status.in_(['pending_dispatch','queued']),Attempt.dispatch_after<=now(),Attempt.dispatch_count<max_count).limit(limit)))

    def claim(self, aid):
        token=uid()
        with self.sessions.begin() as s:
            r=s.execute(update(Attempt).where(Attempt.id==aid,Attempt.execution_status.in_(['pending_dispatch','queued']),Attempt.cancel_requested==False).values(execution_status='running',execution_token=token,started_at=now(),heartbeat_at=now(),updated_at=now()))
            if r.rowcount!=1: return None
            a=s.get(Attempt,aid); t=s.get(ResearchTask,a.task_id)
            request=deepcopy(t.request)
            request['_search_limit']=a.search_limit
            return token,request,a.token_limit

    def heartbeat(self, aid, token):
        with self.sessions.begin() as s:
            r=s.execute(update(Attempt).where(Attempt.id==aid,Attempt.execution_token==token,Attempt.execution_status=='running',Attempt.cancel_requested==False).values(heartbeat_at=now()))
            return r.rowcount==1

    def stale(self, timeout):
        with self.sessions.begin() as s:
            # Charge a conservative unresolved reservation; a dead process cannot report billed usage.
            rows=s.scalars(select(Attempt).where(Attempt.execution_status=='running',Attempt.heartbeat_at<now()-timedelta(seconds=timeout)).with_for_update()).all()
            for a in rows:
                a.execution_status='cancelled' if a.cancel_requested else 'failed'
                a.error_code='worker_lost'; a.execution_token=None; a.ended_at=now(); a.updated_at=now()
                a.reserved_tokens=max(a.reserved_tokens,a.token_limit-a.token_usage)
            return len(rows)

    def save_snapshot(self, aid, token, state, final=False):
        with self.sessions.begin() as s:
            a=s.scalar(select(Attempt).where(Attempt.id==aid).with_for_update())
            if not a or a.execution_token!=token or a.execution_status!='running': raise ExecutionStopped('执行权已失效')
            if a.cancel_requested and not final: raise ExecutionStopped('已请求取消')
            snapshot=deepcopy(state)
            snapshot.pop('config',None)
            a.snapshot=snapshot; a.updated_at=now()
            a.token_usage=state.get('token_usage',0)
            a.reserved_tokens=state.get('unaccounted_token_budget',0)
            a.search_usage=state.get('search_call_count',0)
            traces=state.get('traces',[])
            existing=s.scalar(select(func.count()).select_from(Event).where(Event.attempt_id==aid))
            for i,event in enumerate(traces[existing:],existing): s.add(Event(attempt_id=aid,sequence=i,payload=event))
            calls=state.get('external_calls',[])
            existing_calls = {c.sequence: c for c in s.scalars(select(ExternalCall).where(ExternalCall.attempt_id==aid))}
            for i, call in enumerate(calls):
                if i in existing_calls:
                    existing_calls[i].payload = deepcopy(call)
                else:
                    s.add(ExternalCall(attempt_id=aid,sequence=i,payload=deepcopy(call)))
            if not final: return
            a.execution_status='cancelled' if a.cancel_requested else ('succeeded' if state.get('execution_status')=='finished' else 'failed')
            a.quality_status=state.get('status','unassessed') if a.execution_status=='succeeded' else 'unassessed'
            a.error_code=None if a.execution_status=='succeeded' else ('cancelled' if a.cancel_requested else 'research_failed')
            a.ended_at=now(); a.execution_token=None
            seen=set()
            for d in state.get('source_documents',[]):
                if d['source_id'] in seen: continue
                seen.add(d['source_id'])
                s.add(Source(attempt_id=aid,source_id=d['source_id'],url=d['url'],content=d.get('content',''),metadata_json={k:v for k,v in d.items() if k!='content'}))
            for e in state.get('evidence',[]): s.add(Evidence(attempt_id=aid,evidence_id=e['id'],payload=e))
            s.add(Report(attempt_id=aid,markdown=state.get('report',''),structured=state.get('structured_report',{}),review=state.get('claim_review',{}),quality_status=a.quality_status))

    def fail(self, aid, token, code):
        with self.sessions.begin() as s:
            a=s.scalar(select(Attempt).where(Attempt.id==aid,Attempt.execution_token==token,Attempt.execution_status=='running').with_for_update())
            if a:
                a.execution_status='cancelled' if a.cancel_requested else 'failed'
                a.error_code=code; a.execution_token=None; a.ended_at=now(); a.updated_at=now()
                a.reserved_tokens=max(a.reserved_tokens,a.token_limit-a.token_usage)

    def events(self, aid, after=0, limit=100):
        self.get_attempt(aid)
        with self.sessions() as s:
            rows=s.scalars(select(Event).where(Event.attempt_id==aid,Event.id>after).order_by(Event.id).limit(limit)).all()
            return {'items':[{'id':e.id,**e.payload} for e in rows],'next_cursor':rows[-1].id if rows else after}

    def report(self, aid):
        self.get_attempt(aid)
        with self.sessions() as s:
            r=s.get(Report,aid)
            if not r: raise NotFound('报告尚未生成')
            return {'attempt_id':aid,'markdown':r.markdown,'structured':r.structured,'review':r.review,'quality_status':r.quality_status}

    def evidence(self, aid, offset=0, limit=50):
        self.get_attempt(aid)
        with self.sessions() as s:
            return [e.payload for e in s.scalars(select(Evidence).where(Evidence.attempt_id==aid).order_by(Evidence.id).offset(offset).limit(limit))]

    def source(self, aid, source_id):
        self.get_attempt(aid)
        with self.sessions() as s:
            d=s.scalar(select(Source).where(Source.attempt_id==aid,Source.source_id==source_id))
            if not d: raise NotFound('来源不存在')
            return {**d.metadata_json,'content':d.content}
