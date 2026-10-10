from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_streamlit_research_and_evaluation(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENTSCOUT_DB',str(tmp_path/'ui.db'))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=40).run()
    assert not app.exception
    assert len(app.radio)==0
    assert app.text_area[0].label=='研究需求'
    app.button(key='FormSubmitter:research_form-开始研究').click().run(timeout=40)
    assert not app.exception
    assert app.session_state['research_result']['status']=='demo'
    assert not app.session_state['research_result']['success']
    assert not app.session_state['busy']
    app.button(key='FormSubmitter:evaluation_form-运行评测集').click().run(timeout=40)
    assert not app.exception
    result=app.session_state['evaluation_result']
    assert result['schema_version']==2 and result['summary']['task_count']==10
    assert result['summary']['completion_rate']==0
    assert result['summary']['execution_rate']==1


def test_material_only_ui_does_not_search(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENTSCOUT_DB',str(tmp_path/'material-ui.db'))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=40).run()
    app.text_area[0].set_value('Only use the supplied material to explain zircon isotope results')
    app.text_area[1].set_value('zircon isotope result is 17 units')
    app.button(key='FormSubmitter:research_form-开始研究').click().run(timeout=40)
    assert not app.exception
    run=app.session_state['research_result']
    assert run['search_call_count']==0 and run['evidence']
