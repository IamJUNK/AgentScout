import pytest
from agent.quality import requirements, check_plan, check_report, check_semantics, source_type
from agent.fallback import plan_research_fallback
from models.research import StructuredReport, SemanticReview
from models.schemas import ResearchPlan

def fixture_report():
    return StructuredReport.model_validate({'sections':[{'question_id':'q1','claims':[{'id':'C1','text':'Only one writer','supports':[{'evidence_id':'E1','quote':'readers do not block writers'}]}]}]})

def test_explicit_questions_cannot_be_merged():
    reqs = requirements('WAL 是否允许多个写入者，以及 SQLITE_BUSY 是否仍可能发生')
    assert len(reqs) == 2
    with pytest.raises(ValueError):
        check_plan(ResearchPlan.model_validate({'questions':[{'text':'combined','queries':['x'],'requirement_ids':['r1','r2']}]}), reqs)
    assert len(plan_research_fallback('First question? Second question?').questions) == 2

def test_one_body_does_not_legitimize_another_claim_snippet():
    r = fixture_report()
    e = [{'id':'E1','text':'readers do not block writers','kind':'snippet','url':'https://sqlite.org/wal.html','question_ids':['q1']}]
    assert check_report(r,[{'id':'q1'}],e)
    e.append({'id':'E2','text':'unrelated body','kind':'body','url':'https://sqlite.org/wal.html','question_ids':['q1']})
    assert check_report(r,[{'id':'q1'}],e)

def test_semantic_reviewer_must_cover_and_reject_unsupported_claim():
    r = fixture_report()
    review = SemanticReview.model_validate({'claims':[{'claim_id':'C1','status':'unsupported','explanation':'read/write concurrency does not prove writer count'}], 'questions':[{'question_id':'q1','complete':False,'explanation':'missing writer count'}], 'task_compliant':True})
    assert check_semantics(r, review)
    review.claims = []
    assert check_semantics(r, review)

def test_official_domain_forum_is_not_official_document():
    assert source_type('https://sqlite.org/forum/info/123', ['https://sqlite.org']) == 'forum'
    assert source_type('https://sqlite.org/wal.html', ['https://sqlite.org']) == 'official'
    assert source_type('https://sqlite.org.evil.test/wal.html', ['https://sqlite.org']) == 'unknown'

def test_fabricated_quote_is_rejected():
    e = [{'id':'E1','text':'not the quote','kind':'body','url':'https://sqlite.org/wal.html','question_ids':['q1']}]
    assert any('quotation' in x for x in check_report(fixture_report(),[{'id':'q1'}],e))

def test_source_constraint_is_not_a_separate_question():
    text='根据 SQLite 官方文档，解释 WAL 是否允许多个写入者同时写入，以及开启 WAL 后 SQLITE_BUSY 是否仍可能发生。两问分别作答，引用原文。'
    reqs=requirements(text)
    assert len(reqs)==2
    assert 'WAL 是否' in reqs[0].text

def test_numbered_questions_keep_material_constraint_in_original_request():
    reqs=requirements('仅根据提供材料，不要联网。分别回答：1. 服务最多允许多少个写入者？2. 网络断开是否意味着没有费用？')
    assert len(reqs)==2

def test_redirect_to_forum_cannot_inherit_official_source_class():
    e=[{'id':'E1','text':'readers do not block writers','kind':'body','url':'https://sqlite.org/wal.html','final_url':'https://sqlite.org/forum/info/x','question_ids':['q1']}]
    assert check_report(fixture_report(),[{'id':'q1'}],e,official_only=True,official_prefixes=['https://sqlite.org/'])
