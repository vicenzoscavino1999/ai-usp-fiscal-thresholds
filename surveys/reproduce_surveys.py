"""Reconstruct the ENAHO/CASEN cost comparisons from frozen original records."""
from pathlib import Path
from datetime import datetime,timezone
from typing import Any
import argparse,ast,csv,hashlib,io,json,math,platform,sys,time,zipfile
import numpy as np
import pandas as pd
import pyreadstat
from core_identity import check_core_inputs

BASE=Path(__file__).resolve().parent
class SurveyError(RuntimeError):pass
def require(ok,message):
    if not ok:raise SurveyError(message)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def close(a,b,label,rtol=1e-12,atol=1e-10):
    require(math.isfinite(float(a)) and math.isfinite(float(b)) and math.isclose(float(a),float(b),rel_tol=rtol,abs_tol=atol),f'{label}: {a} != {b}')
def check_hash(path,expected):require(path.is_file() and sha(path)==expected,'Missing or changed frozen input: '+str(path))
def check_source_payload():
    manifest=read(BASE/'SOURCE_MANIFEST.json');require(bool(manifest.get('files')),'Empty module manifest')
    for name,digest in manifest['files'].items():
        p=(BASE/name).resolve();require(p.is_relative_to(BASE.resolve()),'Source path escapes module');check_hash(p,digest)
    return len(manifest['files'])

def load_functions(country,contract,core_root):
    spec=contract['countries'][country];path=BASE/spec['calculation_script'];text=path.read_text(encoding='utf-8-sig')
    check_hash(path,contract['historical_scripts'][path.name]['sha256']);tree=ast.parse(text)
    ns={'np':np,'pd':pd,'Path':Path,'Any':Any,'ROOT':core_root/'upstream','__name__':'historical_'+country}
    # Only literal constants, the exception class and the named cost/validation
    # functions are used. Legacy fiscal simulations and module imports are not run.
    for node in tree.body:
        if isinstance(node,ast.Assign):
            try:value=ast.literal_eval(node.value)
            except (ValueError,TypeError):continue
            for target in node.targets:
                if isinstance(target,ast.Name):ns[target.id]=value
    nodes=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)]
    for node in tree.body:
        if isinstance(node,ast.ClassDef) and node.name=='ExtensionError':nodes.append(node)
        elif isinstance(node,ast.FunctionDef) and node.name in contract['functions'][country]:
            digest=hashlib.sha256(ast.get_source_segment(text,node).encode()).hexdigest()
            require(digest==spec['function_sha256'][node.name],'Historical function changed: '+node.name);nodes.append(node)
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(path),'exec'),ns)
    require(all(n in ns for n in contract['functions'][country]),'Missing historical function')
    return ns

def normalize(country,raw_root,contract):
    spec=contract['countries'][country];meta=read(BASE/spec['metadata']);raw=raw_root/spec['raw_relative'];check_hash(raw,spec['raw_sha256'])
    if country=='PER':
        with zipfile.ZipFile(raw) as z:
            names=[n for n in z.namelist() if Path(n).name.lower()=='sumaria-2024.dta']
            require(names==[spec['extracted_member']],'Expected standard Sumaria, excluding 12g')
            blob=z.read(names[0]);require(hashlib.sha256(blob).hexdigest()==spec['extracted_sha256'],'Extracted Stata hash differs')
        frame=pd.read_stata(io.BytesIO(blob),convert_categoricals=False)
        names={str(n).upper():n for n in frame};required=meta['required_variables']
        require(all(n in names for n in required),'Missing ENAHO columns')
        frame=frame[[names[n] for n in required]].copy();frame.columns=required
    else:
        frame,_=pyreadstat.read_sav(str(raw),usecols=meta['column_projection'],apply_value_formats=False)
        require(set(meta['column_projection'])<=set(frame),'Missing CASEN columns')
    frame.insert(0,'survey_year',2024);frame.insert(0,'country_id',country)
    require(len(frame)==spec['expected_rows'],'Survey row count differs')
    return frame

def weighted_oracle(country,frame,costs,official):
    """Independent household totals, scalar fsum, without the vector cost code."""
    records=[];z=float(official['official_poverty_line_lcu_annual'])
    if country=='CHL':
        valid=frame.pobreza.isin([1,2,3]) & frame.yae.notna() & frame.lp.gt(0) & frame.expr.gt(0)
        persons=frame.loc[valid];groups={}
        for r in persons.itertuples(index=False):
            if r.folio not in groups:groups[r.folio]=r
        households=list(groups.values())
        require(len(households)==78654 and int(valid.sum())==218260,'Oracle CASEN sample differs')
        close(math.fsum(r.expr*r.numper for r in households),math.fsum(float(v) for v in persons.expr),'Oracle household/person weights',rtol=0,atol=0)
    else:households=list(frame.itertuples(index=False))
    for row in costs.itertuples(index=False):
        if country=='PER':
            def term(r):
                line=z if row.policy_variant_z=='pip_ppp_8_30_line' else 12*float(r.LINEA)
                return float(r.FACTOR07)*max(line*float(r.MIEPERHO)-float(getattr(r,row.welfare_variable)),0.0)
        elif row.welfare_concept=='national_methodology_reference':
            def term(r):return float(r.expr)*12*float(r.nae)*max(float(r.lp)-float(r.yae),0.0)
        else:
            variable='ytotcorh' if row.welfare_concept=='primary_total_corrected_income' else 'ymonecorh'
            def term(r):return float(r.expr)*max(z*float(r.numper)-12*float(getattr(r,variable)),0.0)
        gap=math.fsum(term(r) for r in households);cost=gap*row.chi_gmi*row.theta_target
        close(gap,row.aggregate_gap_lcu_annual,'Independent aggregate gap')
        close(cost,row.cost_micro_lcu,'Independent micro cost')
        base=float(official['official_'+('ideal' if row.baseline_gmi_version=='GMI_ideal_aggregate' else 'loaded')+'_cost_lcu'])
        diff=100*(cost/base-1);close(diff,row.difference_percent_vs_official,'Independent percentage')
        records.append({'country_id':country,'micro_gmi_version':row.micro_gmi_version,'independent_cost_lcu':cost,'vector_cost_lcu':row.cost_micro_lcu,'absolute_difference_lcu':abs(cost-row.cost_micro_lcu),'independent_difference_percent':diff})
    return records

def compare_frames(expected,actual,key,label,tolerance):
    require(list(expected)==list(actual),'Different columns: '+label)
    require(len(expected)==len(actual) and not expected[key].duplicated().any() and not actual[key].duplicated().any(),'Different row inventory: '+label)
    a=expected.sort_values(key).reset_index(drop=True);b=actual.sort_values(key).reset_index(drop=True)
    checked=0;errors={}
    for c in a:
        require(a[c].isna().equals(b[c].isna()),'Missing-value pattern differs: '+label+'/'+c)
        mask=a[c].notna();x=a.loc[mask,c];y=b.loc[mask,c]
        if pd.api.types.is_numeric_dtype(x) and not pd.api.types.is_bool_dtype(x):
            require(pd.api.types.is_numeric_dtype(y),'Non-numeric actual column: '+c)
            xx=x.to_numpy(dtype=float);yy=y.to_numpy(dtype=float)
            require(np.isfinite(xx).all() and np.isfinite(yy).all(),'Nonfinite comparison value')
            require(np.allclose(xx,yy,**tolerance),'Numerical comparison differs: '+label+'/'+c)
            errors[c]=float(np.abs(xx-yy).max(initial=0))
        else:require(x.tolist()==y.tolist(),'Exact comparison differs: '+label+'/'+c)
        checked+=len(x)
    return {'file':label,'rows':len(a),'columns':len(a.columns),'nonnull_values_checked':checked,'max_absolute_errors':errors,'status':'PASS'}

def run(raw_root,core_root,output):
    start=time.perf_counter();source_count=check_source_payload();contract=read(BASE/'INPUT_CONTRACT.json')
    require(not output.exists() or not any(output.iterdir()),'Use a new empty output directory')
    output.mkdir(parents=True,exist_ok=True)
    core_checks=check_core_inputs(core_root,contract)
    core_hashes={n:sha(core_root/n) for n in contract['core_inputs']}
    policy=pd.read_parquet(core_root/'upstream/data/model_inputs/policy_cost.parquet')
    # Freeze and log access to expected survey values. Computations cannot read them.
    phase={'comparison':False};access=[];reference=(BASE/'reference').resolve()
    projections={(raw_root/s['projection_relative']).resolve() for s in contract['countries'].values()}
    def audit(event,args):
        if event!='open' or not args or not isinstance(args[0],(str,bytes)):return
        try:p=Path(args[0]).resolve()
        except (TypeError,ValueError):return
        if p.is_relative_to(reference) or p in projections:
            require(phase['comparison'],'Expected survey results cannot be calculation inputs')
            access.append({'name':p.name,'phase':'comparison'})
    sys.addaudithook(audit)
    frames={};calculations={};oracles=[];sample=[]
    for country in ['PER','CHL']:
        print('START raw reconstruction '+country,flush=True)
        ns=load_functions(country,contract,core_root);frame=normalize(country,raw_root,contract);frames[country]=frame
        official=ns['official_inputs']({'policy_cost':policy})
        # Independently check the aggregate PIP denominator and common income line.
        close(official['official_poverty_line_ppp_daily'],8.3,'PIP line',rtol=0,atol=0)
        for target in ['ideal','loaded']:
            base=official['chi_gmi']*official['theta_'+target]*official['official_population_total']*official['official_poverty_line_lcu_annual']*official['official_poverty_gap']
            close(base,official['official_'+target+'_cost_lcu'],'PIP aggregate cost identity')
        if country=='PER':
            validation=ns['validate_enaho'](frame,official);costs=ns['build_costs'](frame,official);households=len(frame);valid_persons=None
        else:
            validation,hh=ns['validate_casen'](frame);costs=ns['build_costs'](hh,official);households=len(hh);valid_persons=218260
        oracle=weighted_oracle(country,frame,costs,official);oracles.extend(oracle)
        for kind,data in [('cost',costs),('validation',validation)]:data.to_csv(output/contract['comparisons'][country+'_'+kind]['filename'],index=False)
        dump(output/(country+'_ANCHORS.json'),official)
        calculations[country]={'cost':costs,'validation':validation}
        sample.append({'country':country,'raw_rows':len(frame),'analysis_households':households,'valid_person_rows':valid_persons,'raw_sha256':contract['countries'][country]['raw_sha256']})
        print('CALCULATED '+country+' cost_rows='+str(len(costs)),flush=True)
    phase['comparison']=True
    reports=[];projections_report=[]
    for country in ['PER','CHL']:
        s=contract['countries'][country];p=raw_root/s['projection_relative']
        # Optional archived projection is evidence, never a calculation input.
        if p.is_file():
            check_hash(p,s['projection_sha256']);archived=pd.read_parquet(p)
            pd.testing.assert_frame_equal(archived,frames[country],check_exact=True,check_dtype=True)
            projections_report.append({'country':country,'rows':len(archived),'columns':len(archived.columns),'exact_values_and_dtypes':True})
        for kind in ['cost','validation']:
            spec=contract['comparisons'][country+'_'+kind];p=BASE/spec['path'];check_hash(p,spec['sha256'])
            reports.append(compare_frames(pd.read_csv(p),pd.read_csv(output/spec['filename']),'micro_gmi_version' if kind=='cost' else 'validation_object',spec['filename'],contract['tolerances']))
    pd.DataFrame(oracles).to_csv(output/'INDEPENDENT_HOUSEHOLD_TOTALS.csv',index=False)
    # All read-only source hashes are checked again after the work.
    for country,s in contract['countries'].items():check_hash(raw_root/s['raw_relative'],s['raw_sha256'])
    for n,h in core_hashes.items():check_hash(core_root/n,h)
    primary={c:float(d['cost'].loc[d['cost'].primary_variant & d['cost'].baseline_gmi_version.eq('GMI_ideal_aggregate'),'difference_percent_vs_official'].iloc[0]) for c,d in calculations.items()}
    result={'status':'PASS','scope':'Raw survey reconstruction of the separate household-cost comparison; aggregate fiscal model unchanged','utc':datetime.now(timezone.utc).isoformat(),'source_files_verified':source_count,'raw_reconstructed':True,'microdata_reexecuted':True,'samples':sample,'comparisons':reports,'projection_checks':projections_report,'independent_cost_rows':len(oracles),'primary_differences_percent':primary,'reference_access':access,'comparison_references_used_during_calculation':False,'core_inputs_sha256':core_hashes,'core_input_semantic_checks':core_checks,'function_sha256':{c:s['function_sha256'] for c,s in contract['countries'].items()},'tolerances':contract['tolerances'],'environment':{'python':platform.python_version(),'platform':platform.platform(),'pandas':pd.__version__,'numpy':np.__version__,'pyreadstat':pyreadstat.__version__},'elapsed_seconds':time.perf_counter()-start,'raw_files_redistributed':False,'v2_release_ready':False}
    dump(output/'SURVEY_REPRODUCTION.json',result)
    print(json.dumps({k:result[k] for k in ['status','microdata_reexecuted','samples','primary_differences_percent','elapsed_seconds']},ensure_ascii=False),flush=True)
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--raw-root',type=Path,required=True);ap.add_argument('--core-root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    try:run(a.raw_root.resolve(),a.core_root.resolve(),a.output.resolve());return 0
    except Exception as exc:
        if a.output.exists():dump(a.output/'SURVEY_FAILURE.json',{'status':'FAIL','error':str(exc),'type':type(exc).__name__})
        print('FAIL: '+str(exc),file=sys.stderr,flush=True);return 1
if __name__=='__main__':raise SystemExit(main())
