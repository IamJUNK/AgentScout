"""Generate a key-free Mock result then show the read-only NiceGUI preview."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.graph import run_research
from config import Settings
from app import create_app
from scripts.preview_saved import SavedPreview
import uvicorn

if __name__=='__main__':
    preview=SavedPreview.__new__(SavedPreview)
    preview.saved=run_research('比较 LangGraph 和 CrewAI 的适用场景',mock=True,settings=Settings())
    uvicorn.run(create_app(preview),host='127.0.0.1',port=8502)
