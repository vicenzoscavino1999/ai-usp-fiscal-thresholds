"""Use the original three input functions, without the old engine/report runner."""
from pathlib import Path
from typing import Any
from types import SimpleNamespace
from datetime import datetime,timezone
import ast,json,hashlib
import pandas as pd
B=Path(__file__).resolve().parent;R=B/'revision_jpm_v2';U=B/'upstream';source=U/'scripts/run_ls_raw_robustness_extension.py'
tree=ast.parse(source.read_text(encoding='utf-8'));names={'ExtensionError','sha256_file','load_latest_labor_share','build_parameter_set'}
selected=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names];assert len(selected)==4
scope=dict(Path=Path,Any=Any,datetime=datetime,timezone=timezone,json=json,hashlib=hashlib,pd=pd,mc=SimpleNamespace(COUNTRIES=['PER','CHL','COL','MEX']),BASELINE_PARAMETER_SET_ID='baseline-official-v3',PARAMETER_SET_ID='robustness-lsraw-v1',SNAPSHOT_DIR=U/'data/raw_snapshots/robustness-lsraw-v1/un_sna_labor_share',SNAPSHOT_MANIFEST=U/'reproducibility/snapshot/dataset_manifest_robustness-lsraw-v1.json',__file__=str(source))
exec(compile(ast.Module(body=selected,type_ignores=[]),str(source),'exec'),scope)
latest,meta=scope['load_latest_labor_share']();I=R/'paso_07d/evidencia/insumos'
values,changes=scope['build_parameter_set']({'values':pd.read_parquet(I/'values.parquet'),'fiscal_anchor':pd.read_parquet(I/'fiscal_anchor.parquet')},latest,meta)
target=R/'paso_03/candidato_corregido/ai-usp-fiscal-thresholds/reports/value_assignment_changes_baseline-official-v3_to_robustness-lsraw-v1.csv';target.parent.mkdir(parents=True,exist_ok=True);changes.to_csv(target,index=False)
assert len(changes)==24
print('24 labour and tax-chain calibration contrasts rebuilt from the hash-checked UN SNA snapshot.')
