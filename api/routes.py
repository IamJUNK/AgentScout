from fastapi import APIRouter, Header, Query, Response
from models.tasks import TaskRequest
from datetime import date
from storage.repository import Conflict

def router(service):
    r=APIRouter(prefix='/api/v1')
    @r.post('/tasks',status_code=202)
    def create(request: TaskRequest, idempotency_key: str = Header(min_length=1,max_length=128)):
        return service.submit(request,idempotency_key)
    @r.get('/tasks')
    def listing(limit: int=Query(20,ge=1,le=100),before: str|None=None,status: str|None=Query(None,pattern='^(pending_dispatch|queued|running|succeeded|failed|cancelled)$'),since:date|None=None,until:date|None=None):
        if since and until and since>until: raise Conflict('开始日期不能晚于结束日期')
        return service.list_tasks(limit,before,status,since,until)
    @r.get('/tasks/{task_id}')
    def detail(task_id: str): return service.get_task(task_id)
    @r.get('/tasks/{task_id}/attempts')
    def attempts(task_id: str): return service.attempts(task_id)
    @r.post('/tasks/{task_id}/cancel')
    def cancel(task_id: str): return service.cancel(task_id)
    @r.post('/tasks/{task_id}/retry',status_code=202)
    def retry(task_id: str): return service.retry(task_id)
    @r.get('/attempts/{aid}/events')
    def events(aid: str, after: int=Query(0,ge=0),limit: int=Query(100,ge=1,le=500)):
        return service.events(aid,after,limit)
    @r.get('/attempts/{aid}/report')
    def report(aid: str, download: bool=False):
        value=service.report(aid)
        if download:
            return Response(value['markdown'],media_type='text/markdown',headers={'Content-Disposition':f'attachment; filename="report-{aid}.md"'})
        return value
    @r.get('/attempts/{aid}/evidence')
    def evidence(aid: str,offset: int=Query(0,ge=0),limit: int=Query(50,ge=1,le=100)):
        return service.evidence(aid,offset,limit)
    @r.get('/attempts/{aid}/sources/{source_id}')
    def source(aid: str,source_id: str): return service.source(aid,source_id)
    return r
