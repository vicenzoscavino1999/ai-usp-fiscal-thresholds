"""Frozen-schema verification of current JPM V2 outputs (no scientific calculation)."""
from pathlib import Path
from io import BytesIO
import argparse,csv,hashlib,json,math,sys,zipfile
import numpy as np
import pandas as pd
import yaml
from PIL import Image

class VerificationError(Exception):
    def __init__(self,code,message,**details):
        super().__init__(message);self.code=code;self.details=details

def require(ok,code,message,**details):
    if not ok:raise VerificationError(code,message,**details)

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def local(root,name):
    p=(root/name).resolve()
    require(p.is_relative_to(root.resolve()),'PATH','Path escapes package',path=name)
    return p

def json_load(path):
    def pairs(items):
        d={}
        for k,v in items:
            require(k not in d,'JSON_DUPLICATE','Duplicate JSON key',key=k);d[k]=v
        return d
    def invalid(x):raise VerificationError('NONFINITE','Non-finite JSON constant',value=x)
    return json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=pairs,parse_constant=invalid)

def family(series):
    if pd.api.types.is_bool_dtype(series):return 'boolean'
    if pd.api.types.is_integer_dtype(series):return 'integer'
    if pd.api.types.is_float_dtype(series):return 'number'
    if pd.api.types.is_datetime64_any_dtype(series):return 'datetime'
    return 'string'

def load_table(path,fmt):
    if fmt=='csv':
        with path.open(encoding='utf-8-sig',newline='') as f:header=next(csv.reader(f),[])
        require(len(header)==len(set(header)),'DUPLICATE_COLUMN','Duplicate CSV header')
        return pd.read_csv(path)
    return pd.read_parquet(path)

def validate_table(frame,schema,side):
    columns=schema['columns'];keys=schema['primary_key']
    require(list(frame)==list(columns),'COLUMNS','Missing, extra, duplicate or reordered columns',side=side,expected=list(columns),actual=list(frame))
    require(len(frame)==schema['rows'],'ROWS','Unexpected number of rows',side=side,expected=schema['rows'],actual=len(frame))
    require(schema['row_matching'] in ['key','registered_row_order'],'CONTRACT','Unknown row matching mode')
    for c,spec in columns.items():
        x=frame[c];null=x.isna()
        require(spec['nullable'] or not null.any(),'NULL','Unexpected null',side=side,column=c,rows=np.flatnonzero(null.to_numpy())[:5].tolist())
        if not null.all():
            require(family(x)==spec['type'],'TYPE','Unexpected logical type',side=side,column=c,expected=spec['type'],actual=family(x))
            if spec['type']=='string':require(all(isinstance(v,str) for v in x[~null]),'TYPE','Non-string value',side=side,column=c)
        if pd.api.types.is_numeric_dtype(x) and not pd.api.types.is_bool_dtype(x):
            require(not np.isinf(x.to_numpy(dtype=float,na_value=np.nan)).any(),'NONFINITE','Infinity is not allowed',side=side,column=c)
        if 'allowed' in spec:require(x[~null].isin(spec['allowed']).all(),'ENUM','Unexpected categorical value',side=side,column=c)
    if schema['row_matching']=='key':
        require(bool(keys) and all(k in columns for k in keys),'CONTRACT','Missing declared primary key')
        for k in keys:
            require(k in schema.get('key_nullable',[]) or not frame[k].isna().any(),'KEY_NULL','Unexpected null key',side=side,column=k)
        require(not frame.duplicated(keys).any(),'DUPLICATE_KEY','Duplicate primary key',side=side,keys=keys)
        return frame.sort_values(keys,na_position='first').reset_index(drop=True)
    require(not keys and bool(schema.get('row_order_reason')),'CONTRACT','Ordinal tables need an explicit reason')
    return frame.reset_index(drop=True)

def compare_table(reference,generated,schema,tolerance):
    a=validate_table(reference,schema,'reference');b=validate_table(generated,schema,'generated');stats=[]
    for c,spec in schema['columns'].items():
        x,y=a[c],b[c];xn,yn=x.isna().to_numpy(),y.isna().to_numpy()
        require(np.array_equal(xn,yn),'NULL_PATTERN','Nulls differ from the frozen reference',column=c)
        active=~xn;xx=x[active];yy=y[active]
        mode=spec['comparison'];require(mode in ['metadata','exact','tolerant'],'CONTRACT','Unknown column comparison',column=c)
        error=0.0
        if mode=='metadata':stats.append({'column':c,'status':'PASS','comparison':'metadata_structure_only'});continue
        if mode=='exact':
            ok=np.asarray(xx==yy,dtype=bool)
        else:
            require(spec['type']=='number','CONTRACT','Tolerance allowed only for floating columns',column=c)
            av=xx.to_numpy(dtype=float);bv=yy.to_numpy(dtype=float)
            ok=np.isclose(av,bv,atol=tolerance['atol'],rtol=tolerance['rtol'],equal_nan=False)
        if not ok.all():
            offsets=np.flatnonzero(active)[np.flatnonzero(~ok)[:5]].tolist()
            rows=b.iloc[offsets][schema['primary_key']].astype(str).to_dict('records') if schema['primary_key'] else offsets
            raise VerificationError('VALUES','Values differ',column=c,mismatches=int((~ok).sum()),row_keys_or_ordinals=rows,comparison=mode,expected=a[c].iloc[offsets].tolist(),actual=b[c].iloc[offsets].tolist())
        if spec['type'] in ['number','integer'] and len(xx):error=float(np.max(np.abs(xx.to_numpy(dtype=float)-yy.to_numpy(dtype=float))))
        stats.append({'column':c,'status':'PASS','comparison':mode,'nulls':int(xn.sum()),'max_absolute_difference':error})
    return {'rows':len(a),'keys':schema['primary_key'],'row_matching':schema['row_matching'],'max_absolute_difference':max((s.get('max_absolute_difference',0) for s in stats),default=0),'columns':stats}

def validate_json(value,schema,pointer='$'):
    kind=schema['type']
    checks={'object':isinstance(value,dict),'array':isinstance(value,list),'null':value is None,'boolean':type(value) is bool,'integer':type(value) is int,'number':type(value) in [int,float] and math.isfinite(value),'string':type(value) is str}
    require(checks[kind],'JSON_TYPE','Unexpected JSON type',pointer=pointer,expected=kind)
    if kind=='object':
        require(set(value)==set(schema['properties']),'JSON_KEYS','Unexpected JSON fields',pointer=pointer)
        for k,v in value.items():validate_json(v,schema['properties'][k],pointer+'.'+k)
    elif kind=='array':
        require(len(value)==schema['length'],'JSON_LENGTH','Unexpected JSON list length',pointer=pointer)
        for i,v in enumerate(value):validate_json(v,schema['prefix_items'][i] if 'prefix_items' in schema else schema['items'],pointer+f'[{i}]')

def compare_arrays(a,b,schema,tolerance):
    require(set(a.files)==set(b.files)==set(schema['arrays']),'ARRAY_KEYS','Missing or extra NPZ arrays')
    records=[]
    for k,spec in schema['arrays'].items():
        x,y=a[k],b[k]
        for label,v in [('reference',x),('generated',y)]:
            require(list(v.shape)==spec['shape'],'ARRAY_SHAPE','Unexpected array shape',array=k,side=label)
            require(str(v.dtype)==spec['dtype'],'ARRAY_TYPE','Unexpected array dtype',array=k,side=label)
            require(np.isfinite(v).all(),'NONFINITE','Non-finite array value',array=k,side=label)
        require(np.allclose(x,y,atol=tolerance['atol'],rtol=tolerance['rtol'],equal_nan=False),'ARRAY_VALUES','Array values differ',array=k)
        records.append({'array':k,'shape':spec['shape'],'status':'PASS','max_absolute_difference':float(np.max(np.abs(x-y),initial=0))})
    return {'arrays':records,'max_absolute_difference':max(r['max_absolute_difference'] for r in records)}


def json_difference_samples(reference,generated,limit=8):
    """Explain strict JSON mismatches without changing their acceptance rule."""
    records=[]
    def walk(a,b,pointer):
        if len(records)>=limit or a==b:return
        if isinstance(a,dict) and isinstance(b,dict) and set(a)==set(b):
            for key in a:walk(a[key],b[key],pointer+'.'+key)
        elif isinstance(a,list) and isinstance(b,list) and len(a)==len(b):
            for i,(x,y) in enumerate(zip(a,b)):walk(x,y,pointer+f'[{i}]')
        else:
            item={'pointer':pointer,'expected':a,'actual':b}
            if type(a) in [int,float] and type(b) in [int,float]:item['absolute_difference']=abs(a-b)
            records.append(item)
    walk(reference,generated,'$');return records

def check_integrity(root,manifest,schemas):
    source=json_load(root/'SOURCE_MANIFEST.json')
    require(bool(source.get('files')),'SOURCE_MANIFEST','Empty source manifest')
    for name,h in source['files'].items():
        p=local(root,name);require(p.is_file(),'SOURCE_MISSING','Missing source file',file=name)
        require(sha(p)==h,'SOURCE_HASH','Source hash mismatch',file=name)
    for n in ['verification/schemas.yaml','verification/tolerances.yaml','verification/reference_manifest.json','verification/document_cells.json','compare_results.py','verify_results.py','verify_documents.py']:
        require(n in source['files'],'SOURCE_MANIFEST','Contract file omitted from source manifest',file=n)
    entries=manifest['artifacts'];ids=[e['id'] for e in entries];refs=[e['reference'] for e in entries];outputs=[e['generated'] for e in entries]
    require(len(entries)==manifest['expected_artifact_count'] and len(entries)>0,'INVENTORY','Wrong artifact count')
    require(len(set(ids))==len(ids) and len(set(refs))==len(refs) and len(set(outputs))==len(outputs),'INVENTORY','Duplicate artifact mapping')
    require(set(ids)==set(schemas),'INVENTORY','Schemas do not match the artifact inventory')
    actual={p.relative_to(root).as_posix() for sub in ['reference','reference_inputs'] for p in (root/sub).rglob('*') if p.is_file()}
    require(set(refs)==actual,'REFERENCE_INVENTORY','Missing or extra reference file',missing=sorted(set(refs)-actual),extra=sorted(actual-set(refs)))
    for e in entries:
        p=local(root,e['reference']);require(e['reference'] in source['files'],'SOURCE_MANIFEST','Reference omitted from source manifest',file=e['reference'])
        require(sha(p)==e['reference_sha256'],'REFERENCE_HASH','Reference hash mismatch',file=e['reference'])
    require(bool(manifest['snapshot_sha256']),'SNAPSHOT','Missing frozen snapshot inventory')
    for n,h in manifest['snapshot_sha256'].items():
        require(n in source['files'] and source['files'][n]==h,'SNAPSHOT','Snapshot manifest differs from source manifest',file=n)
        require(sha(local(root,n))==h,'SNAPSHOT_HASH','Frozen input hash mismatch',file=n)
    return {'status':'PASS','source_files_verified':len(source['files']),'snapshot_files_verified':len(manifest['snapshot_sha256'])}

def documentary_checks(root):
    """Read the Word cells directly; never trust a previously written PASS JSON."""
    from verify_documents import check_documents
    return check_documents(root)

def verify(root,report):
    root=root.resolve();records=[];fail=[];warnings=[];integrity=None;docs=None;matched=[]
    try:
        manifest=json_load(root/'verification/reference_manifest.json')
        schemas=yaml.safe_load((root/'verification/schemas.yaml').read_text())
        tolerance=yaml.safe_load((root/'verification/tolerances.yaml').read_text())
        require(manifest['contract_version']==schemas['contract_version']==tolerance['contract_version']==4,'CONTRACT','Unsupported contract version')
        integrity=check_integrity(root,manifest,schemas['schemas'])
        if not (root/'run_logs/execution.json').is_file():warnings.append({'code':'RUN_MANIFEST_MISSING','message':'No execution history; this command verifies existing outputs only.'})
        for entry in manifest['artifacts']:
            try:
                ref=local(root,entry['reference']);gen=local(root,entry['generated'])
                require(gen.is_file(),'OUTPUT_MISSING','Missing regenerated output',file=entry['generated'])
                profile=tolerance['profiles'].get(entry['tier']);require(profile is not None,'TIER','Missing tolerance profile',tier=entry['tier'])
                require(all(math.isfinite(profile[k]) and profile[k]>=0 for k in ['atol','rtol']),'TIER','Invalid tolerance')
                spec=schemas['schemas'][entry['id']]
                if entry['format'] in ['csv','parquet']:stats=compare_table(load_table(ref,entry['format']),load_table(gen,entry['format']),spec,profile)
                elif entry['format']=='npz':
                    with np.load(ref,allow_pickle=False) as a,np.load(gen,allow_pickle=False) as b:stats=compare_arrays(a,b,spec,profile)
                elif entry['format']=='json':
                    a,b=json_load(ref),json_load(gen);validate_json(a,spec['json_schema']);validate_json(b,spec['json_schema']);require(a==b,'JSON_VALUES','JSON values differ',differences=json_difference_samples(a,b));stats={'exact_json':True}
                else:raise VerificationError('FORMAT','Unsupported artifact format')
                records.append({'file':entry['id'],'status':'PASS','tier':entry['tier'],**stats})
            except Exception as exc:fail.append(error_record(entry['id'],exc))
        try:
            im=np.asarray(Image.open(root/'publication/figure_transition.png').convert('RGBA'))
            with zipfile.ZipFile(root/'revision_jpm_v2/paso_07l/evidencia/MANUSCRITO_JPM_V2.docx') as z:
                original=np.asarray(Image.open(BytesIO(z.read('word/media/image1.png'))).convert('RGBA'))
            require(im.shape==original.shape and np.array_equal(im,original),'FIGURE','Figure pixels differ')
            matched=['word/media/image1.png']
        except Exception as exc:fail.append(error_record('Figure 1',exc))
        try:docs=documentary_checks(root)
        except Exception as exc:fail.append(error_record('documentary_cells',exc))
    except Exception as exc:fail.append(error_record('preflight',exc))
    out={'status':'FAIL' if fail else 'PASS','contract_version':4,'files_passed':len(records),'files_failed':len(fail),'figure_pixel_exact':matched,'integrity':integrity,'documentary_checks':docs,'comparisons':records,'failures':fail,'warnings':warnings,'scope':'Fixed-snapshot, fixed-seed V2 verification; between-seed calibration and legacy Tier D applicability remain separate.'}
    report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(out,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    return out

def diagnostic_value(value):
    if isinstance(value,dict):return {k:diagnostic_value(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [diagnostic_value(v) for v in value]
    if isinstance(value,np.generic):value=value.item()
    if isinstance(value,float) and not math.isfinite(value):return {'nonfinite':str(value)}
    return value

def error_record(file,exc):return diagnostic_value({'file':file,'code':getattr(exc,'code','READ_OR_CONTRACT_ERROR'),'error':str(exc),**getattr(exc,'details',{})})

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);parser.add_argument('--report',type=Path)
    a=parser.parse_args(argv);result=verify(a.root,a.report or a.root/'run_logs/COMPARISON.json')
    brief={k:v for k,v in result.items() if k not in ['comparisons','documentary_checks']}
    brief['documentary_checks']={k:v for k,v in (result['documentary_checks'] or {}).items() if k!='cells'}
    print(json.dumps(brief,indent=2,ensure_ascii=False));return int(result['status']!='PASS')

if __name__=='__main__':sys.exit(main())
