from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Iterable

from models.schemas import SearchResult


def dedupe_results(results: Iterable[SearchResult], limit: int = 10) -> list[SearchResult]:
    if limit <= 0:
        return []
    limit = min(limit, 10)
    seen: set[str] = set()
    output: list[SearchResult] = []
    for item in results:
        try:
            result = item if isinstance(item, SearchResult) else SearchResult.model_validate(item)
        except Exception:
            continue
        url = result.url.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        output.append(result.model_copy(update={"url": url}))
        if len(output) >= limit:
            break
    return output


class MockSearchProvider:
    name = "mock"

    def __init__(self, dataset_path: str | Path | None = None):
        self.dataset_path = Path(dataset_path) if dataset_path else Path(__file__).resolve().parents[1] / "data" / "mock_sources.json"
        self._items = self._load()

    def _load(self) -> list[SearchResult]:
        if self.dataset_path.exists():
            try:
                data = json.loads(self.dataset_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data = data.get("sources", [])
                return [SearchResult.model_validate(x) for x in data]
            except Exception:
                pass
        return [
            SearchResult(title="LangGraph documentation", url="https://langchain-ai.github.io/langgraph/", snippet="Stateful graph orchestration for reliable agent workflows.", source="mock"),
            SearchResult(title="CrewAI documentation", url="https://docs.crewai.com/", snippet="Framework for role-based multi-agent collaboration.", source="mock"),
            SearchResult(title="AutoGen documentation", url="https://microsoft.github.io/autogen/", snippet="Event-driven and multi-agent conversation patterns.", source="mock"),
            SearchResult(title="OpenAI agent research", url="https://platform.openai.com/docs/", snippet="Guidance for tool-using language model applications.", source="mock"),
        ]

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        terms = {t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", query)}
        translations = {"评测": "evaluation", "检索": "retrieval", "抓取": "http", "持久化": "persistence", "实习": "internship", "岗位": "internship", "安全": "validation", "成本": "cost"}
        terms.update(value for key, value in translations.items() if key in query)
        scored = []
        for item in self._items:
            hay = f"{item.title} {item.snippet}".lower()
            score = sum(1 for term in terms if term in hay)
            scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [x[1] for x in scored]
        return dedupe_results(selected, max_results)


class TavilySearchProvider:
    name = "tavily"

    def __init__(self, api_key: str | None = None, base_url: str = "https://api.tavily.com/search"):
        if api_key is None:
            from config import load_settings
            api_key = load_settings().tavily_api_key
        self.api_key = api_key
        self.base_url = base_url

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not self.api_key:
            raise RuntimeError("TAVILY_API_KEY is not configured")
        try:
            import httpx
            response = httpx.post(self.base_url, json={"api_key": self.api_key, "query": query, "max_results": max_results, "search_depth": "basic"}, timeout=10.0)
            response.raise_for_status()
            payload = response.json()
            return [SearchResult(title=x.get("title", ""), url=x.get("url", ""), snippet=x.get("content", x.get("snippet", "")), source="tavily") for x in payload.get("results", [])]
        except ImportError as exc:
            raise RuntimeError("httpx is required for Tavily search") from exc


def search_queries(queries: list[str], provider: str = "mock", max_results: int = 10, api_key: str | None = None) -> tuple[list[SearchResult], dict[str, int]]:
    if provider.lower() not in {"mock", "tavily"}:
        raise ValueError(f"Unsupported search provider: {provider}")
    searcher = TavilySearchProvider(api_key=api_key) if provider.lower() == "tavily" else MockSearchProvider()
    all_results: list[SearchResult] = []
    counts: dict[str, int] = {}
    failures: list[str] = []
    for query in queries:
        try:
            found = searcher.search(query, max_results=min(max_results, 10))
            counts[query] = len(found)
            all_results.extend(found)
        except Exception as exc:
            counts[query] = 0
            failures.append(type(exc).__name__)
    if not all_results and failures:
        raise RuntimeError("Search failed; check credentials, connectivity or switch to Mock. " + ", ".join(failures))
    return dedupe_results(all_results, max_results), counts

