"""Fresh reconstruction of the fiscal core and both raw survey comparisons."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,time
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def dump(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def require(x,msg):
    if not x:raise RuntimeError(msg)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--raw-root',type=Path,required=True);a=ap.parse_args();raw=a.raw_root.resolve()
    source=read(ROOT/'SOURCE_MANIFEST.json')['files']
    for n,h in source.items():require(sha(ROOT/n)==h,'Changed source: '+n)
    actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file()}
    require(actual==set(source)|{'SOURCE_MANIFEST.json'},'A complete run requires a fresh source extraction without prior outputs.')
    contract=read(ROOT/'surveys/INPUT_CONTRACT.json')
    for c,s in contract['countries'].items():require((raw/s['raw_relative']).is_file() and sha(raw/s['raw_relative'])==s['raw_sha256'],'Missing or changed original survey: '+c)
    logs=ROOT/'run_logs';logs.mkdir()
    dump(logs/'FULL_PREFLIGHT.json',{'status':'PASS','mode':'complete','source_files':len(source),'source_manifest_sha256':sha(ROOT/'SOURCE_MANIFEST.json'),'model_inputs_preloaded':False,'outputs_preloaded':False,'survey_originals_checked':True,'utc':datetime.now(timezone.utc).isoformat()})
    env={**os.environ,'NPY_DISABLE_CPU_FEATURES':'X86_V4','PYTHONDONTWRITEBYTECODE':'1','PYTHONHASHSEED':'0','PYTHONUTF8':'1','PYTHONNOUSERSITE':'1'}
    phases=[('core',[sys.executable,'-B','-X','utf8','-u','reproduce.py']),('surveys',[sys.executable,'-B','-u','surveys/reproduce_surveys.py','--core-root',str(ROOT),'--raw-root',str(raw),'--output',str(ROOT/'survey_results')]),('complete_verification',[sys.executable,'-B','-u','verify_complete.py'])]
    records=[]
    for name,cmd in phases:
        print('START '+name,flush=True);t=time.perf_counter();log=logs/('FULL_'+name+'.log')
        with log.open('w',encoding='utf-8') as f:p=subprocess.run(cmd,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
        records.append({'phase':name,'returncode':p.returncode,'seconds':time.perf_counter()-t,'log':log.relative_to(ROOT).as_posix()})
        dump(logs/'FULL_EXECUTION.json',records);print(json.dumps(records[-1]),flush=True)
        if p.returncode:print(log.read_text(encoding='utf-8')[-5000:],flush=True);return p.returncode
    for n,h in source.items():require(sha(ROOT/n)==h,'Source changed during execution: '+n)
    report=read(logs/'COMPARISON_COMPLETE.json');require(report['status']=='PASS','Complete verification did not pass')
    print(json.dumps({k:report[k] for k in ['status','scope','core_files_passed','extension_files_passed','survey_tables_passed','documentary_cells','scientific_outcomes']},ensure_ascii=False),flush=True)
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:print('COMPLETE RUN FAILED: '+str(exc),file=sys.stderr,flush=True);raise SystemExit(1)
