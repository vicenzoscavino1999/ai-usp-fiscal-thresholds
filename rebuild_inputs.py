from pathlib import Path
import sys,importlib.util,json,shutil
import pandas as pd,duckdb
B=Path(__file__).resolve().parent;U=B/'upstream';R=B/'revision_jpm_v2';I=R/'paso_07d/evidencia/insumos'
I.mkdir(parents=True,exist_ok=True)
def module(name):
 spec=importlib.util.spec_from_file_location(name,U/'scripts'/(name+'.py'));m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
a=module('build_official_4c_anchors');a.build(U,'v1.0.1-official-4c')
module('materialize_official_v2_author_signature').build(U)
module('materialize_official_v3_measurement_uncertainty').materialize(U)
sys.path[:0]=[str(R/'paso_07d/candidato_iva_destino'),str(R/'paso_07d/candidato_iva_destino/src')]
spec=importlib.util.spec_from_file_location('original_mc_governance',I/'monte_carlo_original.py');mc=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mc;spec.loader.exec_module(mc)
mc.upsert_governance(U,mc.correlation_matrix_rows())
if '--build-only' in sys.argv:
 print('Raw snapshot and v1-v2-v3 calibration chain rebuilt successfully.');sys.exit(0)
con=duckdb.connect(str(U/'db/ai_usp_threshold.duckdb'),read_only=True)
tables={name:con.execute('SELECT * FROM '+name+' WHERE dataset_version = ?',['v1.0.1-official-4c']).fetchdf() for name in ['policy_cost','policy_admin_transition_cost','historical_capture_percentiles','fiscal_anchor','macro_anchor','digital_gap_anchor','grd_revenue_contrast']}
tables['frontier_benchmark_anchor']=con.execute("SELECT * FROM frontier_benchmark_anchor WHERE dataset_version=? AND benchmark_set_id='baseline_oecd_eurostat_ge10_2024' ORDER BY benchmark_country_id, year",['v1.0.1-official-4c']).fetchdf()
tables['values']=con.execute('SELECT * FROM value_assignment_table WHERE parameter_set_id=?',['baseline-official-v3']).fetchdf()
for name in ['input_audit_report','double_counting_audit']:tables[name]=con.execute('SELECT * FROM '+name+' WHERE parameter_set_id=?',['baseline-official-v3']).fetchdf()
debt=con.execute('SELECT * FROM debt_guardrail_anchor').fetchdf();con.close()
tables['wpp']=pd.read_parquet(U/'data/raw_snapshots/v1.0.1-official-4c/wpp/wpp_projections.parquet')
sys.path.insert(0,str(R/'paso_07d/candidato_iva_destino'));sys.path.insert(0,str(R/'paso_07d/candidato_iva_destino/src'))
from scripts.run_official_tier_a import normalize_keys
tables['values']=normalize_keys(tables['values']);assert len(tables['values'])==457
for name,df in tables.items():df.to_parquet(I/(name+'.parquet'),index=False)
debt.to_parquet(B/'snapshot/debt_guardrail_anchor.parquet',index=False)
debt.to_parquet(R/'paso_07d/costos_transicion_03/evidencia/debt_guardrail_anchor.parquet',index=False)
(B/'run_logs/INPUTS_RECONSTRUCTED.json').write_text(json.dumps({'status':'PASS','tables':{k:len(v) for k,v in tables.items()},'debt_rows':len(debt),'frozen_snapshot':'v1.0.1-official-4c','external_download':False},indent=2),encoding='utf-8')
print('Official inputs reconstructed from frozen raw snapshot; 457 parameters materialized.')
