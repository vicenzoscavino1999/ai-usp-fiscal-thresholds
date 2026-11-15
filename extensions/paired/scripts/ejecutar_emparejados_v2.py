"""Three-seed extension of the unchanged matched history and seven-switch bridge."""
from pathlib import Path
import os,sys,ast,json,math,time,hashlib
sys.dont_write_bytecode=True
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[key]='1'
ROOT=Path(__file__).resolve().parents[3];B=ROOT/'revision_jpm_v2';O=ROOT/'extensions/paired/resultados';start=time.perf_counter()
sys.path.insert(0,str(B/'paso_07d/conciliacion_fiscal_02/scripts'))
import comun as cf
import numpy as np,pandas as pd
from scipy.stats import beta
SEEDS=[20261114,20261215,20261316];SIZES=[5000,10000,25000,50000]
NAMES=['IVA_destino','base_CIT_relativa','renta_IA_ordinaria','asignacion_PIT','respuesta_normalizada','consumo_disponible','instalacion_separada']
BRIDGE_METRICS=['B2_frequency_percent','R_mean_percent_GDP','balance_mean_pp_GDP']
sequence=[0,1,3,7,15,31,63,127]
source=B/'paso_07g/scripts/descomponer_resultados.py';tree=ast.parse(source.read_text(encoding='utf-8'))
selected=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['setup','shapley']]
if len(selected)!=2:raise RuntimeError('Expected precisely two frozen functions')
env={'cf':cf,'np':np,'math':math,'names':NAMES}
exec(compile(ast.Module(body=selected,type_ignores=[]),str(source),mode='exec'),env)
setup,shapley=env['setup'],env['shapley']
(O/'FUNCIONES_REUTILIZADAS.json').write_text(json.dumps({'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'functions':[n.name for n in selected],'function_source_sha256':{n.name:hashlib.sha256(ast.get_source_segment(source.read_text(encoding='utf-8'),n).encode()).hexdigest() for n in selected},'method':'AST definitions only; no original top-level statements executed'},indent=2)+'\n')
spec=pd.read_csv(B/'paso_04/DISTRIBUCIONES_CAPTURA_REGISTRADAS.csv')
samples=pd.read_parquet(B/'paso_04/evidencia/MUESTRAS_HISTORICAS_PARA_SORTEO.parquet')
annual=pd.read_csv(B/'paso_07d/costos_transicion_03/resultados/FRONTERAS_ANUALES_480.csv')
cell=annual.query("country_id=='CHL' and scenario_id=='mid' and regime_id=='r0' and policy_variant_id=='GMI:GMI_ideal_aggregate'").iloc[0]
checkrows=[];hashrows=[];histframes=[];bridgeframes=[];shapleyframes=[];signrows=[]
def check(name,passed,**details):
 checkrows.append(dict(check=name,passed=bool(passed),**details))
 if not passed:raise RuntimeError((name,details))
def arrhash(a):return hashlib.sha256(np.asarray(a,dtype=np.float64).tobytes()).hexdigest()
def sameframe(label,got,ref,keys,exact,floating):
 a=got.set_index(keys).sort_index();b=ref.set_index(keys).sort_index()
 check(label+':keys',a.index.equals(b.index),rows=len(a))
 for col in exact:check(label+':'+col,np.array_equal(a[col],b[col]))
 for col in floating:
  delta=float(np.max(np.abs(a[col]-b[col])));check(label+':'+col,np.allclose(a[col],b[col],atol=1e-10,rtol=1e-8),max_abs_difference=delta)

for seed in SEEDS:
 print(f'Start seed {seed}',flush=True)
 sampler=cf.mc.ValueSampler(cf.x['values'],50000,seed,record_parameters=False)
 front=sampler.array('E_prod_frontier');cs=cf.mc.build_country_scenario_draws(sampler,cf.x,'CHL','mid',front);rd=cf.mc.build_regime_draws(sampler,'r0')
 pol=next(p for p in cf.policies('CHL') if p['policy_variant_id']=='GMI:GMI_ideal_aggregate')
 fun,original,z=setup(sampler,'CHL','mid','r0',cs,rd,pol)
 p,ref,envl,ext,iv=cf.build(sampler,'CHL','mid','r0',cs,rd,pol)
 g=cs['g_ai_level'];F=original['fixed']['f_fix'];ann=cf.annuity('CHL','GMI');cost=pol['cost_gross_gdp'];n=50000
 check(f'full_support:{seed}',np.isfinite(g).all() and (g>0).all() and cs['support_ok'].all())
 check(f'cost_convention:{seed}',abs(cost-cell.benefits)<1e-14 and np.max(np.abs(F-ann-cell.F_recurring_author))<1e-14 and cell.spb==0.)
 rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed,741])))
 u=np.clip(rng.random(n),1e-12,1-1e-12);uneg=rng.random(n);uyear=rng.random(n)
 def pert(lo,mode,hi):
  if abs(hi-lo)<1e-14:return np.full(n,mode)
  return lo+(hi-lo)*beta.ppf(u,1+4*(mode-lo)/(hi-lo),1+4*(hi-mode)/(hi-lo))
 captures={'reference':z['M'],'uniform_bound':envl['M_low'],'possible_bound':envl['M_high']}
 for v in spec.itertuples():
  if bool(v.empirical_resampling):
   vals=samples[samples.variant_id.eq(v.variant_id)].sort_values('year').capture_for_draw.to_numpy()
   capture=vals[np.minimum((uyear*len(vals)).astype(int),len(vals)-1)]
  else:
   positive=pert(v.pos_p10,v.pos_p50,v.pos_p90)
   capture=positive if v.positive_only or v.p_negative==0 else np.where(uneg<v.p_negative,pert(v.neg_p10,v.neg_p50,v.neg_p90),positive)
  captures[v.variant_id]=capture
  check(f'finite_history:{seed}:{v.variant_id}',np.isfinite(capture).all())
  signrows.append(dict(seed=seed,mode=v.variant_id,n=n,negative_count=int((capture<0).sum()),zero_count=int((capture==0).sum()),positive_only=bool(v.positive_only),empirical_resampling=bool(v.empirical_resampling),registered_negative_mass=float(v.p_negative)))
 hist=[]
 for mode,M in captures.items():
  hashrows.append(dict(seed=seed,mode=mode,vector='M',n=n,sha256=arrhash(M)))
  for rule,mult in [('B0',1.),('B2',1.1)]:
   hit=np.isfinite(M)&(g*M-cell.F_recurring_author>=mult*cell.benefits+cell.spb)
   for size in SIZES:
    k=int(hit[:size].sum());q=np.quantile(np.asarray(M)[:size],[.1,.5,.9])
    hist.append(dict(seed=seed,mode=mode,rule=rule,n=size,crossings=k,frequency=k/size,mc95_low=0 if k==0 else beta.ppf(.025,k,size-k+1),mc95_high=1 if k==size else beta.ppf(.975,k+1,size-k),M_p10=q[0],M_p50=q[1],M_p90=q[2],F_recurring=cell.F_recurring_author,benefits=cell.benefits))
 hist=pd.DataFrame(hist);hist.to_csv(O/f'COMPARADORES_{seed}.csv',index=False);histframes.append(hist)
 # Same 128 subsets and seven groups as the frozen scientific bridge.
 bridge=[]
 for mask in range(128):
  revenue=fun(mask&63);f=F-ann if mask&64 else F;balance=revenue-f-1.1*cost;hit=balance>=0
  for size in SIZES:
   k=int(hit[:size].sum())
   bridge.append(dict(seed=seed,mask=mask,n=size,crossings=k,B2_frequency_percent=100*k/size,R_mean_percent_GDP=100*float(revenue[:size].mean()),R_p50_percent_GDP=100*float(np.median(revenue[:size])),balance_mean_pp_GDP=100*float(balance[:size].mean()),F_mean_percent_GDP=100*float(f[:size].mean()),M_mean=float(np.mean(revenue[:size]/g[:size]))))
 bridge=pd.DataFrame(bridge);bridge.to_csv(O/f'PUENTE_{seed}.csv',index=False);bridgeframes.append(bridge)
 attrs=[]
 for size in SIZES:
  a=bridge.query('n==@size')
  for metric in BRIDGE_METRICS:
   attrs.extend(dict(seed=seed,n=size,**v) for v in shapley(zip(a['mask'],a[metric]),metric,f'CHL_mid_r0_{size}'))
 attrs=pd.DataFrame(attrs);attrs.to_csv(O/f'ATRIBUCIONES_{seed}.csv',index=False);shapleyframes.append(attrs)
 # Persist primitives and uniforms so the separate verifier does not import setup.
 primitive={'draw_id':np.arange(n),'g':g,'dw':original['omega_l']*g,'dn':g-original['omega_l']*g,'F_equivalent':F,'original_M':original['mfc_gross'],'current_M':z['M'],'u':u,'uneg':uneg,'uyear':uyear}
 for name in ['chi_Kbase','chi_dom','psi_shift','tau_L_disp','tau_K_disp','tau_R_disp','mpc_W','mpc_Pi','mpc_R','m_M','theta_R_dom','exempt_C']:primitive[name]=sampler.array(name,country='CHL')
 for name in ['lambda_ai','lambda_ai_kbase']:primitive[name]=cs[name]
 pd.DataFrame(primitive).to_parquet(O/f'PRIMITIVAS_{seed}.parquet',index=False)
 fr=cf.fiscal.loc['CHL'];constants=dict(ls=cf.value('LS_labor_share',country='CHL'),pit=fr.pit_gdp/100,cit=fr.cit_gdp/100,ssc=fr.social_contrib_gdp/100,vat=cf.value('tau_C_eff',country='CHL'),kw_reference=cf.value('mpc_W',country='CHL'),base_central=cf.value('chi_Kbase',country='CHL')*cf.value('chi_dom',country='CHL')*(1-cf.value('psi_shift',country='CHL')),benefits=cost,annuity=ann,regime='r0',alpha_reference=.15)
 if seed==SEEDS[0]:(O/'CONSTANTES_CHILE.json').write_text(json.dumps(constants,indent=2)+'\n')
 else:check(f'constants:{seed}',constants==json.loads((O/'CONSTANTES_CHILE.json').read_text()))
 if seed==SEEDS[0]:
  saved=pd.read_parquet(B/'paso_04/evidencia/SORTEOS_EMPAREJADOS.parquet')
  check('baseline_gain_exact',np.array_equal(g,saved.g_ai_level))
  check('baseline_original_capture_exact',np.array_equal(original['mfc_gross'],saved.mfc__structural))
  for mode,M in captures.items():
   if mode not in ['reference','uniform_bound','possible_bound']:check('baseline_history_vector:'+mode,np.array_equal(M,saved['mfc__'+mode].to_numpy()))
  sameframe('baseline_table5',hist.query('n==50000'),pd.read_csv(B/'paso_07e/resultados/COMPARADORES_CAPTURA_ACTUALIZADOS.csv'),['mode','rule'],['n','crossings'],['frequency','mc95_low','mc95_high','M_p50','F_recurring','benefits'])
  sameframe('baseline_bridge',bridge.query('n==50000'),pd.read_csv(B/'paso_07g/bloque_2_descomposicion/PUENTE_CHILE_50000_128.csv'),['mask'],['n','crossings'],BRIDGE_METRICS+['R_p50_percent_GDP','F_mean_percent_GDP','M_mean'])
  a=pd.read_csv(B/'paso_07g/bloque_2_descomposicion/ATRIBUCION_SOBRE_TODOS_LOS_ORDENES.csv').query("case=='CHL_mid_r0_50000'")
  sameframe('baseline_shapley',attrs.query('n==50000'),a,['metric','change'],[],['allocation','min_order_marginal','max_order_marginal','initial','final'])
  (O/'GUARDA_SEMILLA_ORIGINAL.json').write_text(json.dumps({'status':'PASS','checks':checkrows,'before_additional_seeds':True},indent=2)+'\n')
  print('Original seed guard PASS: historical vectors, table 5, 128 subsets, Shapley',flush=True)
 print(f'Completed seed {seed}: {len(hist)} comparator rows, {len(bridge)} bridge rows; elapsed={time.perf_counter()-start:.1f}s',flush=True)

history=pd.concat(histframes,ignore_index=True);bridge=pd.concat(bridgeframes,ignore_index=True);attrs=pd.concat(shapleyframes,ignore_index=True)
pd.DataFrame(hashrows).to_csv(O/'HASHES_VECTORES_CAPTURA.csv',index=False);pd.DataFrame(signrows).to_csv(O/'MASA_NEGATIVA_CONSERVADA.csv',index=False)
history.to_csv(O/'COMPARADORES_TRES_SEMILLAS.csv',index=False);bridge.to_csv(O/'PUENTE_TRES_SEMILLAS.csv',index=False);attrs.to_csv(O/'ATRIBUCIONES_TRES_SEMILLAS.csv',index=False)
conv=[];spread=[]
for family,df,keys,field,scale in [('table5',history,['mode','rule'],'frequency',1.),('bridge',bridge,['mask'],'B2_frequency_percent',.01)]:
 for seed,a in df.groupby('seed'):
  for na,nb in zip(SIZES[:-1],SIZES[1:]):
   x=a.query('n==@na').set_index(keys)[field];y=a.query('n==@nb').set_index(keys)[field];delta=scale*(y-x)
   for k,v in delta.items():conv.append(dict(family=family,seed=seed,n_from=na,n_to=nb,key=str(k),difference=float(v),absolute_difference=abs(float(v)),passes_002=abs(float(v))<=.02))
 for k,a in df.query('n==50000').groupby(keys):
  low=scale*float(a[field].min());high=scale*float(a[field].max());spread.append(dict(family=family,key=str(k),min_frequency=low,max_frequency=high,between_seed_range=high-low,passes_002=high-low<=.02))
conv=pd.DataFrame(conv);spread=pd.DataFrame(spread);conv.to_csv(O/'CONVERGENCIA_ESCALERA.csv',index=False);spread.to_csv(O/'DISPERSION_ENTRE_SEMILLAS.csv',index=False)
ad=[]
for (metric,name),a in attrs.query('n==50000').groupby(['metric','change']):
 vals=a.allocation.to_numpy();signs=np.sign(np.where(np.abs(vals)<1e-12,0.,vals))
 ad.append(dict(metric=metric,change=name,min_allocation=float(vals.min()),max_allocation=float(vals.max()),between_seed_range=float(np.ptp(vals)),sign_stable=len(set(signs))==1,unit='percentage points of conditional frequency' if metric=='B2_frequency_percent' else 'percentage points of counterfactual GDP'))
ad=pd.DataFrame(ad);ad.to_csv(O/'DISPERSION_ATRIBUCIONES.csv',index=False)
rank=attrs.query("n==50000 and metric=='B2_frequency_percent'").copy();rank['rank_by_allocation']=rank.groupby('seed').allocation.rank(method='min',ascending=False).astype(int)
rank[['seed','change','allocation','rank_by_allocation']].to_csv(O/'RANGOS_ATRIBUCIONES.csv',index=False)
rank_stable=bool(rank.groupby('change').rank_by_allocation.nunique().eq(1).all())
headline=history.query("n==50000 and mode in ['reference','hist_tax_mixture','hist_total_revenue_mixture']")
headline.to_csv(O/'TABLA5_TRES_SEMILLAS.csv',index=False)
orders=[]
for (seed,rule),a in headline.groupby(['seed','rule']):
 b=a.set_index('mode').frequency;orders.append(bool(b['reference']<b['hist_tax_mixture']<b['hist_total_revenue_mixture']))
bridge[bridge['mask'].isin(sequence)].to_csv(O/'SECUENCIA_TRES_SEMILLAS.csv',index=False)
maxwithin=float(conv.query('n_from==25000').absolute_difference.max());maxbetween=float(spread.between_seed_range.max())
report=dict(execution_status='PASS',frequency_convergence_status='PASS' if max(maxwithin,maxbetween)<=.02 else 'FAIL',frequency_threshold=.02,max_25k_50k_difference=maxwithin,max_between_seed_range=maxbetween,history_modes=history['mode'].nunique(),history_rows=len(history),bridge_rows=len(bridge),attribution_rows=len(attrs),seeds=SEEDS,sizes=SIZES,headline_capture_order_preserved=all(orders),attribution_signs_preserved=bool(ad.sign_stable.all()),attribution_ranking_identical=rank_stable,all_guards_passed=all(z['passed'] for z in checkrows),guard_checks=len(checkrows),elapsed_seconds=time.perf_counter()-start,model_changed=False,paper_changed=False,scope='B_MATCHED_HISTORY + B_BRIDGE; independent matched sampler; stress block and public integration remain separate')
(O/'CHECKS_EJECUCION.json').write_text(json.dumps(checkrows,indent=2)+'\n');(O/'RESUMEN_EJECUCION.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
