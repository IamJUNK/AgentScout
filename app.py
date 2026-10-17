"""Web entrypoint: research executes in the Celery worker."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from config import load_settings
from storage.repository import Repository, Conflict, NotFound
from services.tasks import TaskService
from api.routes import router

def create_app(service=None, *, with_ui=True):
    owned = service is None
    if owned:
        from workers.celery_app import publish
        settings = load_settings()
        service = TaskService(Repository(settings.database_url), publish, settings)
    @asynccontextmanager
    async def lifespan(app):
        yield
        if owned: service.repo.engine.dispose()
    app = FastAPI(title='AgentScout', version='0.3.0', lifespan=lifespan)
    app.state.service = service
    @app.exception_handler(Conflict)
    async def conflict(request: Request, exc: Conflict):
        return JSONResponse(status_code=409, content={'detail': str(exc)})
    @app.exception_handler(NotFound)
    async def missing(request: Request, exc: NotFound):
        return JSONResponse(status_code=404, content={'detail': str(exc)})
    @app.exception_handler(Exception)
    async def unavailable(request: Request, exc: Exception):
        return JSONResponse(status_code=503, content={'detail': 'Service temporarily unavailable'})
    @app.get('/health/live')
    def live(): return {'status': 'alive'}
    @app.get('/health/ready')
    def ready():
        try:
            service.repo.healthy()
            from redis import Redis
            with Redis.from_url(service.settings.redis_url, socket_connect_timeout=2, socket_timeout=2) as broker: broker.ping()
            return {'status': 'ready'}
        except Exception:
            return JSONResponse(status_code=503, content={'status': 'dependencies_unavailable'})
    app.include_router(router(service))
    if with_ui:
        from ui.pages import install
        install(app, service)
    return app

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(create_app(), host='127.0.0.1', port=8080)
