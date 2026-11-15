"""Complete-run guards, including independently rebuilt anchor metadata."""
from pathlib import Path
import json,os,shutil
import pandas as pd
import pytest
import verify_complete as v
from core_identity import semantic_identity,check_core_inputs

@pytest.fixture
def mini(tmp_path):
    source=os.environ.get('JPM_FULL_TEST_ROOT')
    if not source:pytest.skip('Requires completed full reproduction')
    source=Path(source)
    for sub in ['surveys','survey_results']:
        shutil.copytree(source/sub,tmp_path/sub,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
    contract=v.read(source/'surveys/INPUT_CONTRACT.json')
    for n in contract['core_inputs']:
        p=tmp_path/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/n,p)
    (tmp_path/'run_logs').mkdir()
    for n in ['FULL_PREFLIGHT.json','FULL_EXECUTION.json','execution.json']:
        shutil.copy2(source/'run_logs'/n,tmp_path/'run_logs'/n)
    shutil.copy2(source/'SOURCE_MANIFEST.json',tmp_path/'SOURCE_MANIFEST.json')
    return tmp_path

def test_complete_survey_and_freshness_pass(mini):
    assert v.check_survey_outputs(mini)['tables_passed']==4
    assert v.check_execution(mini)['clean_start']

def test_false_pass_without_raw_reconstruction_rejected(mini):
    p=mini/'survey_results/SURVEY_REPRODUCTION.json';d=v.read(p);d['microdata_reexecuted']=False;p.write_text(json.dumps(d),encoding='utf-8')
    with pytest.raises(v.CompleteError,match='raw survey reconstruction'):v.check_survey_outputs(mini)

def test_missing_country_rejected(mini):
    p=mini/'survey_results/SURVEY_REPRODUCTION.json';d=v.read(p);d['samples']=d['samples'][:1];p.write_text(json.dumps(d),encoding='utf-8')
    with pytest.raises(v.CompleteError,match='Missing survey'):v.check_survey_outputs(mini)

def test_altered_survey_cost_rejected(mini):
    p=mini/'survey_results/gmimicro_cost_comparison_baseline-official-v3.csv';d=pd.read_csv(p);d.loc[0,'cost_micro_lcu']*=1.01;d.to_csv(p,index=False)
    with pytest.raises(RuntimeError,match='Numerical comparison'):v.check_survey_outputs(mini)

def test_prior_outputs_cannot_be_called_fresh(mini):
    p=mini/'run_logs/FULL_PREFLIGHT.json';d=v.read(p);d['outputs_preloaded']=True;p.write_text(json.dumps(d),encoding='utf-8')
    with pytest.raises(v.CompleteError,match='clean sources'):v.check_execution(mini)

def test_incomplete_core_execution_rejected(mini):
    p=mini/'run_logs/execution.json';d=v.read(p);p.write_text(json.dumps(d[:-1]),encoding='utf-8')
    with pytest.raises(v.CompleteError,match='Core execution incomplete'):v.check_execution(mini)

def test_build_timestamp_changes_preserve_scientific_identity(tmp_path):
    p=tmp_path/'anchor.parquet';df=pd.DataFrame({'country_id':['PER'],'value':[.123],'created_at':['old'],'build_id':['old']});df.to_parquet(p,index=False)
    expected=semantic_identity(p);df['created_at']='new';df['build_id']='new';df.to_parquet(p,index=False)
    assert semantic_identity(p)==expected

def test_scientific_anchor_change_is_rejected(tmp_path):
    p=tmp_path/'anchor.parquet';df=pd.DataFrame({'country_id':['PER'],'value':[.123],'created_at':['old'],'build_id':['old']});df.to_parquet(p,index=False)
    contract={'core_inputs':{'anchor.parquet':'historical'},'core_semantic_inputs':{'anchor.parquet':semantic_identity(p)}}
    df['value']=.124;df.to_parquet(p,index=False)
    with pytest.raises(ValueError,match='values/schema differ'):check_core_inputs(tmp_path,contract)
