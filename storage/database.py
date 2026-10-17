"""Deprecated read-only facade for legacy SQLite consumers."""
from pathlib import Path
from copy import deepcopy
from storage.legacy import read_legacy

class RunStore:
    def __init__(self,path=None):
        self.path=Path(path or Path(__file__).resolve().parents[1]/'data'/'agent_scout.db')
        self.records=read_legacy(self.path)
    def get_run(self,run_id):
        record=next((r for r in self.records if r['run_id']==run_id),None)
        return deepcopy(record['state']) if record else None
    def list_runs(self,limit=50):
        return sorted([{'run_id':r['run_id'],**deepcopy(r['state']),'status':'legacy'} for r in self.records],key=lambda r:r.get('created_at',''),reverse=True)[:limit]
    def list_reviews(self,run_id):
        return deepcopy(next((r['reviews'] for r in self.records if r['run_id']==run_id),[]))
    def save_run(self,state):raise RuntimeError('Legacy SQLite is read-only; use the MySQL task service')
    def save_review(self,review):raise RuntimeError('Legacy SQLite is read-only; export a separate review artifact')
