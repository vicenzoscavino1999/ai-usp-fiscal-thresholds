"""Verify a complete core-plus-survey run; a core-only PASS cannot satisfy it."""
from pathlib import Path
import hashlib,importlib.util,json,math,subprocess,sys
import pandas as pd
ROOT=Path(__file__).resolve().parent
class CompleteError(RuntimeError):pass
def require(x,msg):
    if not x:raise CompleteError(msg)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def check_execution(root):
    pre=read(root/'run_logs/FULL_PREFLIGHT.json')
    require(pre['status']=='PASS' and pre['mode']=='complete','No full preflight')
    require(pre['model_inputs_preloaded'] is False and pre['outputs_preloaded'] is False and pre['survey_originals_checked'] is True,'Run did not start from clean sources and original surveys')
    require(pre['source_manifest_sha256']==sha(root/'SOURCE_MANIFEST.json'),'Preflight is from a different candidate')
    execution=read(root/'run_logs/execution.json')
    require(len(execution)==39 and [e['stage'] for e in execution]==list(range(39)) and all(e['returncode']==0 for e in execution),'Core execution incomplete')
    phases=read(root/'run_logs/FULL_EXECUTION.json')
    require([p['phase'] for p in phases[:2]]==['core','surveys'] and all(p['returncode']==0 for p in phases[:2]),'Core and surveys were not both executed')
    require(len(phases) in (2,3),'Unexpected complete execution phases')
    if len(phases)==3:require(phases[2]['phase']=='complete_verification' and phases[2]['returncode']==0,'Previous final verification failed')
    return {'clean_start':True,'core_stages':39,'survey_stage':True}
def check_survey_outputs(root):
    sys.path.insert(0,str(root/'surveys'))
    spec=importlib.util.spec_from_file_location('jpm_survey_verification',root/'surveys/reproduce_surveys.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    count=m.check_source_payload();contract=read(root/'surveys/INPUT_CONTRACT.json');output=root/'survey_results';report=read(output/'SURVEY_REPRODUCTION.json')
    require(report['status']=='PASS' and report['raw_reconstructed'] is True and report['microdata_reexecuted'] is True,'No completed raw survey reconstruction')
    require(report['source_files_verified']==count and report['comparison_references_used_during_calculation'] is False,'Survey scope/source mismatch')
    samples={x['country']:x for x in report['samples']};require(set(samples)=={'PER','CHL'},'Missing survey country')
    require(samples['PER']['raw_rows']==samples['PER']['analysis_households']==33691,'ENAHO sample differs')
    require((samples['CHL']['raw_rows'],samples['CHL']['valid_person_rows'],samples['CHL']['analysis_households'])==(218367,218260,78654),'CASEN sample differs')
    require(report['independent_cost_rows']==14,'Independent household check incomplete')
    require(report['tolerances']==contract['tolerances'],'Survey tolerance changed')
    for c,s in contract['countries'].items():
        require(samples[c]['raw_sha256']==s['raw_sha256'],'Survey original identity differs')
        require(report['function_sha256'][c]==s['function_sha256'],'Survey calculation function differs')
    require(set(report['core_inputs_sha256'])==set(contract['core_inputs']),'Survey anchor inventory differs')
    semantic=m.check_core_inputs(root,contract)
    require(report['core_input_semantic_checks']==semantic,'Survey scientific anchor identity differs')
    for n,h in report['core_inputs_sha256'].items():require(sha(root/n)==h,'Anchor changed since survey calculation: '+n)
    checks=[];primary={}
    for c in ['PER','CHL']:
        for kind in ['cost','validation']:
            entry=contract['comparisons'][c+'_'+kind];reference=root/'surveys'/entry['path'];require(sha(reference)==entry['sha256'],'Survey reference differs')
            generated=output/entry['filename'];require(generated.is_file(),'Missing regenerated survey output: '+entry['filename'])
            a=pd.read_csv(reference);b=pd.read_csv(generated)
            checks.append(m.compare_frames(a,b,'micro_gmi_version' if kind=='cost' else 'validation_object',entry['filename'],contract['tolerances']))
            if kind=='cost':
                chosen=b.loc[b.primary_variant & b.baseline_gmi_version.eq('GMI_ideal_aggregate')];require(len(chosen)==1,'Primary survey row ambiguous')
                value=float(chosen.iloc[0].difference_percent_vs_official);require(math.isclose(value,report['primary_differences_percent'][c],rel_tol=0,abs_tol=1e-12),'Survey headline inconsistent')
                require(round(value,3)==(-7.734 if c=='PER' else .387),'Manuscript comparison differs');primary[c]=value
    expected={e['filename'] for e in contract['comparisons'].values()}|{'PER_ANCHORS.json','CHL_ANCHORS.json','INDEPENDENT_HOUSEHOLD_TOTALS.csv','SURVEY_REPRODUCTION.json'}
    require({p.name for p in output.iterdir() if p.is_file()}==expected,'Missing or unexpected survey output')
    return {'status':'PASS','tables_passed':len(checks),'primary_differences_percent':primary,'microdata_reexecuted':True,'checks':checks}
def main():
    root=ROOT;logs=root/'run_logs';logs.mkdir(exist_ok=True)
    try:
        # Independently verify actual core and extension outputs again, not a saved PASS flag.
        p=subprocess.run([sys.executable,'-B',str(root/'verify_all.py')],cwd=root,capture_output=True,text=True)
        (logs/'FINAL_CORE_VERIFICATION.log').write_text(p.stdout+p.stderr,encoding='utf-8');require(p.returncode==0,'Core/extension verification failed')
        core=read(logs/'COMPARISON_FULL.json');require(core['status']=='PASS' and core['files_failed']==0,'Core verification not PASS')
        execution=check_execution(root);surveys=check_survey_outputs(root)
        result={'status':'PASS','scope':'Complete fresh reconstruction: core, extensions, current documents and both raw-survey comparisons','core_files_passed':core['core_files_passed'],'extension_files_passed':core['extension_files_passed'],'survey_tables_passed':surveys['tables_passed'],'documentary_cells':core['documentary_cells'],'figure_pixel_exact':core['figure_pixel_exact'],'scientific_outcomes':core['scientific_outcomes'],'surveys':surveys,'execution':execution,'source_manifest_sha256':sha(root/'SOURCE_MANIFEST.json'),'v2_release_ready':False,'published':False,'remaining':'Remote CI execution, final availability/deposit and editorial submission remain separate.'}
    except Exception as exc:result={'status':'FAIL','scope':'complete','error':str(exc),'v2_release_ready':False}
    (logs/'COMPARISON_COMPLETE.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False));return int(result['status']!='PASS')
if __name__=='__main__':raise SystemExit(main())
