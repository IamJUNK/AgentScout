from threading import Event, Thread
from agent.graph import run_research
from config import load_settings
from storage.repository import Repository, ExecutionStopped
from workers.celery_app import celery_app

class AttemptStore:
    def __init__(self, repo, aid, token, stopped):
        self.repo,self.aid,self.token,self.stopped=repo,aid,token,stopped
    def save_run(self,state):
        if self.stopped.is_set(): raise ExecutionStopped('执行已取消或心跳失效')
        self.repo.save_snapshot(self.aid,self.token,state)

def execute_attempt(aid, repository=None, settings=None):
    settings=settings or load_settings()
    repo=repository or Repository(settings.database_url)
    claimed=repo.claim(aid)
    if not claimed: return {'status':'ignored_duplicate_or_terminal'}
    token,request,limit=claimed
    stopped,done=Event(),Event()
    def heartbeat():
        while not done.wait(10):
            try:
                if not repo.heartbeat(aid,token): stopped.set(); return
            except Exception:
                stopped.set(); return
    thread=Thread(target=heartbeat,daemon=True)
    thread.start()
    def check(*_):
        if stopped.is_set() or not repo.heartbeat(aid,token): raise ExecutionStopped('执行权失效或取消')
    config=settings.model_copy(update={'max_total_tokens':min(limit,settings.max_total_tokens),
        'max_search_calls':request.get('_search_limit',settings.max_search_calls),
        'research_timeout_seconds':min(request['timeout_seconds'],settings.research_timeout_seconds),
        'retrieval_mode':request['retrieval_mode'],
        'official_source_prefixes':request.get('official_source_prefixes') or settings.official_source_prefixes})
    try:
        check()
        state=run_research(request['input_text'],supplied_text=request['supplied_text'],mock=request['mock'],
            search_count=request['search_count'],force_refresh=request['force_refresh'],settings=config,
            store=AttemptStore(repo,aid,token,stopped),on_node=check,control=check)
        repo.save_snapshot(aid,token,state,final=True)
        return {'status':repo.get_attempt(aid)['execution_status']}
    except Exception:
        repo.fail(aid,token,'worker_execution_error')
        raise
    finally:
        done.set(); thread.join(timeout=2)
        if repository is None: repo.engine.dispose()

@celery_app.task(name='agentscout.research')
def research(aid): return execute_attempt(aid)
