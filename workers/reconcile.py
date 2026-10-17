"""Single compensator process; conditional writes tolerate overlapping ticks."""
import logging
import time
from config import load_settings
from services.tasks import TaskService
from storage.repository import Repository
from workers.celery_app import publish
def main():
    s=load_settings()
    service=TaskService(Repository(s.database_url),publish,s)
    while True:
        try: logging.info('reconcile %s',service.reconcile())
        except Exception: logging.error('Reconciliation failed; retrying next interval')
        time.sleep(s.dispatch_interval_seconds)
if __name__=='__main__': main()
