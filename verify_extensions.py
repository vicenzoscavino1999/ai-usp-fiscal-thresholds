"""Verify integrated extensions against the frozen inventory and economic identities."""
from pathlib import Path
import json,math,hashlib,ast
import numpy as np
import pandas as pd
from verify_results import require,VerificationError,json_load,local,sha,compare_table,load_table

def compare_json(a,b,ignored,path='$'):
    if path in ignored:
        require(type(b) in (int,float) and math.isfinite(b) and b>=0,'RUNTIME','Invalid runtime',pointer=path)
        return
    if isinstance(a,dict):
        require(isinstance(b,dict) and set(a)==set(b),'JSON_KEYS','JSON fields differ',pointer=path)
        for k in a:compare_json(a[k],b[k],ignored,path+'.'+k)
    elif isinstance(a,list):
        require(isinstance(b,list) and len(a)==len(b),'JSON_LENGTH','JSON length differs',pointer=path)
        for i,x in enumerate(a):compare_json(x,b[i],ignored,path+f'[{i}]')
    elif type(a) is float:
        require(type(b) in (int,float) and math.isfinite(b) and math.isclose(a,b,rel_tol=1e-8,abs_tol=1e-10),'JSON_NUMBER','JSON numeric value differs',pointer=path)
    else:
        require(type(a) is type(b) and a==b,'JSON_VALUE','JSON value differs',pointer=path)

def semantic_checks(root):
    results=root/'extensions';records=[]
    def ck(name,value):
        require(bool(value),'SCIENTIFIC_CONSISTENCY',name);records.append(name)
    for group,glob in [('convergence','MC_*.csv'),('stress','MC_ESTRES_20*.csv')]:
        frames=[]
        for p in (results/group/'resultados').glob(glob):
            d=pd.read_csv(p);frames.append(d)
            ck('positive denominators:'+p.name,(d.n>0).all() and (d.valid==d.n).all())
            for count,freq in [('recurring_author_crossings','recurring_author_frequency'),('registered_leakage_crossings','registered_leakage_frequency'),('nonnegative_frontier_count','nonnegative_frontier_frequency')]:
                ck('frequency identity:'+p.name+':'+count,np.all((d[count]>=0)&(d[count]<=d.n)) and np.allclose(d[freq],d[count]/d.n,atol=1e-14,rtol=0))
            ck('ordered quantiles:'+p.name,((d.Fmax_p05<=d.Fmax_p50)&(d.Fmax_p50<=d.Fmax_p95)).all())
        z=pd.concat(frames,ignore_index=True);keys=['dependency','country_id','scenario_id','regime_id','policy_variant_id','rule','mode']
        pf=['recurring_author_frequency','registered_leakage_frequency','nonnegative_frontier_frequency'];within=between=0.
        for seed,a in z.groupby('seed'):
            x=a.query('n==25000').set_index(keys).sort_index();y=a.query('n==50000').set_index(keys).sort_index()
            ck('nested keys:'+group+str(seed),x.index.equals(y.index))
            within=max(within,float((x[pf]-y[pf]).abs().max().max()))
        for metric in pf:
            p=z.query('n==50000').pivot(index=keys,columns='seed',values=metric)
            ck('three seeds:'+group+metric,list(p.columns)==[20261114,20261215,20261316])
            between=max(between,float((p.max(axis=1)-p.min(axis=1)).max()))
        ck('registered convergence:'+group,max(within,between)<=.02)
        summary=json_load(results/group/'resultados'/('RESUMEN_MC.json' if group=='convergence' else 'RESUMEN_EJECUCION.json'))
        ck('reported convergence:'+group,abs(within-summary['max_25k_50k_frequency_difference'])<1e-14 and abs(between-summary['max_between_seed_frequency_range'])<1e-14)
    for name in ['COMPARADORES_TRES_SEMILLAS.csv','PUENTE_TRES_SEMILLAS.csv']:
        d=pd.read_csv(results/'paired/resultados'/name);isbridge=name.startswith('PUENTE');freq='B2_frequency_percent' if isbridge else 'frequency'
        ck('paired count identity:'+name,np.allclose(d[freq],d.crossings/d.n*(100 if isbridge else 1),atol=1e-12,rtol=0))
        keys=['mask'] if isbridge else ['mode','rule'];within=0.
        for seed,a in d.groupby('seed'):
            x=a.query('n==25000').set_index(keys);y=a.query('n==50000').set_index(keys)
            within=max(within,float((x[freq]-y[freq]).abs().max())/(100 if isbridge else 1))
        q=d.query('n==50000').pivot(index=keys,columns='seed',values=freq)
        ck('paired convergence:'+name,max(within,float((q.max(axis=1)-q.min(axis=1)).max())/(100 if isbridge else 1))<=.02)
    scope=results/'scope/resultados';d=pd.read_csv(scope/'CLASIFICACION_COBERTURA_V2_480.csv')
    for mode in ['reference','uniform','possible']:
        ck('coverage identity:'+mode,np.array_equal(d['covers_B2_'+mode],d['Fmax_B2_'+mode]>=d.F_recurring_author))
    expected=np.select([d.covers_B2_uniform,d.covers_B2_possible],['uniform_within_declared_domain','possible_not_uniform'],default='no_crossing_within_declared_domain')
    ck('domain classes',np.array_equal(expected,d.coverage_class))
    counts=d.groupby('scenario_role')[['covers_B2_reference','covers_B2_uniform','covers_B2_possible']].sum()
    ck('nonstress classes',counts.loc['nonstress'].tolist()==[4,0,18])
    h=pd.read_csv(scope/'ADJUDICACION_H1_H5_V2.csv').set_index('hypothesis_id')
    ck('five hypothesis records',set(h.index)=={'H1','H2','H3','H4','H5'})
    ck('conditional judgments',h.loc[['H1','H2','H3','H4'],'v2_verdict'].tolist()==['MIXED','NOT_TESTABLE','NOT_TESTABLE','HOLDS'])
    ck('retired H5 disclosed',pd.isna(h.loc['H5','v2_verdict']) and h.loc['H5','legacy_verdict']=='HOLDS' and h.loc['H5','assessment_status']=='RETIRED_LEGACY_CLASSIFICATION_RULE' and bool(h.loc['H5','amendment_reason']))
    diag=pd.read_csv(results/'convergence/resultados/DIAGNOSTICOS_ACTUALES_480.csv')
    low=diag[diag.diagnostic=='exposure_low']
    if low.empty:low=diag[diag.diagnostic.str.contains('low_exposure',regex=False)]
    ck('low exposure reconstructed',len(low)==480 and int(low.covers_B2.sum())==7 and int(low.loc[low.headline,'covers_B2'].sum())==1)
    a=json_load(results/'convergence/resultados/ANALISIS_CONTROL_EXPOSICION.json')
    ck('low exposure remains adverse',a['zero_crossing_expectation_status']=='FAIL_RETAINED' and a['minimum_exposure_B2_numeric']<a['tested_exposure'] and a['test_margin_B2']>0)
    findings=json_load(scope/'SCIENTIFIC_FINDINGS.json')
    ck('scientific disclosure',findings['D_LOW_EXPOSURE']=='FAIL_RETAINED' and not findings['legacy_plan_complete'] and not findings['v2_release_ready'])
    ck('disclosure fields',set(findings)=={'execution_status','hypotheses','H5_status','D_LOW_EXPOSURE','low_exposure_threshold','low_exposure_test','interpretation','legacy_plan_complete','v2_release_ready'})
    ck('disclosure judgments',findings['execution_status']=='PASS' and findings['hypotheses']=={'H1':'MIXED','H2':'NOT_TESTABLE','H3':'NOT_TESTABLE','H4':'HOLDS','H5':None} and findings['H5_status']==h.loc['H5','assessment_status'])
    ck('disclosure threshold',math.isclose(findings['low_exposure_threshold'],a['minimum_exposure_B2_numeric'],rel_tol=0,abs_tol=1e-12) and findings['low_exposure_test']==a['tested_exposure'])
    # File access and elapsed time are runtime metadata. Every reference read must be confined to comparison stages.
    access=list((root/'run_logs').glob('*_access.json'));ck('scientific access reports',len(access)>=38)
    for p in access:
        a=json_load(p);ck('no external access:'+p.name,not a['blocked'])
        if not a['reference_allowed']:ck('no expected-output input:'+p.name,not any(n.startswith(('reference/','reference_inputs/','extension_reference/')) for n in a['files_accessed']))
    for group,filename,source in [('paired','FUNCIONES_REUTILIZADAS.json','revision_jpm_v2/paso_07g/scripts/descomponer_resultados.py'),('stress','FUNCIONES_REUTILIZADAS.json','extensions/convergence/scripts/convergencia_v2.py')]:
        a=json_load(results/group/'resultados'/filename);ck('reused source hash:'+group,a.get('source_sha256',a.get('sha256'))==sha(root/source))
        names=['setup','shapley'] if group=='paired' else ['record','oracle','grid']
        ck('reused function names:'+group,a['functions']==names)
        if group=='stress':ck('AST-only reuse',a['AST_only'] is True)
        else:
            text=(root/source).read_text(encoding='utf-8');tree=ast.parse(text)
            hashes={n.name:hashlib.sha256(ast.get_source_segment(text,n).encode()).hexdigest() for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names}
            ck('reused function hashes',a['function_source_sha256']==hashes)
    return {'checks':len(records),'status':'PASS','coverage_nonstress':counts.loc['nonstress'].to_dict(),'scientific_outcomes':{'D_LOW_EXPOSURE':'FAIL_RETAINED','H1':'MIXED','H2':'NOT_TESTABLE','H3':'NOT_TESTABLE','H4':'HOLDS','H5':'RETIRED_LEGACY_CLASSIFICATION_RULE'},'legacy_plan_complete':False,'v2_release_ready':False}

def verify(root):
    root=Path(root).resolve();contract=json_load(root/'extensions/config/VERIFICATION_CONTRACT.json');source=json_load(root/'SOURCE_MANIFEST.json');records=[];fail=[]
    try:
        for n,h in source['files'].items():require(sha(local(root,n))==h,'SOURCE_HASH','Source changed',file=n)
        entries=contract['artifacts'];require(len(entries)==contract['expected_artifacts'] and len({e['generated'] for e in entries})==len(entries),'INVENTORY','Invalid extension inventory')
        refs={p.relative_to(root).as_posix() for p in (root/'extension_reference').rglob('*') if p.is_file()}
        require(refs=={e['reference'] for e in entries},'REFERENCE_INVENTORY','Extension reference inventory differs')
        expected={e['generated'] for e in entries}|set(contract['additional_outputs'])
        actual={p.relative_to(root).as_posix() for p in (root/'extensions').glob('*/resultados/*') if p.is_file()}
        require(actual==expected,'OUTPUT_INVENTORY','Extension output inventory differs',missing=sorted(expected-actual),extra=sorted(actual-expected))
        for e in entries:
            try:
                ref=local(root,e['reference']);gen=local(root,e['generated'])
                require(e['reference'] in source['files'] and sha(ref)==e['sha256'],'REFERENCE_HASH','Extension reference changed')
                if e['format'] in ['csv','parquet']:stat=compare_table(load_table(ref,e['format']),load_table(gen,e['format']),e['schema'],contract['fixed_seed'])
                else:compare_json(json_load(ref),json_load(gen),e.get('ignored_runtime_pointers',[]));stat={}
                records.append({'file':e['generated'],'status':'PASS','rows':stat.get('rows'),'max_absolute_difference':stat.get('max_absolute_difference',0)})
            except Exception as exc:fail.append({'file':e['generated'],'code':getattr(exc,'code',type(exc).__name__),'error':str(exc),'details':getattr(exc,'details',{})})
        semantic=semantic_checks(root)
    except Exception as exc:
        semantic=None;fail.append({'file':'integrated_guards','code':getattr(exc,'code',type(exc).__name__),'error':str(exc),'details':getattr(exc,'details',{})})
    return {'status':'FAIL' if fail else 'PASS','files_passed':len(records),'files_failed':len(fail),'comparisons':records,'semantic':semantic,'failures':fail,'fixed_seed':contract['fixed_seed'],'between_seed_frequency_limit':.02}
