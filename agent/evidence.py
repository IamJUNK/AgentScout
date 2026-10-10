from __future__ import annotations
import hashlib
import json
import re
from collections import deque
from agent.fallback import estimate_tokens
from models.schemas import EvidenceChunk

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
    """Visit every paragraph and its tail; offsets refer to cleaned text."""
    section = ""
    for match in re.finditer(r"[^\n]+", text):
        if match.group().startswith("#"):
            section = match.group().lstrip("# ")
        start = match.start()
        while start < match.end():
            end = min(start + size, match.end())
            yield text[start:end], start, end, section
            if end == match.end():
                break
            start = end - overlap


def select_evidence(documents, questions, token_budget):
    chunks = {}
    for doc in documents:
        if doc.get("fetch_status") == "failed":
            continue
        entries = [("user" if doc["url"].startswith("user://") else ("mock" if doc.get("mock") else "body"), doc.get("content", ""))]
        if doc.get("snippet") and doc.get("snippet") != doc.get("content"):
            entries.append(("mock" if doc.get("mock") else "snippet", doc["snippet"]))
        for kind, content in entries:
            for text, start, end, section in split_document(content):
                if not text.strip():
                    continue
                eid = "E" + hashlib.sha256(f"{doc['url']}|{kind}|{start}|{end}|{text}".encode()).hexdigest()[:12]
                chunks[eid] = EvidenceChunk(id=eid, source_id=doc["source_id"], url=doc["url"], title=doc["title"], text=text, section=section, start=start, end=end, kind=kind, retrieved_at=doc["retrieved_at"], published_at=doc.get("published_at"), download_truncated=doc.get("download_truncated", False)).model_dump()
    queues = {}
    for question in questions:
        query = question["text"] + " " + " ".join(question["queries"])
        ranked = []
        for chunk in chunks.values():
            score = relevance(query, chunk["text"] + " " + chunk["section"])
            if chunk["kind"] == "user":
                # Material explicitly supplied for this task may lack query keywords.
                score = max(score, .001)
            if score > 0:
                chunk["question_ids"].append(question["id"])
                ranked.append((score, chunk))
        ranked.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
        first, rest, seen = [], [], set()
        for _, chunk in ranked:
            if chunk["url"] not in seen:
                first.append(chunk)
                seen.add(chunk["url"])
            else:
                rest.append(chunk)
        queues[question["id"]] = deque(first + rest)
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
    return list(chosen.values()), {"scanned_chunks": len(chunks), "selected_chunks": len(chosen), "relevant_chunks": sum(bool(c["question_ids"]) for c in chunks.values()), "omitted_relevant_chunks": sum(bool(c["question_ids"]) and c["id"] not in chosen for c in chunks.values()), "estimated_tokens": used, "token_budget": token_budget, "selection_method": "lexical relevance over all acquired paragraphs; question/source diversity", "selection_is_heuristic": True}
