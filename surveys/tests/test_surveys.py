import json
from pathlib import Path
import pandas as pd
import pytest
import reproduce_surveys as s
import acquire_surveys as a

def test_changed_raw_input_rejected(tmp_path):
    p=tmp_path/'survey';p.write_bytes(b'changed')
    with pytest.raises(s.SurveyError,match='changed frozen input'):s.check_hash(p,'0'*64)

def test_changed_module_source_rejected(tmp_path,monkeypatch):
    p=tmp_path/'code.py';p.write_text('original')
    (tmp_path/'SOURCE_MANIFEST.json').write_text(json.dumps({'files':{'code.py':s.sha(p)}}))
    monkeypatch.setattr(s,'BASE',tmp_path);assert s.check_source_payload()==1
    p.write_text('changed')
    with pytest.raises(s.SurveyError,match='changed frozen input'):s.check_source_payload()

def test_existing_download_is_checked_without_network(tmp_path):
    p=tmp_path/'raw.dat';p.write_bytes(b'original')
    spec={'raw_relative':'raw.dat','raw_sha256':a.sha(p),'source_url':'https://invalid.example/unneeded'}
    assert a.acquire(spec,tmp_path)['status']=='EXISTING_HASH_VERIFIED'
    p.write_bytes(b'changed')
    with pytest.raises(RuntimeError,match='Existing file differs'):a.acquire(spec,tmp_path)
    assert p.read_bytes()==b'changed'

def test_partial_download_not_overwritten(tmp_path):
    (tmp_path/'raw.dat.part').write_bytes(b'partial')
    with pytest.raises(RuntimeError,match='partial download'):a.acquire({'raw_relative':'raw.dat','raw_sha256':'0'*64},tmp_path)

def example():
    frame=pd.DataFrame({'MIEPERHO':[2.,1.,3.],'FACTOR07':[1.,2.,1.],'INGHOG2D':[15.,12.,0.],'LINEA':[1.,1.,1.]})
    costs=pd.DataFrame([{'policy_variant_z':'pip_ppp_8_30_line','welfare_variable':'INGHOG2D','chi_gmi':1.,'theta_target':1.,'aggregate_gap_lcu_annual':35.,'cost_micro_lcu':35.,'baseline_gmi_version':'GMI_ideal_aggregate','difference_percent_vs_official':-65.,'micro_gmi_version':'ideal'}])
    official={'official_poverty_line_lcu_annual':10.,'official_ideal_cost_lcu':100.}
    return frame,costs,official

def test_annual_household_income_and_person_weights():
    frame,costs,official=example();out=s.weighted_oracle('PER',frame,costs,official)
    assert out[0]['independent_cost_lcu']==35.

def test_wrong_units_or_costs_rejected():
    frame,costs,official=example();costs.loc[0,'aggregate_gap_lcu_annual']=105.
    with pytest.raises(s.SurveyError,match='Independent aggregate gap'):s.weighted_oracle('PER',frame,costs,official)

def test_cost_difference_rejected():
    x=pd.DataFrame({'id':['a','b'],'cost':[1.,2.]});y=x.copy();y.loc[1,'cost']=2.01
    with pytest.raises(s.SurveyError,match='Numerical comparison'):s.compare_frames(x,y,'id','cost',{'rtol':1e-12,'atol':1e-10})

def test_duplicate_variants_rejected():
    x=pd.DataFrame({'id':['a','b'],'cost':[1.,2.]});y=x.copy();y.loc[1,'id']='a'
    with pytest.raises(s.SurveyError,match='row inventory'):s.compare_frames(x,y,'id','cost',{'rtol':1e-12,'atol':1e-10})

def test_missing_value_mask_rejected():
    x=pd.DataFrame({'id':['a','b'],'cost':[1.,2.]});y=x.copy();y.loc[1,'cost']=float('nan')
    with pytest.raises(s.SurveyError,match='Missing-value pattern'):s.compare_frames(x,y,'id','cost',{'rtol':1e-12,'atol':1e-10})
