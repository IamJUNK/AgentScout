from celery import Celery
from config import load_settings
settings=load_settings()
celery_app=Celery('agentscout',broker=settings.redis_url,include=['workers.tasks'])
celery_app.conf.update(task_serializer='json',accept_content=['json'],result_serializer='json',
    task_ignore_result=True,task_acks_late=True,task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,broker_connection_retry_on_startup=True,
    broker_transport_options={'visibility_timeout':3600,'socket_connect_timeout':3,'socket_timeout':3},
    task_publish_retry=False,task_soft_time_limit=660,task_time_limit=690,
    task_default_queue='research',timezone='UTC',enable_utc=True)
def publish(aid):
    celery_app.send_task('agentscout.research',args=[aid],task_id=aid)
