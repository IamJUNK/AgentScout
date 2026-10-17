"""Default is read-only dry-run. Import creates archive records, never queue jobs."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from storage.legacy import read_legacy, import_records

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database',type=Path)
    parser.add_argument('--output',type=Path,help='Export to a NEW JSON file (never overwrites)')
    parser.add_argument('--import-mysql',action='store_true')
    parser.add_argument('--apply',action='store_true',help='Required with --import-mysql')
    args=parser.parse_args()
    if args.import_mysql and not args.apply: parser.error('MySQL import requires --apply; omit import flags for dry-run')
    records=read_legacy(args.database)
    print(json.dumps({'mode':'dry-run','records':len(records),'reviews':sum(len(r['reviews']) for r in records)},ensure_ascii=False))
    if args.output:
        with args.output.open('x',encoding='utf-8') as output:
            json.dump({'schema_version':1,'kind':'legacy_archive','records':records},output,ensure_ascii=False,indent=2)
    if args.import_mysql:
        from config import load_settings
        from storage.repository import Repository
        repo=Repository(load_settings().database_url)
        try: print(json.dumps(import_records(repo,records)))
        finally: repo.engine.dispose()

if __name__=='__main__': main()
