from agent.citations import validate_report, duplicate_citations

EVIDENCE = [{"id": "Eone", "url": "https://example.com/1", "text": "the official result is limited"}, {"id": "Etwo", "url": "https://example.com/2", "text": "additional result"}]


def test_evidence_identity_and_url_must_match():
    report = "A factual claim [证据 Eone](https://example.com/2)"
    metrics = validate_report(report, evidence=EVIDENCE)
    assert metrics.invalid_citations and metrics.cited_sources == 0


def test_url_only_or_unread_candidate_is_not_evidence():
    metrics = validate_report("- claim [来源 1](https://example.com/1)", [{"url": "https://example.com/1"}])
    assert metrics.invalid_citations and not metrics.cited_sources


def test_paragraphs_are_checked_outside_named_sections():
    metrics = validate_report("## Custom heading\nA factual claim with no citation\n\n## 来源列表\n[证据 Eone](https://example.com/1)", evidence=EVIDENCE)
    assert metrics.uncited_claims and metrics.citation_coverage == 0
    assert metrics.cited_sources == 0


def test_adding_candidates_does_not_reduce_paragraph_attribution():
    text = "A factual claim [证据 Eone](https://example.com/1)"
    assert validate_report(text, evidence=EVIDENCE[:1]).citation_coverage == 1
    assert validate_report(text, evidence=EVIDENCE).citation_coverage == 1
    assert validate_report(text, evidence=EVIDENCE).source_utilization == .5


def test_unsupported_percentage_is_flagged():
    metrics = validate_report("准确率为 100% [证据 Eone](https://example.com/1)", evidence=EVIDENCE)
    assert metrics.uncited_claims


def test_duplicate_urls_count_once():
    text = "Claim [证据 Eone](https://example.com/1)\nAnother [证据 Eone](https://example.com/1)"
    assert validate_report(text, evidence=EVIDENCE).cited_sources == 1
    assert duplicate_citations(text) == ["https://example.com/1"]


def test_empty_report_is_invalid():
    assert validate_report("", evidence=EVIDENCE).uncited_claims


def test_wrapped_paragraph_has_one_attribution_unit():
    report = "A factual statement spans\nmultiple lines. [证据 Eone](https://example.com/1)"
    metrics = validate_report(report, evidence=EVIDENCE)
    assert metrics.claim_count == 1 and not metrics.uncited_claims


def test_table_headers_are_not_claims_but_rows_are():
    report = "| Item | Result |\n| --- | --- |\n| A | limited [证据 Eone](https://example.com/1) |"
    metrics = validate_report(report, evidence=EVIDENCE)
    assert metrics.claim_count == 1 and metrics.citation_coverage == 1
    assert not metrics.uncited_claims


def test_short_chinese_assertion_still_needs_citation():
    report = "A result [证据 Eone](https://example.com/1)\n\n已证实。"
    assert "已证实。" in validate_report(report, evidence=EVIDENCE).uncited_claims


def test_list_items_do_not_share_citation_across_claims():
    report = "- First unreferenced claim\n- Second claim [证据 Eone](https://example.com/1)"
    metrics = validate_report(report, evidence=EVIDENCE)
    assert metrics.claim_count == 2 and metrics.citation_coverage == .5


def test_reference_subheadings_do_not_count_as_body():
    report = "A supported claim [证据 Eone](https://example.com/1)\n\n## References\n### Additional reading\n[证据 Etwo](https://example.com/2)"
    metrics = validate_report(report, evidence=EVIDENCE)
    assert metrics.cited_sources == 1
