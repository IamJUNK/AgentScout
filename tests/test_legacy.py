import hashlib
import json
import sqlite3
import pytest
from storage.legacy import read_legacy

def test_legacy_read_does_not_create_or_modify_schema(tmp_path):
    path=tmp_path/'original.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE run_details(run_id TEXT PRIMARY KEY,state_json TEXT)')
        db.execute('INSERT INTO run_details VALUES (?,?)',('old',json.dumps({'status':'completed','report':'old report','config':{'api_key':'private'}})))
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    result=read_legacy(path)
    assert result[0]['state']=={'status':'completed','report':'old report'}
    assert result[0]['reviews']==[]
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    with sqlite3.connect(path) as db:
        assert [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]==['run_details']

def test_missing_legacy_path_is_not_created(tmp_path):
    path=tmp_path/'missing.db'
    with pytest.raises(FileNotFoundError): read_legacy(path)
    assert not path.exists()
