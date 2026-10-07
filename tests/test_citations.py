from agent.citations import duplicate_citations, validate_report

SOURCES = [{"url": "https://example.com/1"}, {"url": "https://example.com/2"}]

def test_coverage():
    assert validate_report("[来源 1](https://example.com/1)", SOURCES).citation_coverage == 0.5

def test_invalid_citation():
    metric = validate_report("[来源 3](https://invalid.example)", SOURCES)
    assert metric.invalid_citations == ["https://invalid.example"]

def test_uncited_claims():
    metric = validate_report("## 关键发现\n- This is a factual claim\n## 局限性\n- limitation", SOURCES)
    assert "- This is a factual claim" in metric.uncited_claims

def test_duplicate_urls_count_once():
    text = "[来源 1](https://example.com/1) [来源 1](https://example.com/1)"
    assert validate_report(text, SOURCES).cited_sources == 1
    assert duplicate_citations(text) == ["https://example.com/1"]

def test_empty_sources():
    assert validate_report("", []).citation_coverage == 0
