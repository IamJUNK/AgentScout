import time
import httpx
import pytest
from models.schemas import SearchResult, SourceDocument
from tools.search import MockSearchProvider, TavilySearchProvider, dedupe_results
from tools.webpage import _clean_html, fetch_page, clear_page_cache, _check_public_host
from agent.evidence import select_evidence


def test_mock_relevance_and_no_unrelated_padding():
    assert "LangGraph" in MockSearchProvider().search("LangGraph", 5)[0].title
    assert MockSearchProvider().search("火山岩年代测定的误差来源", 5) == []


def test_dedupe_merges_query_provenance():
    first = SearchResult(title="a", url="https://example.com", question_ids=["q1"], queries=["one"], snippet="first")
    second = first.model_copy(update={"question_ids": ["q2"], "queries": ["two"], "snippet": "second"})
    result = dedupe_results([first, second])[0]
    assert result.question_ids == ["q1", "q2"]
    assert "second" in result.snippet
    assert dedupe_results([first], 0) == []


def test_source_limit_is_configurable():
    items = [SearchResult(title=str(i), url=f"https://example.com/{i}") for i in range(25)]
    assert len(dedupe_results(items, 20)) == 20


def test_fetch_failure_preserves_snippet_as_distinct_evidence(monkeypatch):
    def broken(*args): raise httpx.ReadTimeout("Timed out")
    monkeypatch.setattr("tools.webpage._fetch_content", broken)
    doc = fetch_page(SearchResult(title="a", url="https://example.com/a", snippet="retained"), force_refresh=True)
    assert doc.content == "" and doc.snippet == "retained"
    assert doc.fetch_status == "snippet_only" and "ReadTimeout" in doc.fetch_error


def test_fetch_empty_failure(monkeypatch):
    monkeypatch.setattr("tools.webpage._fetch_content", lambda *args: (_ for _ in ()).throw(ValueError("blocked")))
    assert fetch_page(SearchResult(title="a", url="https://example.com/a"), force_refresh=True).fetch_status == "failed"


def test_tail_evidence_survives_cleaning_and_selection():
    html = "<nav>skip</nav><article><p>" + "irrelevant introductory text " * 700 + "</p><h2>Discovery</h2><p>zircon isotope result: 17 units</p></article>"
    content = _clean_html(html)
    assert len(content) > 8000 and "zircon isotope" in content and "skip" not in content
    doc = SourceDocument(title="paper", url="https://example.com", source_id="S1", content=content).model_dump()
    evidence, stats = select_evidence([doc], [{"id":"q1", "text":"zircon isotope result", "queries":["zircon isotope"]}], 1500)
    assert any("17 units" in e["text"] and e["start"] > 8000 for e in evidence)
    assert stats["scanned_chunks"] > stats["selected_chunks"]


def test_important_search_snippet_not_discarded():
    doc = SourceDocument(title="article", url="https://example.com", source_id="S1", content="generic company history", snippet="zircon isotope result 17 units").model_dump()
    evidence, _ = select_evidence([doc], [{"id":"q1", "text":"zircon isotope", "queries":["zircon isotope"]}], 1500)
    assert any(e["kind"] == "snippet" for e in evidence)


def fake_network(monkeypatch, handler):
    clear_page_cache()
    client = httpx.Client
    monkeypatch.setattr("tools.webpage._check_public_host", lambda url: None)
    monkeypatch.setattr("tools.webpage.httpx.Client", lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs))


def test_block_page_is_not_success(monkeypatch):
    fake_network(monkeypatch, lambda req: httpx.Response(200, headers={"content-type":"text/html"}, text="<p>Access denied. Verify you are human.</p>"))
    doc = fetch_page(SearchResult(title="blocked",url="https://example.com/blocked"))
    assert doc.fetch_status == "failed"


def test_download_limit_explicit_and_not_cached(monkeypatch):
    calls=[]
    def handler(req):
        calls.append(1)
        return httpx.Response(200, headers={"content-type":"text/html"}, text="<p>" + "data "*500 + "</p>")
    fake_network(monkeypatch, handler)
    item=SearchResult(title="big",url="https://example.com/big")
    first=fetch_page(item,max_bytes=1024)
    second=fetch_page(item,max_bytes=1024)
    assert first.download_truncated and first.fetch_status == "partial"
    assert first.fetch_error and len(calls)==2 and not second.cache_hit


def test_cache_preserves_acquisition_timestamp_and_can_refresh(monkeypatch):
    calls=[]
    def handler(req):
        calls.append(1)
        return httpx.Response(200, headers={"content-type":"text/html"}, text=f"<p>content version {len(calls)}</p>")
    fake_network(monkeypatch,handler)
    item=SearchResult(title="a",url="https://example.com/cache")
    first=fetch_page(item)
    second=fetch_page(item)
    third=fetch_page(item,force_refresh=True)
    assert len(calls)==2 and second.cache_hit
    assert first.retrieved_at == second.retrieved_at
    assert third.content != first.content


def test_unsupported_content_type_is_labeled(monkeypatch):
    fake_network(monkeypatch,lambda req: httpx.Response(200,headers={"content-type":"application/pdf"},content=b"pdf"))
    doc=fetch_page(SearchResult(title="pdf",url="https://example.com/pdf",snippet="summary"))
    assert doc.fetch_status == "snippet_only" and "Unsupported" in doc.fetch_error


def test_private_addresses_are_rejected():
    for address in ("http://127.0.0.1", "http://localhost", "http://192.168.1.1", "file:///tmp/x"):
        with pytest.raises(ValueError): _check_public_host(address)


def test_search_missing_key():
    with pytest.raises(RuntimeError, match="TAVILY_API_KEY"):
        TavilySearchProvider(api_key="").search("agent")


def test_search_network_error(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a,**k: (_ for _ in ()).throw(httpx.ConnectError("offline")))
    with pytest.raises(httpx.ConnectError):
        TavilySearchProvider(api_key="fixture").search("agent")
