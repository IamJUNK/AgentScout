"""Read-only rendering of an existing result; no database, queue, search or model calls."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import Settings
from app import create_app
from storage.repository import NotFound,Conflict

class SavedPreview:
    preview=True
    settings=Settings()
    def __init__(self,path):
        self.saved=json.loads(path.read_text(encoding='utf-8'))
        prefixes=self.saved.get('config',{}).get('settings',{}).get('official_source_prefixes',[])
        self.settings=Settings(official_source_prefixes=prefixes)
    def attempt(self):
        s=self.saved
        return {'id':'saved','number':1,'execution_status':'succeeded' if s['execution_status']=='finished' else 'failed',
            'quality_status':s['status'],'token_usage':s['token_usage'],'reserved_tokens':s.get('unaccounted_token_budget',0),
            'updated_at':s['ended_at'],'error_code':None}
    def get_task(self,tid):
        if tid!='saved':raise NotFound('预览任务不存在')
        return {'id':'saved','request':{'input_text':self.saved['input_text']},'current_attempt':self.attempt()}
    def list_tasks(self,*args):return {'items':[{'id':'saved','input_text':self.saved['input_text'],'created_at':self.saved['created_at'],'current_attempt':self.attempt()}],'next_cursor':None}
    def get_attempt(self,aid):return self.attempt()
    def attempts(self,tid):return [self.attempt()]
    def report(self,aid):return {'markdown':self.saved['report'],'structured':self.saved.get('structured_report',{}),'review':self.saved.get('claim_review',{}),'quality_status':self.saved['status']}
    def evidence(self,aid,offset=0,limit=100):return self.saved['evidence'][offset:offset+limit]
    def source(self,aid,sid):return next(d for d in self.saved['source_documents'] if d['source_id']==sid)
    def events(self,aid,after=0,limit=100):
        rows=[{'id':i+1,**e} for i,e in enumerate(self.saved['traces']) if i+1>after][:limit]
        return {'items':rows,'next_cursor':rows[-1]['id'] if rows else after}
    def submit(self,*args):raise Conflict('此页面只预览已保存结果；提交研究请启动 MySQL 与 Worker 服务。')
    def cancel(self,*args):raise Conflict('只读预览')
    def retry(self,*args):raise Conflict('只读预览')

if __name__=='__main__':
    import uvicorn
    if len(sys.argv)!=2:raise SystemExit('Usage: python scripts/preview_saved.py PATH_TO_SAVED_STATE')
    uvicorn.run(create_app(SavedPreview(Path(sys.argv[1]))),host='127.0.0.1',port=8502)
