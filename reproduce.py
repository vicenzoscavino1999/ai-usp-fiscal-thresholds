from pathlib import Path
import subprocess,sys,os,json,time,hashlib,platform
from datetime import datetime,timezone
B=Path(__file__).resolve().parent;L=B/'run_logs';L.mkdir(exist_ok=True)
env=os.environ.copy();env.update(NPY_DISABLE_CPU_FEATURES='X86_V4',PYTHONHASHSEED='0',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',PYTHONUTF8='1',MPLCONFIGDIR=str(L/'matplotlib'),TEMP=str(B/'tmp'),TMP=str(B/'tmp'))
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:env[k]='1'
(B/'tmp').mkdir(exist_ok=True)
for rel in ['snapshot','publication','paso_04/evidencia','paso_07d/evidencia/insumos','paso_07d/resultados_candidatos','paso_07d/conciliacion_fiscal_02/resultados','paso_07d/conciliacion_fiscal_02/evidencia','paso_07d/costos_transicion_03/resultados','paso_07d/costos_transicion_03/evidencia','paso_07e/resultados','paso_07e/evidencia/inputs','paso_07e/evidencia/scripts/inputs','paso_07g/evidencia','paso_07g/bloque_1_matematica','paso_07g/bloque_2_descomposicion','paso_07g/bloque_3_transicion','paso_07h/evidencia','paso_07h/resultados','paso_07l/resultados']:
 (B/rel if rel in ['snapshot','publication'] else B/'revision_jpm_v2'/rel).mkdir(parents=True,exist_ok=True)
if (B/'upstream').exists():(B/'upstream/metadata').mkdir(exist_ok=True)
stages=[
 'rebuild_inputs.py','rebuild_labor.py','revision_jpm_v2/paso_04/evidencia/scripts/auditar_historia_paso04.py',
 'revision_jpm_v2/paso_04/evidencia/scripts/ejecutar_captura_paso04.py','bootstrap.py',
 'revision_jpm_v2/paso_07d/conciliacion_fiscal_02/scripts/ejecutar_conciliacion.py',
 'revision_jpm_v2/paso_07d/conciliacion_fiscal_02/scripts/verificar_modelo.py',
 'revision_jpm_v2/paso_07d/conciliacion_fiscal_02/scripts/examinar_anclas.py',
 'revision_jpm_v2/paso_07d/conciliacion_fiscal_02/scripts/verificar_resultados.py',
 'revision_jpm_v2/paso_07d/costos_transicion_03/scripts/ejecutar_costos03.py',
 'revision_jpm_v2/paso_07d/costos_transicion_03/scripts/probar_modelo03.py',
 'revision_jpm_v2/paso_07d/costos_transicion_03/scripts/verificar_resultados03.py','handoffs.py',
 'revision_jpm_v2/paso_07e/evidencia/scripts/actualizar_comparadores.py',
 'revision_jpm_v2/paso_07g/scripts/revisar_matematica.py',
 'revision_jpm_v2/paso_07g/scripts/descomponer_resultados.py',
 'revision_jpm_v2/paso_07g/scripts/sensibilidad_transicion.py',
 'revision_jpm_v2/paso_07g/scripts/verificar_transicion.py',
 'revision_jpm_v2/paso_07h/scripts/diagnosticar_calibraciones.py',
 'revision_jpm_v2/paso_07h/scripts/verificar_y_extender.py',
 'revision_jpm_v2/paso_07h/scripts/resumir_decisiones.py',
 'revision_jpm_v2/paso_07l/scripts/auditar_nucleo.py',
 'revision_jpm_v2/paso_07l/scripts/auditar_financiacion.py',
 'revision_jpm_v2/paso_07l/scripts/auditar_resultados.py',
 'revision_jpm_v2/paso_07l/scripts/auditar_complementos.py',
 'revision_jpm_v2/paso_07d/costos_transicion_03/scripts/figura_resumen03.py',
 'rebuild_figure.py','compare_results.py']
stages += ['extensions/convergence/scripts/convergencia_v2.py', 'extensions/convergence/scripts/diagnosticos_v2.py', 'extensions/convergence/scripts/verificar_convergencia_v2.py', 'extensions/paired/scripts/ejecutar_emparejados_v2.py', 'extensions/paired/scripts/verificar_emparejados_v2.py', 'extensions/stress/scripts/ejecutar_estres_dependencia_v2.py', 'extensions/stress/scripts/verificar_estres_dependencia_v2.py', 'extensions/stress/scripts/resumir_estres_v2.py', 'extensions/scope/scripts/derivar_alcance_v2.py', 'extensions/scope/scripts/registrar_alcance_integrado.py', 'verify_all.py']
for group in ['convergence','paired','stress','scope']:(B/'extensions'/group/'resultados').mkdir(parents=True,exist_ok=True)
start=int(sys.argv[1]) if len(sys.argv)>1 else 0
if start==0 and (B/'SOURCE_MANIFEST.json').exists():
 manifest=json.loads((B/'SOURCE_MANIFEST.json').read_text())
 for rel,h in manifest['files'].items():assert hashlib.sha256((B/rel).read_bytes()).hexdigest()==h,rel
 assert not list((B/'extensions').glob('*/resultados/*')),'Extension outputs must be reconstructed in a fresh extraction.'
 assert not (B/'upstream/db/ai_usp_threshold.duckdb').exists(),'Use a fresh extraction for a complete run.'
 assert not list((B/'revision_jpm_v2/paso_07d/evidencia/insumos').glob('*.parquet')),'Model inputs must be reconstructed, not preloaded.'
 (L/'PREFLIGHT.json').write_text(json.dumps({'status':'PASS','source_files_verified':len(manifest['files']),'model_inputs_preloaded':False,'database_preloaded':False,'python':sys.version,'platform':platform.platform(),'prefix':sys.prefix,'utc':datetime.now(timezone.utc).isoformat()},indent=2),encoding='utf-8')
records=json.loads((L/'execution.json').read_text()) if (L/'execution.json').exists() else []
for i,stage in enumerate(stages):
 if i<start:continue
 t=time.perf_counter();print(f'START {i}: {stage}',flush=True);lf=L/f'{i:02}_{Path(stage).stem}_{len(records):02}.log'
 stageenv={**env,'JPM_COMPARE':'1' if stage in ['compare_results.py','verify_all.py'] else '0'}
 with lf.open('w',encoding='utf-8') as f:p=subprocess.run([sys.executable,'-X','utf8',str(B/'execute_isolated.py'),stage],cwd=B,env=stageenv,stdout=f,stderr=subprocess.STDOUT)
 record=dict(stage=i,script=stage,returncode=p.returncode,seconds=time.perf_counter()-t,log=lf.relative_to(B).as_posix(),utc=datetime.now(timezone.utc).isoformat());records.append(record)
 (L/'execution.json').write_text(json.dumps(records,indent=2),encoding='utf-8');print(json.dumps(record),flush=True)
 if p.returncode:print(lf.read_text(encoding='utf-8')[-4000:],flush=True);sys.exit(p.returncode)
print('All scientific stages completed.',flush=True)
