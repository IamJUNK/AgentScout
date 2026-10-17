"""Explicit ephemeral core-test store; never used by the production service."""
from copy import deepcopy

class MemoryRunStore:
    def __init__(self):
        self.runs = {}
        self.reviews = []

    def save_run(self, state):
        self.runs[state['run_id']] = deepcopy(state)

    def get_run(self, run_id):
        return deepcopy(self.runs.get(run_id))

    def list_runs(self, limit=50):
        return sorted(deepcopy(list(self.runs.values())), key=lambda s: s['created_at'], reverse=True)[:limit]

    def save_review(self, review):
        self.reviews.append(deepcopy(review))

    def list_reviews(self, run_id):
        return [deepcopy(r) for r in self.reviews if r['run_id'] == run_id]
