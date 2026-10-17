"""CPU embeddings; explicit preparation only, never downloads inside a task."""
from functools import lru_cache
from pathlib import Path
from threading import Lock
import math
import time


def token_windows(text, offsets, maximum=120, overlap=16):
    if not offsets:
        return [text or ' ']
    windows = []
    start = 0
    while start < len(offsets):
        end = min(start + maximum, len(offsets))
        windows.append(text[offsets[start][0]:offsets[end-1][1]])
        if end == len(offsets): break
        start = end - overlap
    return windows


@lru_cache(maxsize=2)
def prepared_model(name, directory):
    from fastembed import TextEmbedding
    from tokenizers import Tokenizer
    if not (Path(directory) / 'manifest.json').exists():
        raise ValueError('Local embedding model is not prepared; run scripts/prepare_embeddings.py')
    model = TextEmbedding(model_name=name, cache_dir=directory, threads=2, local_files_only=True)
    tokenizer = Tokenizer.from_str(model.model.tokenizer.to_str())
    tokenizer.no_truncation()
    tokenizer.no_padding()
    return model, tokenizer, Lock()


def encode_local(texts, settings, *, deadline=None, control=lambda: None):
    model, tokenizer, lock = prepared_model(settings.local_embedding_model, settings.embedding_cache_dir)
    if len(texts) > 256 or sum(len(t) for t in texts) > 250000:
        raise ValueError('Local embedding input budget exceeded')
    windows, groups = [], []
    with lock:
        for text in texts:
            offsets = tokenizer.encode(text, add_special_tokens=False).offsets
            parts = token_windows(text, offsets)
            groups.append((len(windows), len(windows)+len(parts)))
            windows.extend(parts)
        if len(windows) > 2048:
            raise ValueError('Local embedding window budget exceeded')
        vectors = []
        for start in range(0, len(windows), 32):
            control()
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError('Embedding deadline exhausted')
            vectors.extend(model.embed(windows[start:start+32], batch_size=32))
    output = []
    for start,end in groups:
        row = [sum(float(v[i]) for v in vectors[start:end])/(end-start) for i in range(len(vectors[start]))]
        norm = math.sqrt(sum(x*x for x in row))
        output.append([x/norm for x in row] if norm else row)
    return output
