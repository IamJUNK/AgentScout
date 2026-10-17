from __future__ import annotations
import hashlib
import json
import re
from collections import deque
from agent.fallback import estimate_tokens
from models.schemas import EvidenceChunk
from agent.retrieval.ranking import lexical_rank, cosine_rank, rrf, EmbeddingClient

_STOP = {"the", "and", "what", "how", "does", "for", "with", "from", "compare", "research", "please", "only", "about"}
_CN_STOP = {"研究", "什么", "如何", "比较", "哪些", "以及", "进行", "需要", "要求", "分析", "相关", "问题", "是否"}


def terms(text: str) -> set[str]:
    result = {x for x in re.findall(r"[a-z][a-z0-9_-]{1,}", text.casefold()) if x not in _STOP}
    for seq in re.findall(r"[\u3400-\u9fff]+", text):
        result.update(seq[i:i+2] for i in range(len(seq)-1) if seq[i:i+2] not in _CN_STOP)
    return result


def relevance(query: str, text: str) -> float:
    wanted = terms(query)
    return len(wanted & terms(text)) / len(wanted) if wanted else 0.0


def split_document(text: str, size: int = 1100, overlap: int = 150):
    """Preserve small paragraph context and exact offsets into cleaned text."""
    section = ""
    lines = list(re.finditer(r'[^\n]+', text))
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.group().startswith('#'):
            section = line.group().lstrip('# ')
        start, end = line.start(), line.end()
        j = i + 1
        while j < len(lines) and not lines[j].group().startswith('#') and lines[j].end() - start <= size:
            end = lines[j].end()
            j += 1
        while start < end:
            stop = min(start + size, end)
            yield text[start:stop], start, stop, section
            if stop == end:
                break
            start = stop - overlap
        i = j


def select_evidence(documents, questions, token_budget, *, settings=None, embed=None, official_only=False):
    chunks = {}
    excluded = 0
    seen_content = {}
    for doc in documents:
        if doc.get("fetch_status") == "failed":
            continue
        from agent.quality import source_type
        if official_only and source_type(doc.get('final_url') or doc['url'], settings.official_source_prefixes if settings else ()) != 'official':
            excluded += 1
            continue
        entries = [("user" if doc["url"].startswith("user://") else ("mock" if doc.get("mock") else "body"), doc.get("content", ""))]
        if doc.get("snippet") and doc.get("snippet") != doc.get("content"):
            entries.append(("mock" if doc.get("mock") else "snippet", doc["snippet"]))
        for kind, content in entries:
            for text, start, end, section in split_document(content):
                if not text.strip():
                    continue
                # Identical content is indexed once; aliases remain on the source records.
                identity = (kind, text)
                if identity in seen_content:
                    continue
                seen_content[identity] = doc['source_id']
                eid = "E" + hashlib.sha256(f"{doc['url']}|{kind}|{start}|{end}|{text}".encode()).hexdigest()[:12]
                chunks[eid] = EvidenceChunk(id=eid, source_id=doc["source_id"], url=doc["url"], title=doc["title"], text=text, section=section, start=start, end=end, kind=kind, retrieved_at=doc["retrieved_at"], published_at=doc.get("published_at"), download_truncated=doc.get("download_truncated", False)).model_dump()
                chunks[eid]['final_url'] = doc.get('final_url') or doc['url']
    queues = {}
    all_chunks = list(chunks.values())
    texts = [c['section'] + '\n' + c['text'] for c in all_chunks]
    queries = [q['text'] + ' ' + ' '.join(q['queries']) for q in questions]
    vectors = None
    degradation = None
    if settings and settings.retrieval_mode == 'hybrid':
        try:
            if embed is None:
                raise ValueError('No budgeted embedding executor supplied')
            vectors = embed(texts + queries)
        except Exception as exc:
            degradation = type(exc).__name__ + ': embedding unavailable; using BM25'
    for qi, question in enumerate(questions):
        query = question["text"] + " " + " ".join(question["queries"])
        ranked = []
        ranking = lexical_rank(query, texts)
        if vectors is not None:
            ranking = rrf(ranking, cosine_rank(vectors[len(texts)+qi], vectors[:len(texts)]))
        scores = dict(ranking)
        for index, chunk in enumerate(all_chunks):
            score = scores.get(index, 0)
            if chunk["kind"] == "user":
                # Material explicitly supplied for this task may lack query keywords.
                score = max(score, .001)
            if score > 0:
                chunk["question_ids"].append(question["id"])
                ranked.append((score, chunk))
        # Body quality precedes diversity; summaries must not crowd out primary text.
        ranked.sort(key=lambda pair: (pair[1]['kind'] not in {'body','user'}, -pair[0], pair[1]['id']))
        queues[question["id"]] = deque(c for _, c in ranked)
    chosen, used = {}, 0
    while any(queues.values()):
        for queue in queues.values():
            if not queue:
                continue
            chunk = queue.popleft()
            if chunk["id"] in chosen:
                continue
            cost = estimate_tokens(json.dumps(chunk, ensure_ascii=False))
            if used + cost <= token_budget:
                chosen[chunk["id"]] = chunk
                used += cost
    return list(chosen.values()), {"scanned_chunks": len(chunks), "selected_chunks": len(chosen), 'excluded_sources':excluded, "relevant_chunks": sum(bool(c["question_ids"]) for c in chunks.values()), "omitted_relevant_chunks": sum(bool(c["question_ids"]) and c["id"] not in chosen for c in chunks.values()), "estimated_tokens": used, "token_budget": token_budget, "selection_method": 'hybrid_rrf' if vectors is not None else 'bm25', 'degradation': degradation, "selection_is_heuristic": True}
