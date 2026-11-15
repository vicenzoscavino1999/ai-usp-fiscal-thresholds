"""Identity of regenerated anchors: ignore only declared build-time metadata."""
import hashlib,json,math
import numpy as np
import pandas as pd
IGNORED=('build_id','created_at')
def semantic_identity(path):
    frame=pd.read_parquet(path);columns=sorted(frame.columns)
    excluded=[c for c in IGNORED if c in columns];data_columns=[c for c in columns if c not in excluded]
    def scalar(x):
        if pd.isna(x):return None
        if isinstance(x,np.generic):x=x.item()
        if isinstance(x,float) and not math.isfinite(x):raise ValueError('Nonfinite anchor value')
        if isinstance(x,(pd.Timestamp,)):return x.isoformat()
        return x
    records=[json.dumps([scalar(x) for x in row],ensure_ascii=False,separators=(',',':'),allow_nan=False) for row in frame[data_columns].itertuples(index=False,name=None)]
    payload={'all_columns':columns,'value_columns':data_columns,'rows':sorted(records)}
    encoded=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
    return {'sha256':hashlib.sha256(encoded).hexdigest(),'rows':len(frame),'columns':len(columns),'excluded_build_metadata':excluded,'value_columns':data_columns}
def check_core_inputs(core_root,contract):
    results={}
    for name,expected in contract['core_semantic_inputs'].items():
        actual=semantic_identity(core_root/name)
        if actual!=expected:raise ValueError('Regenerated anchor values/schema differ: '+name)
        results[name]=actual
    if set(results)!=set(contract['core_inputs']):raise ValueError('Missing anchor identity')
    return results
