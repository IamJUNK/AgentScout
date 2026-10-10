from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from agent.evidence import relevance
from models.schemas import SearchResult


def dedupe_results(results, limit=30):
    if limit <= 0:
        return []
    output = {}
    for item in results:
        try:
            result = item if isinstance(item, SearchResult) else SearchResult.model_validate(item)
            url = result.url.strip()
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                continue
        except (ValueError, TypeError):
            continue
        if url in output:
            prior = output[url]
            prior.question_ids = list(dict.fromkeys(prior.question_ids + result.question_ids))
            prior.queries = list(dict.fromkeys(prior.queries + result.queries))
            if result.snippet and result.snippet not in prior.snippet:
                prior.snippet += "\n" + result.snippet
        elif len(output) < limit:
            output[url] = result.model_copy(update={"url": url})
    return list(output.values())


class MockSearchProvider:
    name = "mock"

    def __init__(self, dataset_path=None):
        path = Path(dataset_path) if dataset_path else Path(__file__).resolve().parents[1] / "data" / "mock_sources.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data["sources"]
        self._items = [SearchResult.model_validate(item) for item in data]

    def search(self, query, max_results=5, timeout=10):
        translations = {"评测": "evaluation", "检索": "retrieval", "抓取": "http", "持久化": "persistence", "安全": "validation", "成本": "cost", "技能": "skills", "实习": "internship", "多智能体": "multi-agent"}
        augmented = query + " " + " ".join(value for key, value in translations.items() if key in query)
        ranked = [(relevance(augmented, item.title + " " + item.snippet), item) for item in self._items]
        ranked.sort(key=lambda pair: -pair[0])
        return dedupe_results([item for score, item in ranked if score > 0], max_results)


class TavilySearchProvider:
    name = "tavily"

    def __init__(self, api_key=None, base_url="https://api.tavily.com/search"):
        if api_key is None:
            from config import load_settings
            api_key = load_settings().tavily_api_key
        self.api_key, self.base_url = api_key, base_url

    def search(self, query, max_results=5, timeout=10):
        if not self.api_key:
            raise RuntimeError("TAVILY_API_KEY is not configured")
        response = httpx.post(self.base_url, json={"api_key": self.api_key, "query": query, "max_results": max(1, min(10, max_results)), "search_depth": "basic"}, timeout=timeout)
        response.raise_for_status()
        return [SearchResult(title=item.get("title", ""), url=item.get("url", ""), snippet=item.get("content", item.get("snippet", "")), source="tavily", published_at=item.get("published_date")) for item in response.json().get("results", [])]
