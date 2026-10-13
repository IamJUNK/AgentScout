"""Run the current app with key-free settings and a separate demo database."""
from pathlib import Path
import os
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config


def demo_settings():
    # Never load the developer's .env while capturing public documentation.
    return config.Settings(search_provider="mock")


config.load_settings = demo_settings
os.environ["AGENTSCOUT_DB"] = str(ROOT / "data" / "readme-demo.db")
runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
