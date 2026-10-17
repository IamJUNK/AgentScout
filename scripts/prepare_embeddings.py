"""Explicit model download; never reads API secrets or starts a research task."""
import hashlib
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import Settings

def main():
    from fastembed import TextEmbedding
    settings=Settings()
    directory=Path(settings.embedding_cache_dir)
    directory.mkdir(parents=True,exist_ok=True)
    model=TextEmbedding(model_name=settings.local_embedding_model,cache_dir=str(directory),threads=2)
    details=next(m for m in TextEmbedding.list_supported_models() if m['model']==settings.local_embedding_model)
    files=[]
    for path in sorted(directory.rglob('*')):
        if path.is_file() and path.suffix in {'.onnx','.json'} and path.name!='manifest.json':
            digest=hashlib.sha256()
            with path.open('rb') as f:
                for block in iter(lambda:f.read(1024*1024),b''):digest.update(block)
            files.append({'path':str(path.relative_to(directory)),'sha256':digest.hexdigest()})
    (directory/'manifest.json').write_text(json.dumps({'model':details,'files':files},indent=2),encoding='utf-8')
    print(json.dumps({'model':details['model'],'dimension':model.embedding_size,'files':len(files)}))

if __name__=='__main__':main()
