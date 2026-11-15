from pathlib import Path
import sys, os, hashlib, json
sys.dont_write_bytecode=True
P=Path(r'D:\Copia_Laptop_D\paper de economia'); R=P/'revision_jpm_v2'
S=Path(os.environ.get('JPM_STEP04_OUTPUT_DIR',str(R/'paso_04')));E=S/'evidencia';E.mkdir(parents=True,exist_ok=True)
B=R/'paso_03/candidato_corregido/ai-usp-fiscal-thresholds'
sys.path.insert(0,str(B));sys.path.insert(0,str(B/'src'))
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[key]='1'
import numpy as np,pandas as pd,duckdb
from scripts import run_official_monte_carlo as mc
from scripts import run_official_tier_a as ta
REV='revision-jpm-v2-step04-sensitivity-20261114'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def savejson(name,obj):
    (E/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=lambda z:z.item() if isinstance(z,np.generic) else str(z))+'\n',encoding='utf-8')
def load_inputs():
    con=duckdb.connect(str(B/'db/ai_usp_threshold.duckdb'),read_only=True)
    tables={name:con.execute('SELECT * FROM '+name+' WHERE dataset_version = ?',[ta.DATASET_VERSION]).fetchdf() for name in ['policy_cost','policy_admin_transition_cost','historical_capture_percentiles','fiscal_anchor','macro_anchor','digital_gap_anchor','grd_revenue_contrast']}
    tables['frontier_benchmark_anchor']=con.execute("SELECT * FROM frontier_benchmark_anchor WHERE dataset_version=? AND benchmark_set_id='baseline_oecd_eurostat_ge10_2024'",[ta.DATASET_VERSION]).fetchdf()
    tables['values']=ta.normalize_keys(con.execute('SELECT * FROM value_assignment_table WHERE parameter_set_id=?',[mc.PARAMETER_SET_ID]).fetchdf())
    for name in ['input_audit_report','double_counting_audit']:
        tables[name]=con.execute('SELECT * FROM '+name+' WHERE parameter_set_id=?',[mc.PARAMETER_SET_ID]).fetchdf()
    con.close()
    tables['wpp']=pd.read_parquet(B/'data/raw_snapshots/v1.0.1-official-4c/wpp/wpp_projections.parquet')
    assert len(tables['values'])==457
    return tables
def base_results():return pd.read_csv(R/'paso_03/resultados_auditados_v2/fiscal_space_result.csv').query('xi==0.1').reset_index(drop=True)
def classify(flow,cost,spb):
    return np.where(flow<(cost-1e-12),'no_cruza',np.where(flow>=(1.1*cost+spb-1e-12),'cruza_con_deuda','cruza_sin_deuda'))

if __name__=='__main__':
    x=load_inputs();g=x['grd_revenue_contrast'];print('GRD contrast',list(g.columns));print(g[g.country_id.eq('CHL')].tail(4).to_string(index=False))
    raw=pd.read_parquet(B/'data/raw_snapshots/v1.0.1-official-4c/grd/grd_revenue.parquet')
    z=raw[raw.country_id.eq('CHL')]
    print(z.groupby(['government_level','unit']).agg(n=('year','size'),first=('year','min'),last=('year','max')).to_string())
    cols=['year','government_level','unit','tax_revenue_including_sc','total_revenue_excluding_grants_inc_sc','total_resource_revenue','non_resource_tax_revenue_including_sc','total_non_resource_revenue_inc_sc','source_sheet']
    print(z[z.government_level.eq('general_government')&z.year.ge(2018)][cols].to_string(index=False))
