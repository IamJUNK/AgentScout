"""Read-only model discovery and one small search, without logging credentials."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from config import load_settings
from tools.search import TavilySearchProvider

s = load_settings()
try:
    r = httpx.get(s.llm_base_url.rstrip('/') + '/models',
                  headers={'Authorization': 'Bearer ' + s.llm_api_key}, timeout=15)
    if r.status_code == 200:
        print(json.dumps({'service': 'model', 'status': 200,
                          'available_models': [m.get('id') for m in r.json().get('data', [])]}))
    else:
        print(json.dumps({'service': 'model', 'status': r.status_code}))
except Exception as exc:
    print(json.dumps({'service': 'model', 'error_type': type(exc).__name__}))
try:
    results = TavilySearchProvider(s.tavily_api_key).search('SQLite WAL official documentation', 2, timeout=15)
    print(json.dumps({'service': 'search', 'status': 'ok', 'count': len(results),
                      'urls': [x.url for x in results]}))
except httpx.HTTPStatusError as exc:
    print(json.dumps({'service': 'search', 'status': exc.response.status_code}))
except Exception as exc:
    print(json.dumps({'service': 'search', 'error_type': type(exc).__name__}))
