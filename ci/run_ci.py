"""Shared local/GitHub CI entry point. Downloads occur only before offline science."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,time
SOURCE=Path(__file__).resolve().parents[1]
EVIDENCE=None
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def container_user_args():
    # Native Linux bind mounts retain their host owner, even with all capabilities dropped.
    return ['--user',f'{os.getuid()}:{os.getgid()}'] if sys.platform.startswith('linux') else []
def main():
    global EVIDENCE
    ap=argparse.ArgumentParser();ap.add_argument('--workdir',type=Path,required=True);ap.add_argument('--raw-root',type=Path);a=ap.parse_args()
    work=a.workdir.resolve();require_new=not work.exists() or not any(work.iterdir())
    if not require_new:raise RuntimeError('Use a new empty CI work directory')
    if work==SOURCE or SOURCE in work.parents:raise RuntimeError('CI work directory must be outside the source package')
    work.mkdir(parents=True,exist_ok=True);e=work/'evidence';e.mkdir();EVIDENCE=e;run=work/'reproduction';run.mkdir()
    manifest=json.loads((SOURCE/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))['files']
    for n,h in manifest.items():
        p=(SOURCE/n).resolve()
        if not p.is_relative_to(SOURCE) or sha(p)!=h:raise RuntimeError('Source manifest mismatch: '+n)
        target=run/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    shutil.copy2(SOURCE/'SOURCE_MANIFEST.json',run/'SOURCE_MANIFEST.json')
    steps=[]
    def call(name,cmd,timeout=3600):
        print('START '+name,flush=True);t=time.perf_counter()
        with (e/(name+'.log')).open('w',encoding='utf-8') as f:
            try:
                p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,text=True,timeout=timeout)
                code=p.returncode
            except subprocess.TimeoutExpired:
                code=124;f.write('\nStep exceeded its execution timeout.\n')
        steps.append({'step':name,'returncode':code,'seconds':time.perf_counter()-t});(e/'CI_EXECUTION.json').write_text(json.dumps(steps,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(steps[-1]),flush=True)
        if code:print((e/(name+'.log')).read_text(encoding='utf-8')[-5000:],flush=True);raise RuntimeError(name+' failed')
    tag='jpm-v2-r9-ci'
    call('docker_preflight',['docker','version','--format','{{json .Server}}'],timeout=60)
    call('docker_build',['docker','build','--platform','linux/amd64','--tag',tag,str(SOURCE)],timeout=900)
    image=json.loads(subprocess.check_output(['docker','image','inspect',tag],text=True,timeout=60))[0]
    (e/'DOCKER_IMAGE.json').write_text(json.dumps({'id':image['Id'],'os':image['Os'],'architecture':image['Architecture'],'base':'python:3.12.10-slim@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db'},indent=2)+'\n',encoding='utf-8')
    raw=a.raw_root.resolve() if a.raw_root else work/'raw'
    if not a.raw_root:
        raw.mkdir()
        # Use the CA bundle already pinned in requirements-lock.txt for current provider certificates.
        acquisition_bootstrap="import os,certifi,runpy;os.environ['SSL_CERT_FILE']=certifi.where();runpy.run_path('surveys/acquire_surveys.py',run_name='__main__')"
        call('acquire_original_surveys',['docker','run','--rm',*container_user_args(),'--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:rw,nosuid,nodev,size=536870912','--mount',f'type=bind,source={SOURCE},target=/app,readonly','--mount',f'type=bind,source={raw},target=/raw','--workdir','/app',image['Id'],'python','-B','-c',acquisition_bootstrap,'--destination','/raw'],timeout=1200)
    # Raw originals are read-only and cannot enter uploaded CI artifacts.
    base=['docker','run','--rm',*container_user_args(),'--platform','linux/amd64','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:rw,nosuid,nodev,size=2147483648','--mount',f'type=bind,source={run},target=/app','--mount',f'type=bind,source={raw},target=/raw,readonly','--mount',f'type=bind,source={e},target=/evidence','--workdir','/app','-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTHONPATH=/app:/app/surveys','-e','JPM_INTEGRATION_TEST_ROOT=/app','-e','JPM_FULL_TEST_ROOT=/app',image['Id'],'python','-B']
    call('numeric_runtime',base+['ci/check_numeric_runtime.py','--output','/evidence/NUMERIC_RUNTIME.json'])
    try:call('complete_reproduction',base+['-X','utf8','-u','reproduce_complete.py','--raw-root','/raw'])
    finally:
        for n in ['COMPARISON.json','execution.json','COMPARISON_COMPLETE.json','COMPARISON_FULL.json','FULL_PREFLIGHT.json','FULL_EXECUTION.json']:
            if (run/'run_logs'/n).is_file():shutil.copy2(run/'run_logs'/n,e/n)
        comparison=run/'run_logs/COMPARISON.json'
        if comparison.is_file() and json.loads(comparison.read_text(encoding='utf-8'))['status']!='PASS':
            context=run/'revision_jpm_v2/paso_07g/evidencia/CONTEXTOS_80.json'
            if context.is_file():shutil.copy2(context,e/'DIAGNOSTIC_CONTEXTOS_80.json')
    call('tests',base+['-m','pytest','tests','surveys/tests','-q','-p','no:cacheprovider','--junitxml=/evidence/TESTS.xml'],timeout=600)
    for n,h in manifest.items():
        if sha(run/n)!=h:raise RuntimeError('Source changed during CI: '+n)
    result=json.loads((e/'COMPARISON_COMPLETE.json').read_text(encoding='utf-8'))
    if result['status']!='PASS':raise RuntimeError('Complete report not PASS')
    summary={'status':'PASS','scope':'Same CI entry point used locally and in GitHub Actions','local_or_hosted':'github_actions' if os.environ.get('GITHUB_ACTIONS')=='true' else 'local','source_manifest_sha256':sha(SOURCE/'SOURCE_MANIFEST.json'),'image_id':image['Id'],'raw_source':'provided_frozen_files' if a.raw_root else 'provider_downloads_hash_checked','raw_records_uploaded':False,'steps':steps}
    (e/'CI_RESULT.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8');print(json.dumps(summary),flush=True);return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        if EVIDENCE is not None:
            (EVIDENCE/'CI_RESULT.json').write_text(json.dumps({'status':'FAIL','error':str(exc),'source_manifest_sha256':sha(SOURCE/'SOURCE_MANIFEST.json'),'local_or_hosted':'github_actions' if os.environ.get('GITHUB_ACTIONS')=='true' else 'local','raw_records_uploaded':False},indent=2)+'\n',encoding='utf-8')
        print('CI FAILED: '+str(exc),file=sys.stderr,flush=True);raise SystemExit(1)
