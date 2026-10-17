"""Fixed-corpus ranking experiment. Never calls a model API or changes labels."""
import json
import time
from pathlib import Path
from agent.retrieval.local import encode_local
from agent.retrieval.ranking import lexical_rank, cosine_rank, rrf
from config import Settings, ROOT

def measure(ranking, relevant, k=3):
    ids=[i for i,_ in ranking]
    hits=set(ids[:k]) & set(relevant)
    rank=next((i+1 for i,v in enumerate(ids) if v in relevant),None)
    return {'recall_at_3':len(hits)/len(relevant),'reciprocal_rank':1/rank if rank else 0}

def main():
    corpus=json.loads((ROOT/'evals/fixtures/retrieval_cases.json').read_text(encoding='utf-8'))
    cases=corpus['dev']+corpus['frozen']
    settings=Settings()
    started=time.perf_counter()
    vectors=encode_local(corpus['documents']+[c['query'] for c in cases],settings)
    elapsed=round(time.perf_counter()-started,3)
    n=len(corpus['documents']); rows=[]
    for i,case in enumerate(cases):
        bm25=lexical_rank(case['query'],corpus['documents'])
        dense=cosine_rank(vectors[n+i],vectors[:n])
        rows.append({'id':case['id'],'split':'dev' if i<len(corpus['dev']) else 'frozen',
            'bm25':measure(bm25,case['relevant']),'dense':measure(dense,case['relevant']),
            'hybrid':measure(rrf(bm25,dense),case['relevant'])})
    report={'model':settings.local_embedding_model,'annotation_status':corpus['annotation_status'],
        'total_embedding_seconds':elapsed,'rows':rows,'summary':{}}
    for split in ('dev','frozen'):
        subset=[r for r in rows if r['split']==split]
        report['summary'][split]={method:{metric:sum(r[method][metric] for r in subset)/len(subset) for metric in ('recall_at_3','reciprocal_rank')} for method in ('bm25','dense','hybrid')}
    target=ROOT/'evals/results/retrieval-upgrade.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report['summary'],ensure_ascii=False,indent=2))

if __name__=='__main__':main()
