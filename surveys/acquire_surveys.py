"""Obtain frozen survey inputs from their providers; never silently replace a version."""
from pathlib import Path
from urllib.request import Request,urlopen
import argparse,hashlib,json,time
BASE=Path(__file__).resolve().parent
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def acquire(spec,destination):
    target=destination/spec['raw_relative'];target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if sha(target)!=spec['raw_sha256']:raise RuntimeError('Existing file differs from the frozen version: '+str(target))
        return {'path':spec['raw_relative'],'status':'EXISTING_HASH_VERIFIED','sha256':spec['raw_sha256']}
    partial=target.with_name(target.name+'.part')
    if partial.exists():raise RuntimeError('A partial download already exists; inspect it before retrying: '+str(partial))
    request=Request(spec['source_url'],headers={'User-Agent':'JPM-V2-survey-reconstruction/1.0'})
    size=0;last=time.monotonic()
    with urlopen(request,timeout=300) as response,partial.open('xb') as out:
        while chunk:=response.read(1024*1024):
            out.write(chunk);size+=len(chunk)
            if time.monotonic()-last>15:print(f'{target.name}: {size} bytes',flush=True);last=time.monotonic()
    digest=sha(partial)
    if digest!=spec['raw_sha256']:raise RuntimeError('Provider file does not match the historical version. Preserved as .part; do not change the contract or use it for exact reproduction. Actual SHA256='+digest)
    partial.rename(target)
    return {'path':spec['raw_relative'],'status':'DOWNLOADED_HASH_VERIFIED','bytes':size,'sha256':digest}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--destination',type=Path,required=True);ap.add_argument('--country',choices=['PER','CHL','both'],default='both');a=ap.parse_args()
    contract=json.loads((BASE/'INPUT_CONTRACT.json').read_text(encoding='utf-8'));countries=['PER','CHL'] if a.country=='both' else [a.country]
    results=[]
    for c in countries:results.append(acquire(contract['countries'][c],a.destination.resolve()))
    print(json.dumps(results,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
