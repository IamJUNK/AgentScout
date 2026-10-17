from config import Settings
from models.tasks import TaskRequest
from storage.repository import Conflict

class TaskService:
    def __init__(self, repository, publisher, settings: Settings):
        self.repo, self.publisher, self.settings = repository, publisher, settings

    def submit(self, request: TaskRequest, key: str):
        if not key.strip() or len(key)>128: raise Conflict('幂等键必须为 1–128 字符')
        if not request.mock and not (self.settings.llm_api_key and self.settings.llm_model):
            raise Conflict('真实研究需要配置模型接口')
        from agent.fallback import prepare_brief
        if not request.mock and prepare_brief(request.input_text).allow_web_research and not self.settings.tavily_api_key:
            raise Conflict('联网研究需要配置搜索接口')
        if request.max_tokens>self.settings.max_total_tokens or request.timeout_seconds>self.settings.research_timeout_seconds:
            raise Conflict('请求超过服务端单次研究预算')
        tid=self.repo.create_task(request,key,self.settings.max_task_tokens,self.settings.max_task_search_calls,self.settings.max_search_calls)
        self.dispatch(self.repo.get_task(tid)['current_attempt']['id'])
        return self.repo.get_task(tid)

    def dispatch(self, aid):
        s=self.settings
        if not self.repo.reserve_dispatch(aid,s.dispatch_max_attempts,s.dispatch_interval_seconds): return
        try:
            self.publisher(aid)
        except Exception:
            return  # durable pending state is retried by the reconciler
        self.repo.mark_queued(aid)

    def reconcile(self):
        stale=self.repo.stale(self.settings.heartbeat_timeout_seconds)
        ids=self.repo.due_dispatch(self.settings.dispatch_max_attempts)
        for aid in ids: self.dispatch(aid)
        return {'stale_attempts':stale,'dispatch_candidates':len(ids)}

    def retry(self, task_id):
        aid=self.repo.retry(task_id,self.settings.max_task_attempts,self.settings.max_search_calls)
        self.dispatch(aid)
        return self.repo.get_task(task_id)

    def cancel(self, task_id): return self.repo.cancel(task_id)

    # Shared read surface for HTTP routes and UI; storage stays behind this boundary.
    def list_tasks(self, *args, **kwargs): return self.repo.list_tasks(*args, **kwargs)
    def get_task(self, task_id): return self.repo.get_task(task_id)
    def attempts(self, task_id): return self.repo.attempts(task_id)
    def get_attempt(self, aid): return self.repo.get_attempt(aid)
    def events(self, *args, **kwargs): return self.repo.events(*args, **kwargs)
    def report(self, aid): return self.repo.report(aid)
    def evidence(self, *args, **kwargs): return self.repo.evidence(*args, **kwargs)
    def source(self, aid, sid): return self.repo.source(aid, sid)
