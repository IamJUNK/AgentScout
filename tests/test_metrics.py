from evals.metrics import evaluate_run, keyword_recall, summarize


def test_keyword_synonyms_are_diagnostic():
    words=['state','workflow','multi-agent','orchestration']
    assert keyword_recall('状态、工作流、多智能体、编排',words)==1
    assert keyword_recall('',[])==1


def completed_run():
    return {'run_id':'a','report':'A supported result','status':'completed','execution_status':'finished','evidence':[{'id':'E1'}],'assessment':[{'status':'supported'}],'report_review':{'task_compliant':True,'complete':True,'supported':True,'issues':[]},'citation_metrics':{'cited_sources':1,'invalid_citations':[],'uncited_claims':[],'citation_coverage':1}}


def test_keywords_and_arbitrary_source_quota_do_not_determine_completion():
    row=evaluate_run(completed_run(),{'id':'1','expected_keywords':['unmentioned synonym'],'required_source_count':50})
    assert row['completed'] and row['keyword_recall']==0


def test_unresolved_citations_prevent_completion():
    run=completed_run()
    run['citation_metrics']['uncited_claims']=['claim']
    assert not evaluate_run(run,{'id':'1'})['completed']


def test_partial_demo_and_failed_never_count_as_completed():
    for status in ['demo','partial','failed','insufficient_evidence','needs_review']:
        run=completed_run();run['status']=status
        assert not evaluate_run(run,{'id':'1'})['completed']


def test_semantic_and_evidence_gaps_prevent_completion():
    run=completed_run();run['assessment'][0]['status']='conflicting'
    assert not evaluate_run(run,{'id':'1'})['completed']
    run=completed_run();run['report_review']['supported']=False
    assert not evaluate_run(run,{'id':'1'})['completed']


def test_title_echo_does_not_count_toward_keywords():
    run=completed_run();run['report']='# target keyword\n> 研究需求：target keyword\nA supported answer'
    assert evaluate_run(run,{'id':'1','expected_keywords':['target keyword']})['keyword_recall']==0


def test_empty_report_and_errors_fail():
    run=completed_run();run['report']='';run['errors']=['failure']
    row=evaluate_run(run,{'id':'1'})
    assert not row['completed'] and 'critical node error' in row['failure_reasons']
    assert summarize([])['completion_rate']==0


def test_expected_empty_result_is_not_execution_failure():
    row = evaluate_run({'run_id': 'empty', 'status': 'insufficient_evidence', 'execution_status': 'finished'}, {'id': 'empty'})
    summary = summarize([row])
    assert summary['incomplete_tasks'] == 1
    assert summary['execution_failed_tasks'] == 0
