from pathlib import Path
import sys,os,json,hashlib,importlib.util
import numpy as np,pandas as pd
R=Path(__file__).resolve().parents[3];S=R/'paso_04';E=S/'evidencia';B=R/'paso_07d/candidato_iva_destino';I=R/'paso_07d/evidencia/insumos'
sys.path[:0]=[str(B),str(B/'src')]
from scripts import run_official_tier_a as ta
spec=importlib.util.spec_from_file_location('original_mc_reproduction',I/'monte_carlo_original.py');mc=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mc;spec.loader.exec_module(mc)
REV='revision-jpm-v2-step04-sensitivity-20261114'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def load_inputs():
 x={p.stem:pd.read_parquet(p) for p in I.glob('*.parquet') if p.stem!='sorteos'}
 x['values']=ta.normalize_keys(x['values']);assert len(x['values'])==457;return x
def savejson(name,obj):
 (E/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=lambda z:z.item() if isinstance(z,np.generic) else str(z))+'\n',encoding='utf-8')
