"""Integration-only fault gate. Never imported by the application deployment."""
import time
from workers.celery_app import celery_app
from workers import tasks
original=tasks.run_research

def gated_research(input_text, **kwargs):
    if input_text=='integration:hold-worker':
        # The ordinary worker has already claimed its DB token and started heartbeat.
        # Control checks allow real cancellation; SIGSTOP suspends the entire process.
        for _ in range(1200):
            kwargs['control']()
            time.sleep(.1)
    return original(input_text,**kwargs)

tasks.run_research=gated_research
