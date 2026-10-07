from pathlib import Path
from streamlit.testing.v1 import AppTest

def test_streamlit_mock_and_evaluation(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTSCOUT_DB", str(tmp_path / "ui.db"))
    # RunStore's default is resolved at import; inject the temporary store.
    from storage.database import RunStore
    monkeypatch.setattr("storage.database.RunStore", lambda: RunStore(tmp_path / "ui.db"))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state["research_result"]["success"]
    app.button(key="FormSubmitter:evaluation_form-运行评测集").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["evaluation_result"]["summary"]["task_count"] == 10
