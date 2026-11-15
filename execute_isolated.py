from pathlib import Path
import sys,os,runpy,json,atexit
B=Path(__file__).resolve().parent;target=(B/sys.argv[1]).resolve();log=B/'run_logs';log.mkdir(exist_ok=True)
seen=set();blocked=[];allow_reference=os.environ.get('JPM_COMPARE')=='1'
roots=[B,Path(sys.prefix),Path(sys.base_prefix)]
if os.name=='nt':
 roots.append(Path(os.environ['WINDIR']))
else:
 # OS libraries and metadata; the Docker root filesystem is mounted read-only.
 roots.extend(Path(p) for p in ['/usr','/etc','/proc','/sys','/dev','/lib','/lib64'])
roots=[p.resolve() for p in roots]
def inside(p,root):return p==root or root in p.parents
def audit(event,args):
 if event in ['socket.connect','socket.getaddrinfo']:raise RuntimeError('Network disabled during scientific reproduction')
 if event!='open' or not isinstance(args[0],(str,bytes,os.PathLike)):return
 p=Path(os.fsdecode(args[0])).resolve()
 if not any(inside(p,r) for r in roots):
  blocked.append(str(p));raise RuntimeError('External filesystem dependency: '+str(p))
 if any(inside(p,B/x) for x in ['reference','reference_inputs','extension_reference','surveys/reference','survey_comparators/aggregates']) and not allow_reference:raise RuntimeError('Expected results cannot be scientific inputs: '+str(p))
 if inside(p,B):seen.add(p.relative_to(B).as_posix())
def finish():
 (log/(target.stem+'_access.json')).write_text(json.dumps({'files_accessed':sorted(seen),'blocked':blocked,'reference_allowed':allow_reference},indent=2),encoding='utf-8')
atexit.register(finish);sys.addaudithook(audit);sys.dont_write_bytecode=True;sys.path.insert(0,str(target.parent));sys.argv=[str(target),*sys.argv[2:]]
runpy.run_path(str(target),run_name='__main__')
