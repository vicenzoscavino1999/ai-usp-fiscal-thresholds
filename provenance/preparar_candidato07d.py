from pathlib import Path
import sys, os, shutil, hashlib, json, difflib
sys.dont_write_bytecode=True
R=Path(r'D:\Copia_Laptop_D\paper de economia\revision_jpm_v2')
S=R/'paso_07d'; E=S/'evidencia'; C=S/'candidato_iva_destino'
B=R/'paso_03/candidato_corregido/ai-usp-fiscal-thresholds'
I=E/'insumos'; I.mkdir(exist_ok=True)
assert not C.exists(), 'El candidato ya existe; revisar antes de reemplazar.'
for folder in ['src/ai_usp','scripts']:
    (C/folder).mkdir(parents=True,exist_ok=True)
    paths=(B/folder).glob('*.py') if folder=='src/ai_usp' else [B/folder/n for n in ['__init__.py','run_official_tier_a.py','run_official_monte_carlo.py']]
    for p in paths:
        if p.exists(): shutil.copy2(p,C/folder/p.name)
for name in ['distancias.csv','canales.csv','valores_oficiales.csv','sorteos.parquet']:
    shutil.copy2(R/'paso_07c/evidencia/insumos'/name,I/name)
shutil.copy2(B/'scripts/run_official_monte_carlo.py',I/'monte_carlo_original.py')
shutil.copy2(B/'src/ai_usp/labor_share.py',I/'labor_share_original.py')
os.environ['JPM_STEP04_OUTPUT_DIR']=str(E/'scratch_loader')
sys.path.insert(0,str(R/'paso_04/evidencia/scripts'))
from paso04_common import load_inputs
x=load_inputs()
for name,df in x.items(): df.to_parquet(I/(name+'.parquet'),index=False)
changes=[
 ('src/ai_usp/labor_share.py','(1.0 - exempt_c) * (1.0 - m_m) * max(0.0, consumption_base)', '(1.0 - exempt_c) * max(0.0, consumption_base)'),
 ('scripts/run_official_monte_carlo.py','(1.0 - exempt_c_r) * (1.0 - m_m) * np.maximum(0.0, consumption_base)', '(1.0 - exempt_c_r) * np.maximum(0.0, consumption_base)')]
diffs=[]
for rel,old,new in changes:
    p=C/rel; before=p.read_text(encoding='utf-8'); assert before.count(old)==1,rel
    after=before.replace(old,new)
    note='# Paso 07d: VAT follows final consumption at destination, including imports.\n'
    target='    delta_consumption_taxable_gdp0 = (' if 'labor_share' in rel else '    delta_consumption_taxable = '
    after=after.replace(target,'    '+note+target)
    p.write_text(after,encoding='utf-8')
    diffs.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='anterior/'+rel,tofile='candidato/'+rel))
(S/'CAMBIOS_IVA.patch').write_text(''.join(diffs),encoding='utf-8')
records=[]
for p in sorted(list(I.glob('*'))+list(C.rglob('*.py'))):
    if p.is_file(): records.append({'path':str(p.relative_to(S)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size})
(E/'MANIFIESTO_INSUMOS_CANDIDATO.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'files':len(records),'candidate':str(C),'snapshots':list(x)},ensure_ascii=False))
