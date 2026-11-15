"""Integration fault injection on a disposable copy of a completed reproduction.

Set JPM_INTEGRATION_TEST_ROOT to a completed package. Normal unit runs skip this
module; no source, expected value or generated output in that package is edited.
"""
from pathlib import Path
import os,json,shutil,sys,subprocess
import pandas as pd
import pytest
from verify_extensions import verify

@pytest.fixture(scope='module')
def completed(tmp_path_factory):
    source=os.environ.get('JPM_INTEGRATION_TEST_ROOT')
    if not source:pytest.skip('Requires a completed reconstruction via JPM_INTEGRATION_TEST_ROOT')
    dest=tmp_path_factory.mktemp('integrated')/'copy'
    shutil.copytree(source,dest,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
    return dest

def test_untouched_integrated_extensions_pass(completed):
    result=verify(completed)
    assert result['status']=='PASS',result['failures']
    assert result['semantic']['scientific_outcomes']['D_LOW_EXPOSURE']=='FAIL_RETAINED'

@pytest.mark.parametrize('mutation,code',[
    ('missing','OUTPUT_INVENTORY'),('duplicate','DUPLICATE_KEY'),('count','VALUES'),
    ('frequency','VALUES'),('null','NULL'),('diagnostic','JSON_VALUE'),('hypothesis','NULL_PATTERN'),
    ('source','SOURCE_HASH'),('extra','OUTPUT_INVENTORY'),('findings','SCIENTIFIC_CONSISTENCY'),('provenance','SCIENTIFIC_CONSISTENCY')])
def test_corruption_is_rejected(completed,mutation,code):
    path=completed/'extensions/stress/resultados/MC_ESTRES_20261114.csv'
    if mutation=='diagnostic':path=completed/'extensions/convergence/resultados/ANALISIS_CONTROL_EXPOSICION.json'
    if mutation=='hypothesis':path=completed/'extensions/scope/resultados/ADJUDICACION_H1_H5_V2.csv'
    if mutation=='source':path=completed/'extensions/stress/scripts/ejecutar_estres_dependencia_v2.py'
    if mutation=='findings':path=completed/'extensions/scope/resultados/SCIENTIFIC_FINDINGS.json'
    if mutation=='provenance':path=completed/'extensions/stress/resultados/FUNCIONES_REUTILIZADAS.json'
    original=path.read_bytes();extra=completed/'extensions/stress/resultados/UNREGISTERED.csv'
    try:
        if mutation=='missing':path.unlink()
        elif mutation=='extra':extra.write_text('unexpected\n1\n')
        elif mutation=='source':path.write_bytes(original+b'\n# unexpected edit\n')
        elif mutation=='diagnostic':
            x=json.loads(original);x['zero_crossing_expectation_status']='PASS';path.write_text(json.dumps(x),encoding='utf-8')
        elif mutation=='findings':
            x=json.loads(original);x['hypotheses']['H5']='HOLDS';path.write_text(json.dumps(x),encoding='utf-8')
        elif mutation=='provenance':
            x=json.loads(original);x['functions']=['wrong_function'];path.write_text(json.dumps(x),encoding='utf-8')
        else:
            x=pd.read_csv(path)
            if mutation=='duplicate':x.iloc[1]=x.iloc[0]
            if mutation=='count':x.loc[0,'recurring_author_crossings']+=1
            if mutation=='frequency':x.loc[0,'recurring_author_frequency']+=.01
            if mutation=='null':x.loc[0,'Fmax_p50']=float('nan')
            if mutation=='hypothesis':x.loc[x.hypothesis_id=='H5','v2_verdict']='HOLDS'
            x.to_csv(path,index=False)
        result=verify(completed)
        assert result['status']=='FAIL'
        assert code in [x['code'] for x in result['failures']],result['failures']
    finally:
        path.write_bytes(original)
        if extra.exists():extra.unlink()

def test_expected_results_blocked_during_science(completed):
    ref=next((completed/'extension_reference').glob('*/*.csv'))
    script=completed/'probe_reference_guard.py';script.write_text('from pathlib import Path\nPath('+repr(str(ref))+').read_text()\n')
    try:
        run=subprocess.run([sys.executable,str(completed/'execute_isolated.py'),script.name],cwd=completed,env={**os.environ,'JPM_COMPARE':'0'},capture_output=True,text=True)
        assert run.returncode!=0 and 'Expected results cannot be scientific inputs' in run.stderr
    finally:
        script.unlink()
        log=completed/'run_logs/probe_reference_guard_access.json'
        if log.exists():log.unlink()

def test_full_cli_pass_and_failure_exit_codes(completed):
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
    run=subprocess.run([sys.executable,str(completed/'verify_all.py')],cwd=completed,env=env,capture_output=True,text=True)
    assert run.returncode==0,run.stdout+run.stderr
    path=completed/'extensions/scope/resultados/SCIENTIFIC_FINDINGS.json';original=path.read_bytes()
    try:
        x=json.loads(original);x['D_LOW_EXPOSURE']='PASS';path.write_text(json.dumps(x),encoding='utf-8')
        bad=subprocess.run([sys.executable,str(completed/'verify_all.py')],cwd=completed,env=env,capture_output=True,text=True)
        assert bad.returncode!=0
        assert json.loads((completed/'run_logs/COMPARISON_FULL.json').read_text())['status']=='FAIL'
    finally:path.write_bytes(original)
