from __future__ import annotations
import math
import re
import httpx
from rank_bm25 import BM25Plus


def tokens(text):
    text = text.casefold()
    words = re.findall(r'[a-z0-9_-]+', text)
    for sequence in re.findall(r'[\u3400-\u9fff]+', text):
        words.extend(sequence[i:i+2] for i in range(max(1, len(sequence)-1)))
    return words or ['_empty_']


def lexical_rank(query, texts):
    if not texts:
        return []
    corpus = [tokens(t) for t in texts]
    query_tokens = tokens(query)
    scores = BM25Plus(corpus).get_scores(query_tokens)
    # BM25Plus adds a constant even without overlap; explicitly exclude these.
    return sorted([(i, float(scores[i])) for i, row in enumerate(corpus) if set(row) & set(query_tokens)], key=lambda x: (-x[1], x[0]))


def cosine_rank(query, vectors):
    qnorm = math.sqrt(sum(v*v for v in query))
    if not qnorm:
        raise ValueError('Zero embedding vector')
    result = []
    for i, row in enumerate(vectors):
        if len(row) != len(query) or not all(math.isfinite(v) for v in row):
            raise ValueError('Invalid embedding dimensions or non-finite values')
        norm = math.sqrt(sum(v*v for v in row))
        result.append((i, sum(a*b for a,b in zip(query,row))/(qnorm*norm) if norm else 0))
    return sorted(result, key=lambda x: (-x[1], x[0]))


def rrf(*rankings, k=60):
    scores = {}
    for ranking in rankings:
        for rank, (index, _) in enumerate(ranking, 1):
            scores[index] = scores.get(index, 0) + 1/(k+rank)
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))


class EmbeddingClient:
    def __init__(self, settings):
        self.settings = settings
        self.calls = []

    def encode(self, texts):
        s = self.settings
        if not (s.embedding_base_url and s.embedding_model):
            raise ValueError('Embedding endpoint/model not configured; lexical degradation')
        if len(texts) > 256 or sum(len(t) for t in texts) > 250000:
            raise ValueError('Embedding input budget exceeded')
        record = {'kind': 'embedding', 'model': s.embedding_model, 'count': len(texts), 'status': 'started', 'tokens': None}
        self.calls.append(record)
        try:
            response = httpx.post(s.embedding_base_url.rstrip('/') + '/embeddings',
                headers={'Authorization': 'Bearer ' + s.embedding_api_key},
                json={'model': s.embedding_model, 'input': texts}, timeout=s.embedding_timeout_seconds)
            response.raise_for_status()
            data = response.json()
            rows = sorted(data['data'], key=lambda r: r['index'])
            if [r['index'] for r in rows] != list(range(len(texts))):
                raise ValueError('Embedding response missing/duplicated indices')
            vectors = [r['embedding'] for r in rows]
            if not vectors or not vectors[0] or any(len(v) != len(vectors[0]) or not all(isinstance(x, (int,float)) and math.isfinite(x) for x in v) for v in vectors):
                raise ValueError('Invalid embedding response')
            record.update(status='succeeded', tokens=data.get('usage', {}).get('total_tokens'))
            return vectors
        except Exception:
            record['status'] = 'failed'
            raise
