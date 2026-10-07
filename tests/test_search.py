import httpx
import pytest
from models.schemas import SearchResult
from tools.search import MockSearchProvider, TavilySearchProvider, dedupe_results
from tools.webpage import _clean_html, fetch_page, fetch_pages

def test_mock_results():
    results = MockSearchProvider().search("LangGraph", 5)
    assert len(results) == 5
    assert "LangGraph" in results[0].title

def test_url_deduplication():
    a = SearchResult(title="a", url="https://example.com")
    assert len(dedupe_results([a, a])) == 1

def test_result_bound():
    items = [SearchResult(title=str(i), url=f"https://example.com/{i}") for i in range(20)]
    assert len(dedupe_results(items, 20)) == 10
    assert dedupe_results(items, 0) == []

def test_fetch_failure_fallback(monkeypatch):
    def broken(*args): raise httpx.ReadTimeout("Timed out")
    monkeypatch.setattr("tools.webpage._fetch_content", broken)
    doc = fetch_page(SearchResult(title="a", url="https://example.com", snippet="retained"))
    assert doc.content == "retained"
    assert doc.fetch_status == "snippet_only"
    assert "ReadTimeout" in doc.fetch_error

def test_fetch_empty_failure(monkeypatch):
    def broken(*args): raise ValueError("blocked")
    monkeypatch.setattr("tools.webpage._fetch_content", broken)
    assert fetch_page(SearchResult(title="a", url="https://example.com")).fetch_status == "failed"

def test_fetch_limit(monkeypatch):
    monkeypatch.setattr("tools.webpage._fetch_content", lambda *args: "ok")
    items = [SearchResult(title=str(i), url=f"https://example.com/{i}") for i in range(10)]
    assert len(fetch_pages(items, 20)) == 5

def test_clean_html():
    assert _clean_html("<nav>skip</nav><script>bad</script><p>body</p><footer>skip</footer>") == "body"
    assert len(_clean_html("<p>" + "x" * 9000 + "</p>")) == 8000

def test_search_missing_key():
    with pytest.raises(RuntimeError, match="TAVILY_API_KEY"):
        TavilySearchProvider(api_key="").search("agent")

def test_search_network_error(monkeypatch):
    def broken(*args, **kwargs): raise httpx.ConnectError("offline")
    monkeypatch.setattr(httpx, "post", broken)
    with pytest.raises(httpx.ConnectError):
        TavilySearchProvider(api_key="fixture-placeholder").search("agent")
