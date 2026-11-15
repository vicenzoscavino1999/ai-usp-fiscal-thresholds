"""Fault-injection tests on disposable copies; no reference updates."""
from pathlib import Path
import copy,csv,json,os,shutil,subprocess,sys,zipfile
import numpy as np,pandas as pd,pytest
import verify_results as v

TOL={'atol':1e-10,'rtol':1e-8}
@pytest.fixture
def table_case():
    d=pd.DataFrame({'country':['CHL','PER'],'year':[2024,2024],'prob':[0.27,0.10],'root':[np.nan,1.5],'covered':[True,False],'class':['conditional','uncovered']})
    s={'rows':2,'row_matching':'key','primary_key':['country'],'key_nullable':[],'columns':{
        'country':{'type':'string','nullable':False,'comparison':'exact','allowed':['CHL','PER']},
        'year':{'type':'integer','nullable':False,'comparison':'exact'},
        'prob':{'type':'number','nullable':False,'comparison':'tolerant'},
        'root':{'type':'number','nullable':True,'comparison':'tolerant','null_policy':'same_as_reference'},
        'covered':{'type':'boolean','nullable':False,'comparison':'exact'},
        'class':{'type':'string','nullable':False,'comparison':'exact'}}}
    return d,s

def test_clean_passes(table_case):
    d,s=table_case;assert v.compare_table(d,d.copy(),s,TOL)['rows']==2

def test_reordered_keyed_rows_pass(table_case):
    d,s=table_case;assert v.compare_table(d,d.iloc[::-1],s,TOL)['rows']==2

def test_mismatch_with_nullable_key_remains_failure_and_serializes(table_case):
    d,s=table_case;d.loc[0,'country']=None;s['columns']['country']['nullable']=True;s['key_nullable']=['country']
    b=d.copy();b.loc[0,'prob']+=.01
    with pytest.raises(v.VerificationError) as exc:v.compare_table(d,b,s,TOL)
    record=v.error_record('fixture',exc.value)
    assert record['code']=='VALUES' and record['mismatches']==1
    assert record['expected']!=record['actual']
    json.dumps({'status':'FAIL','failures':[record]},allow_nan=False)

@pytest.mark.parametrize('mutation,code',[
    ('perturbed','VALUES'),('missing_row','ROWS'),('extra_row','ROWS'),('missing_column','COLUMNS'),('extra_column','COLUMNS'),('reordered_columns','COLUMNS'),('duplicate_key','DUPLICATE_KEY'),('unknown_key','ENUM'),('null_key','NULL'),('nan','NULL'),('inf','NONFINITE'),('negative_inf','NONFINITE'),('string_in_number','TYPE'),('integer_for_bool','TYPE'),('float_for_integer','TYPE'),('changed_class','VALUES'),('null_moved','NULL_PATTERN'),('null_filled','NULL_PATTERN'),('new_null_nullable','NULL_PATTERN')])
def test_mutations_rejected(table_case,mutation,code):
    d,s=table_case;b=d.copy()
    if mutation=='perturbed':b.loc[0,'prob']+=.01
    elif mutation=='missing_row':b=b.iloc[:1]
    elif mutation=='extra_row':b=pd.concat([b,b.iloc[:1]],ignore_index=True)
    elif mutation=='missing_column':b=b.drop(columns='year')
    elif mutation=='extra_column':b['extra']=1
    elif mutation=='reordered_columns':b=b[list(b)[::-1]]
    elif mutation=='duplicate_key':b.loc[1,'country']='CHL'
    elif mutation=='unknown_key':b.loc[1,'country']='XXX'
    elif mutation=='null_key':b.loc[1,'country']=None
    elif mutation=='nan':b.loc[0,'prob']=np.nan
    elif mutation=='inf':b.loc[0,'prob']=np.inf
    elif mutation=='negative_inf':b.loc[0,'prob']=-np.inf
    elif mutation=='string_in_number':b['prob']=b.prob.astype(str)
    elif mutation=='integer_for_bool':b['covered']=b.covered.astype(int)
    elif mutation=='float_for_integer':b['year']=b.year.astype(float)
    elif mutation=='changed_class':b.loc[0,'class']='robust'
    elif mutation=='null_moved':b['root']=[1.5,np.nan]
    elif mutation=='null_filled':b.loc[0,'root']=1.5
    elif mutation=='new_null_nullable':b.loc[1,'root']=np.nan
    with pytest.raises(v.VerificationError) as error:v.compare_table(d,b,s,TOL)
    assert error.value.code==code

def test_ordinal_permutation_rejected(table_case):
    d,s=table_case;s.update(row_matching='registered_row_order',primary_key=[],row_order_reason='Registered random draw order')
    with pytest.raises(v.VerificationError,match='Values differ'):v.compare_table(d,d.iloc[::-1],s,TOL)

def test_allowed_null_is_not_literal_placeholder(table_case):
    d,s=table_case;d.loc[0,'class']=None;s['columns']['class']['nullable']=True;b=d.copy();b.loc[0,'class']='<NULL>'
    with pytest.raises(v.VerificationError) as err:v.compare_table(d,b,s,TOL)
    assert err.value.code=='NULL_PATTERN'

def test_integer_above_float_precision_exact(table_case):
    d,s=table_case;d['year']=np.array([2**53+1,2**53+2],dtype=np.int64);b=d.copy();b.loc[0,'year']=2**53
    with pytest.raises(v.VerificationError) as err:v.compare_table(d,b,s,TOL)
    assert err.value.code=='VALUES'

def test_profile_controls_tolerance(table_case):
    # Illustrative fixture only; this does NOT calibrate the actual Tier B policy.
    d,s=table_case;b=d.copy();b.loc[0,'prob']+=.005
    with pytest.raises(v.VerificationError):v.compare_table(d,b,s,TOL)
    assert v.compare_table(d,b,s,{'atol':.01,'rtol':0})['rows']==2

def test_within_original_tolerance_passes(table_case):
    d,s=table_case;b=d.copy();b.loc[0,'prob']+=1e-12
    assert v.compare_table(d,b,s,TOL)['rows']==2

def test_duplicate_csv_header_rejected(tmp_path):
    p=tmp_path/'x.csv';p.write_text('country,country\nCHL,PER\n')
    with pytest.raises(v.VerificationError) as err:v.load_table(p,'csv')
    assert err.value.code=='DUPLICATE_COLUMN'

@pytest.mark.parametrize('change,code',[('key','ARRAY_KEYS'),('shape','ARRAY_SHAPE'),('dtype','ARRAY_TYPE'),('nan','NONFINITE'),('inf','NONFINITE'),('value','ARRAY_VALUES')])
def test_npz_corruption_rejected(tmp_path,change,code):
    a=np.array([[1.,2.],[3.,4.]]);b=a.copy();name='x'
    if change=='key':name='wrong'
    elif change=='shape':b=b[:1]
    elif change=='dtype':b=b.astype(np.float32)
    elif change=='nan':b[0,0]=np.nan
    elif change=='inf':b[0,0]=np.inf
    elif change=='value':b[0,0]=9.
    np.savez(tmp_path/'a.npz',x=a);np.savez(tmp_path/'b.npz',**{name:b})
    with np.load(tmp_path/'a.npz') as x,np.load(tmp_path/'b.npz') as y,pytest.raises(v.VerificationError) as err:
        v.compare_arrays(x,y,{'arrays':{'x':{'shape':[2,2],'dtype':'float64','nullable':False}}},TOL)
    assert err.value.code==code

@pytest.mark.parametrize('text,code',[('{"x":1,"x":2}','JSON_DUPLICATE'),('{"x":NaN}','NONFINITE'),('{"x":Infinity}','NONFINITE')])
def test_json_invalid_rejected(tmp_path,text,code):
    p=tmp_path/'x.json';p.write_text(text)
    with pytest.raises(v.VerificationError) as err:v.json_load(p)
    assert err.value.code==code

@pytest.mark.parametrize('value,code',[({'wrong':1},'JSON_KEYS'),({'x':'1'},'JSON_TYPE'),({'x':True},'JSON_TYPE')])
def test_json_schema_rejects(value,code):
    with pytest.raises(v.VerificationError) as err:v.validate_json(value,{'type':'object','properties':{'x':{'type':'integer'}}})
    assert err.value.code==code


def test_strict_json_diagnostic_reports_small_float_difference_and_stays_serializable():
    a=[{'context':{'q_bar':.5},'country':'PER'}];b=[{'context':{'q_bar':.5+1e-15},'country':'PER'}]
    with pytest.raises(v.VerificationError) as err:
        v.require(a==b,'JSON_VALUES','JSON values differ',differences=v.json_difference_samples(a,b))
    d=err.value.details['differences'];assert len(d)==1 and d[0]['pointer']=='$[0].context.q_bar'
    assert d[0]['expected']==.5 and d[0]['actual']>.5 and 0<d[0]['absolute_difference']<1e-14
    assert json.loads(json.dumps(v.error_record('contexts',err.value),allow_nan=False))['code']=='JSON_VALUES'

@pytest.fixture
def integrity_case(tmp_path):
    r=tmp_path/'package';r.mkdir();(r/'reference').mkdir();(r/'reference_inputs').mkdir();(r/'verification').mkdir();(r/'raw').mkdir()
    for n in ['verification/schemas.yaml','verification/tolerances.yaml','verification/reference_manifest.json','verification/document_cells.json','compare_results.py','verify_results.py','verify_documents.py','raw/frozen.csv','reference/x.csv']:
        (r/n).write_text('immutable '+n)
    source={'files':{p.relative_to(r).as_posix():v.sha(p) for p in r.rglob('*') if p.is_file()}}
    (r/'SOURCE_MANIFEST.json').write_text(json.dumps(source))
    m={'expected_artifact_count':1,'artifacts':[{'id':'x','reference':'reference/x.csv','generated':'results/x.csv','reference_sha256':v.sha(r/'reference/x.csv')}],'snapshot_sha256':{'raw/frozen.csv':v.sha(r/'raw/frozen.csv')}}
    return r,m,{'x':{}},source

def test_integrity_clean(integrity_case):
    r,m,s,_=integrity_case;assert v.check_integrity(r,m,s)['status']=='PASS'

@pytest.mark.parametrize('mutation,code',[('input_hash','SOURCE_HASH'),('input_missing','SOURCE_MISSING'),('reference_hash','SOURCE_HASH'),('reference_missing','SOURCE_MISSING'),('reference_extra','REFERENCE_INVENTORY'),('source_manifest_omission','SOURCE_MANIFEST'),('inventory_omission','INVENTORY'),('duplicate_mapping','INVENTORY'),('schema_missing','INVENTORY'),('snapshot_manifest_wrong','SNAPSHOT'),('outside_path','PATH')])
def test_integrity_mutations(integrity_case,mutation,code):
    r,m,s,source=integrity_case
    if mutation=='input_hash':(r/'raw/frozen.csv').write_text('changed')
    elif mutation=='input_missing':(r/'raw/frozen.csv').unlink()
    elif mutation=='reference_hash':(r/'reference/x.csv').write_text('changed')
    elif mutation=='reference_missing':(r/'reference/x.csv').unlink()
    elif mutation=='reference_extra':(r/'reference/extra.csv').write_text('extra')
    elif mutation=='source_manifest_omission':del source['files']['verification/schemas.yaml'];(r/'SOURCE_MANIFEST.json').write_text(json.dumps(source))
    elif mutation=='inventory_omission':m['artifacts']=[]
    elif mutation=='duplicate_mapping':m['artifacts']*=2;m['expected_artifact_count']=2
    elif mutation=='schema_missing':s={}
    elif mutation=='snapshot_manifest_wrong':m['snapshot_sha256']['raw/frozen.csv']='0'*64
    elif mutation=='outside_path':source['files']['../outside']='0'*64;(r/'SOURCE_MANIFEST.json').write_text(json.dumps(source))
    with pytest.raises(v.VerificationError) as err:v.check_integrity(r,m,s)
    assert err.value.code==code

def test_cli_nonzero_even_python_optimized(tmp_path):
    root=tmp_path/'empty';root.mkdir();report=tmp_path/'result.json'
    proc=subprocess.run([sys.executable,'-O',str(Path(v.__file__)),'--root',str(root),'--report',str(report)],capture_output=True,text=True)
    assert proc.returncode==1 and json.loads(report.read_text())['status']=='FAIL'

@pytest.mark.integration
def test_real_20_parameter_checks_reject_perturbation(tmp_path):
    from verify_documents import check_documents
    root=Path(v.__file__).resolve().parent;mini=tmp_path/'document_case'
    for relative in ['verification/document_cells.json','revision_jpm_v2/paso_07l/evidencia/MANUSCRITO_JPM_V2.docx','revision_jpm_v2/paso_07l/evidencia/SUPLEMENTO_TECNICO_JPM_V2.docx','revision_jpm_v2/paso_07d/evidencia/insumos/values.parquet']:
        p=mini/relative;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/relative,p)
    assert check_documents(mini)['cells_verified']==164
    p=mini/'revision_jpm_v2/paso_07d/evidencia/insumos/values.parquet';d=pd.read_parquet(p);d.loc[d.name.eq('LS_labor_share')&d.country_id.eq('CHL'),'baseline_value']+=.01;d.to_parquet(p,index=False)
    with pytest.raises(v.VerificationError) as err:check_documents(mini)
    assert err.value.code=='DOCUMENT_PARAMETER'

@pytest.mark.integration
def test_real_document_cell_change_rejected(tmp_path):
    from verify_documents import check_documents
    root=Path(v.__file__).resolve().parent;mini=tmp_path/'document_case'
    for relative in ['verification/document_cells.json','revision_jpm_v2/paso_07l/evidencia/MANUSCRITO_JPM_V2.docx','revision_jpm_v2/paso_07l/evidencia/SUPLEMENTO_TECNICO_JPM_V2.docx','revision_jpm_v2/paso_07d/evidencia/insumos/values.parquet']:
        p=mini/relative;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/relative,p)
    p=mini/'verification/document_cells.json';d=json.loads(p.read_text());d['cells'][0]['expected']='incorrect';p.write_text(json.dumps(d))
    with pytest.raises(v.VerificationError) as err:check_documents(mini)
    assert err.value.code=='DOCUMENT_VALUE'
