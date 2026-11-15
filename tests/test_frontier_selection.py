"""Economic population, uniqueness and stable aggregation of the AI benchmark."""
from pathlib import Path
import importlib.util,sys,math
import numpy as np
import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('frontier_test_anchors',ROOT/'upstream/scripts/build_official_4c_anchors.py')
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a)

@pytest.fixture
def raw():
    geo={iso:code for code,iso in a.EUROSTAT_TO_ISO3.items()}
    return pd.DataFrame([{**a.FRONTIER_DIMENSIONS,'geo':geo[c],'time':2024,'value':float(i+1)} for i,c in enumerate(a.BENCHMARK_COUNTRIES)])

@pytest.fixture
def aip():
    return pd.DataFrame([dict(country_id=c,year=2023,aipi_total=.5+i/100) for i,c in enumerate(a.BENCHMARK_COUNTRIES)])

def test_other_indicators_denominators_sizes_and_years_do_not_enter(raw):
    distractors=[]
    for col,value in [('indic_is','E_AI_TX'),('size_emp','0-9'),('unit','PC_ENT_AI_TX'),('nace_r2','C'),('freq','Q'),('time',2025)]:
        copy=raw.copy();copy[col]=value;copy['value']=99.;distractors.append(copy)
    x=a.select_frontier_observations(pd.concat([raw,*distractors],ignore_index=True))
    assert len(x)==24 and x.benchmark_country_id.tolist()==sorted(a.BENCHMARK_COUNTRIES)
    assert math.fsum(x.adoption_proxy)/24==.125

def test_raw_order_invariance_and_whitespace(raw,aip):
    expected=a.select_frontier_observations(raw);expected_aip=a.benchmark_aipi(aip)
    for c in ['geo',*a.FRONTIER_DIMENSIONS]:raw[c]=' '+raw[c]+' '
    raw['time']=raw.time.astype(str)
    for seed in range(20):
        pd.testing.assert_frame_equal(a.select_frontier_observations(raw.sample(frac=1,random_state=seed)),expected)
        pd.testing.assert_frame_equal(a.benchmark_aipi(aip.sample(frac=1,random_state=seed)),expected_aip)

@pytest.mark.parametrize('column',['geo','time','value',*a.FRONTIER_DIMENSIONS])
def test_missing_dimension_rejected(raw,column):
    with pytest.raises(RuntimeError,match='Missing Eurostat'):a.select_frontier_observations(raw.drop(columns=column))

def test_missing_country_is_not_replaced(raw):
    with pytest.raises(RuntimeError,match='one cell per country'):a.select_frontier_observations(raw.iloc[1:])

@pytest.mark.parametrize('changed',[False,True])
def test_duplicates_are_rejected_even_if_values_agree(raw,changed):
    row=raw.iloc[[0]].copy()
    if changed:row['value']=90.
    with pytest.raises(RuntimeError,match='one cell per country'):a.select_frontier_observations(pd.concat([raw,row]))

@pytest.mark.parametrize('value',[np.nan,pd.NA,np.inf,-1.,101.,'bad'])
def test_invalid_percentage_rejected(raw,value):
    raw['value']=raw.value.astype(object);raw.loc[0,'value']=value
    with pytest.raises(RuntimeError,match='Invalid Eurostat benchmark percentage'):a.select_frontier_observations(raw)

@pytest.mark.parametrize('year',[np.nan,pd.NA,np.inf,2024.5,'bad'])
def test_invalid_year_rejected(raw,year):
    raw['time']=raw.time.astype(object);raw.loc[0,'time']=year
    with pytest.raises(RuntimeError,match='Invalid Eurostat benchmark year'):a.select_frontier_observations(raw)

def test_aipi_uses_latest_up_to_anchor_and_rejects_ties(aip):
    future=aip.copy();future['year']=2025;future['aipi_total']=.99
    pd.testing.assert_frame_equal(a.benchmark_aipi(pd.concat([aip,future])),a.benchmark_aipi(aip))
    with pytest.raises(RuntimeError,match='one latest cell'):a.benchmark_aipi(pd.concat([aip,aip.iloc[[0]]]))
    with pytest.raises(RuntimeError,match='one latest cell'):a.benchmark_aipi(aip.iloc[1:])

@pytest.mark.parametrize('value',[np.nan,pd.NA,np.inf,-.01,1.01,'bad'])
def test_invalid_aipi_rejected(aip,value):
    aip['aipi_total']=aip.aipi_total.astype(object);aip.loc[0,'aipi_total']=value
    with pytest.raises(RuntimeError,match='Invalid AIPI benchmark score'):a.benchmark_aipi(aip)

def test_frozen_snapshot_population_and_known_country_cells():
    p=ROOT/'upstream/data/raw_snapshots/v1.0.1-official-4c'
    x=a.select_frontier_observations(pd.read_parquet(p/'frontier/frontier_benchmark.parquet')).set_index('benchmark_country_id')
    assert len(x)==24 and x.year.eq(2024).all()
    for country,percent in [('DNK',27.58),('FRA',9.91),('TUR',4.42),('AUT',20.27)]:
        assert x.loc[country,'adoption_proxy']==percent/100
    assert math.isclose(math.fsum(x.adoption_proxy)/24,.1517625,abs_tol=1e-16,rel_tol=0)
    assert len(a.benchmark_aipi(pd.read_parquet(p/'imf_aipi/aipi.parquet')))==24

@pytest.fixture(params=['candidato_iva_destino/scripts/run_official_monte_carlo.py','evidencia/insumos/monte_carlo_original.py'])
def mc(request):
    base=ROOT/'revision_jpm_v2/paso_07d'
    sys.path[:0]=[str(base/'candidato_iva_destino'),str(base/'candidato_iva_destino/src')]
    name='frontier_mc_'+str(request.param.startswith('evidencia'))
    spec=importlib.util.spec_from_file_location(name,base/request.param);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module

@pytest.mark.parametrize('vary',[False,True])
def test_all_country_draw_outputs_are_exact_under_frontier_permutations(mc,vary):
    values=mc.normalize_keys(pd.read_parquet(ROOT/'reference_inputs/values.parquet'))
    lookup=mc.value_lookup(values)
    class Central:
        size=3
        def array(self,name,**scope):
            if vary and name=='gamma_translation':return np.array([.9,1.,1.1])
            if vary and name=='epsilon':return np.array([1e-9,1e-8,1e-7])
            scope.pop('force_draw',None)
            return np.full(3,lookup(name,**scope))
    sampler=Central();p=ROOT/'upstream/data/raw_snapshots/v1.0.1-official-4c/frontier/frontier_benchmark.parquet'
    frontier=a.select_frontier_observations(pd.read_parquet(p))
    def run(x):return mc.build_country_scenario_draws(sampler,{'frontier_benchmark_anchor':x},'CHL','mid',sampler.array('E_prod_frontier'))
    expected=run(frontier)
    for seed in range(20):
        actual=run(frontier.sample(frac=1,random_state=seed))
        assert actual.keys()==expected.keys()
        for key in expected:np.testing.assert_array_equal(actual[key],expected[key],err_msg=key)
    with pytest.raises(mc.OfficialRunError,match='one observation'):run(pd.concat([frontier,frontier.iloc[[0]]]))
    invalid=frontier.copy();invalid.loc[0,'adoption_proxy']=np.nan
    with pytest.raises(mc.OfficialRunError,match='Invalid frontier'):run(invalid)
