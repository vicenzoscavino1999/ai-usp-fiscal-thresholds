"""Reject demographic ambiguity before materializing the national calibration."""
from pathlib import Path
import importlib.util,sys
import numpy as np
import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('anchors_for_selection_tests',ROOT/'upstream/scripts/build_official_4c_anchors.py')
anchors=importlib.util.module_from_spec(spec);sys.modules[spec.name]=anchors;spec.loader.exec_module(anchors)

@pytest.fixture
def cells():
    rows=[]
    for year,value in [(2023,70.),(2024,71.373),(2025,99.)]:
        for sex,age,offset in [('SEX_T','AGE_AGGREGATE_YGE15',0),('SEX_F','AGE_AGGREGATE_YGE15',4),('SEX_T','AGE_5YRBANDS_Y40-44',-4),('SEX_T','AGE_YTHADULT_YGE15',0)]:
            rows.append(dict(country_id='PER',indicator_code='EMP_NIFL_SEX_AGE_RT',sex=sex,age_group=age,year=year,value=value+offset))
    return pd.DataFrame(rows)

def test_selects_total_before_latest_year_and_ignores_other_demographics(cells):
    row=anchors.select_informality_observation(cells,'PER')
    assert row.year==2024 and row.value==71.373 and row.sex=='SEX_T' and row.age_group=='AGE_AGGREGATE_YGE15'
    assert anchors.select_informality_observation(cells,'PER',2023).value==70.

def test_selection_is_independent_of_tied_row_order(cells):
    for seed in range(20):assert anchors.select_informality_observation(cells.sample(frac=1,random_state=seed),'PER').value==71.373

def test_whitespace_and_numeric_year_text_are_normalized(cells):
    for name in ['country_id','indicator_code','sex','age_group']:cells[name]=' '+cells[name]+' '
    cells['year']=cells.year.astype(str)
    assert anchors.select_informality_observation(cells,'PER').value==71.373

@pytest.mark.parametrize('dimension',['sex','age_group','country_id','indicator_code'])
def test_missing_required_demographic_cell_is_not_replaced(cells,dimension):
    cells[dimension]='unavailable'
    with pytest.raises(RuntimeError,match='Missing ILOSTAT both-sexes'):anchors.select_informality_observation(cells,'PER')

@pytest.mark.parametrize('value',[71.373,80.])
def test_duplicate_latest_cells_are_rejected_even_if_values_agree(cells,value):
    row=cells[cells.year.eq(2024)&cells.sex.eq('SEX_T')&cells.age_group.eq('AGE_AGGREGATE_YGE15')].copy();row['value']=value
    with pytest.raises(RuntimeError,match='Ambiguous ILOSTAT'):anchors.select_informality_observation(pd.concat([cells,row]),'PER')

@pytest.mark.parametrize('value',[np.nan,np.inf,-1.,101.,'invalid'])
def test_invalid_percentages_are_rejected(cells,value):
    cells['value']=cells.value.astype(object)
    cells.loc[cells.year.eq(2024)&cells.sex.eq('SEX_T')&cells.age_group.eq('AGE_AGGREGATE_YGE15'),'value']=value
    with pytest.raises(RuntimeError,match='Invalid ILOSTAT informality percentage'):anchors.select_informality_observation(cells,'PER')

def test_missing_age_dimension_is_rejected(cells):
    with pytest.raises(RuntimeError,match='Missing ILOSTAT dimensions'):anchors.select_informality_observation(cells.drop(columns='age_group'),'PER')

@pytest.mark.parametrize('year',['bad',2024.5,np.inf])
def test_invalid_year_is_rejected(cells,year):
    cells['year']=cells.year.astype(object);cells.loc[0,'year']=year
    with pytest.raises(RuntimeError,match='Invalid ILOSTAT observation year'):anchors.select_informality_observation(cells,'PER')

@pytest.mark.parametrize('country,value',[('PER',71.373),('CHL',27.458),('COL',56.143),('MEX',56.407)])
def test_frozen_snapshot_has_one_explicit_total_cell(country,value):
    frame=pd.read_parquet(ROOT/'upstream/data/raw_snapshots/v1.0.1-official-4c/ilostat/ilostat_labor.parquet')
    row=anchors.select_informality_observation(frame,country)
    assert row.year==2024 and row.value==value
