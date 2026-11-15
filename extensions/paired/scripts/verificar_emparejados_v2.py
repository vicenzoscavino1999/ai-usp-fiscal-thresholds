"""Separate direct accounting, inverse-beta and permutation implementation.
Does not import or execute the production model or setup/shapley functions.
"""
from pathlib import Path
import os,json,itertools,time
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[key]='1'
import numpy as np,pandas as pd
from scipy.special import betaincinv,betainc
ROOT=Path(__file__).resolve().parents[3];B=ROOT/'revision_jpm_v2';O=ROOT/'extensions/paired/resultados';start=time.perf_counter()
SEEDS=[20261114,20261215,20261316];SIZES=[5000,10000,25000,50000]
NAMES=['IVA_destino','base_CIT_relativa','renta_IA_ordinaria','asignacion_PIT','respuesta_normalizada','consumo_disponible','instalacion_separada']
METRICS=['B2_frequency_percent','R_mean_percent_GDP','balance_mean_pp_GDP']
c=json.loads((O/'CONSTANTES_CHILE.json').read_text());spec=pd.read_csv(B/'paso_04/DISTRIBUCIONES_CAPTURA_REGISTRADAS.csv');samples=pd.read_parquet(B/'paso_04/evidencia/MUESTRAS_HISTORICAS_PARA_SORTEO.parquet')
annual=pd.read_csv(B/'paso_07d/costos_transicion_03/resultados/FRONTERAS_ANUALES_480.csv');cell=annual.query("country_id=='CHL' and scenario_id=='mid' and regime_id=='r0' and policy_variant_id=='GMI:GMI_ideal_aggregate'").iloc[0]
values=pd.read_parquet(B/'paso_07d/evidencia/insumos/values.parquet');checks=[];worst={};allhistory=[];allbridge=[]
def check(name,value,**data):
 checks.append(dict(check=name,passed=bool(value),**data))
 if not value:raise RuntimeError((name,data))
def eq(name,a,b,tol=1e-10):
 a=np.asarray(a);b=np.asarray(b);err=float(np.max(np.abs(a-b)));worst[name]=max(worst.get(name,0.),err)
 check(name,a.shape==b.shape and np.isfinite(a).all() and np.isfinite(b).all() and err<=tol,max_abs_error=err,values=int(a.size))
for name in ['tau_L_relative_delta_r0','tau_K_relative_delta_r0','tau_C_relative_delta_r0','tau_AI_eff_r0']:
 row=values[values.name.eq(name)];check('r0_assumption:'+name,len(row)==1 and float(row.iloc[0].baseline_value)==0.)
for seed in SEEDS:
 p=pd.read_parquet(O/f'PRIMITIVAS_{seed}.parquet');g=p.g.to_numpy();dw=p.dw.to_numpy();dn=g-dw;s=c['ls'];n=len(p)
 check(f'primitive_dimensions:{seed}',n==50000 and p.draw_id.tolist()==list(range(50000)) and np.isfinite(p.to_numpy()).all())
 eq('income_conservation',p.dn,dn,1e-14)
 rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed,741])))
 for field,vector in [('u',np.clip(rng.random(n),1e-12,1-1e-12)),('uneg',rng.random(n)),('uyear',rng.random(n))]:
  check(f'original_rng_uniforms:{seed}:{field}',np.array_equal(p[field],vector))
 absbase=p.chi_Kbase.to_numpy()*p.chi_dom.to_numpy()*(1-p.psi_shift.to_numpy());relative=absbase/c['base_central']
 oldcons=p.mpc_W.to_numpy()*(1-p.tau_L_disp.to_numpy())*dw+p.mpc_Pi.to_numpy()*(1-p.tau_K_disp.to_numpy())*absbase*dn+p.mpc_R.to_numpy()*p.theta_R_dom.to_numpy()*(1-p.tau_R_disp.to_numpy())*np.maximum(0,dn-p.chi_Kbase.to_numpy()*dn)
 records=[]
 for mask in range(128):
  dest,corp,rent,allocate,norm,consume,sep=[bool(mask&(1<<j)) for j in range(7)]
  alpha=.15 if allocate else 0.
  labor=(c['ssc']+(1-alpha)*c['pit'])/s*dw
  corporate=c['cit']/(1-s)*dn*(relative if corp else absbase)
  if not rent:corporate=corporate-p.lambda_ai_kbase.to_numpy()*g*c['cit']/(1-s)
  capital=alpha*c['pit']/(1-s)*dn
  spending=c['kw_reference']*(dw-labor)+.5*c['kw_reference']*(dn-corporate-capital) if consume else (1-p.exempt_C.to_numpy())*np.maximum(0,oldcons)
  if not dest:spending=spending*(1-p.m_M.to_numpy())
  revenue=labor+corporate+capital+c['vat']*spending
  f=p.F_equivalent.to_numpy()-(c['annuity'] if sep else 0.);balance=revenue-f-1.1*c['benefits'];hit=balance>=0.
  if mask==0:eq('original_endpoint_capture',revenue/g,p.original_M)
  if mask==127:eq('current_endpoint_capture',revenue/g,p.current_M);reference=revenue/g
  for size in SIZES:
   records.append(dict(seed=seed,mask=mask,n=size,crossings=int(hit[:size].sum()),B2_frequency_percent=100*float(hit[:size].mean()),R_mean_percent_GDP=100*float(revenue[:size].mean()),balance_mean_pp_GDP=100*float(balance[:size].mean())))
 rebuilt=pd.DataFrame(records).set_index(['n','mask']).sort_index();saved=pd.read_csv(O/f'PUENTE_{seed}.csv').set_index(['n','mask']).sort_index()
 check('bridge_key_order',rebuilt.index.equals(saved.index));check('bridge_counts_exact',np.array_equal(rebuilt.crossings,saved.crossings),rows=len(saved))
 for metric in METRICS:eq('bridge:'+metric,rebuilt[metric],saved[metric])
 allbridge.append(rebuilt.reset_index())
 # Domain extrema use explicit eight-corner cash accounting, not model envelope().
 corners=[]
 for alpha,kw,kn in itertools.product([0.,.3],[0.,1.],[0.,1.]):
  labor=(c['ssc']+(1-alpha)*c['pit'])/s*dw
  capital=(c['cit']*relative+alpha*c['pit'])/(1-s)*dn
  corners.append((labor+capital+c['vat']*(kw*(dw-labor)+kn*(dn-capital)))/g)
 captures={'reference':reference,'uniform_bound':np.min(corners,axis=0),'possible_bound':np.max(corners,axis=0)}
 def inverse_pert(lo,mode,hi):
  if abs(hi-lo)<1e-14:return np.full(n,mode)
  a=1+4*(mode-lo)/(hi-lo);b=1+4*(hi-mode)/(hi-lo)
  q=betaincinv(a,b,p.u.to_numpy());eq('inverse_beta_roundtrip',betainc(a,b,q),p.u.to_numpy(),1e-11)
  return lo+(hi-lo)*q
 for v in spec.itertuples():
  if v.empirical_resampling:
   vals=samples[samples.variant_id.eq(v.variant_id)].sort_values('year').capture_for_draw.to_numpy();draw=vals[np.minimum(np.floor(p.uyear.to_numpy()*len(vals)).astype(int),len(vals)-1)]
  else:
   positive=inverse_pert(v.pos_p10,v.pos_p50,v.pos_p90)
   draw=positive if v.positive_only or v.p_negative==0 else np.where(p.uneg.to_numpy()<v.p_negative,inverse_pert(v.neg_p10,v.neg_p50,v.neg_p90),positive)
  captures[v.variant_id]=draw
 hist=[]
 for mode,M in captures.items():
  for rule,xi in [('B0',1.),('B2',1.1)]:
   hit=g*M-cell.F_recurring_author>=xi*cell.benefits+cell.spb
   for size in SIZES:
    q=np.quantile(M[:size],[.1,.5,.9]);k=int(hit[:size].sum())
    hist.append(dict(seed=seed,mode=mode,rule=rule,n=size,crossings=k,frequency=k/size,M_p10=q[0],M_p50=q[1],M_p90=q[2],mc95_low=0. if k==0 else betaincinv(k,size-k+1,.025),mc95_high=1. if k==size else betaincinv(k+1,size-k,.975)))
 hist=pd.DataFrame(hist).set_index(['n','mode','rule']).sort_index();old=pd.read_csv(O/f'COMPARADORES_{seed}.csv').set_index(['n','mode','rule']).sort_index()
 check('history_keys',hist.index.equals(old.index));check('history_counts_exact',np.array_equal(hist.crossings,old.crossings),rows=len(hist))
 for col in ['frequency','M_p10','M_p50','M_p90','mc95_low','mc95_high']:eq('history:'+col,hist[col],old[col])
 allhistory.append(hist.reset_index())
 negative=pd.read_csv(O/'MASA_NEGATIVA_CONSERVADA.csv').query('seed==@seed')
 for v in negative.itertuples():check('negative_mass_retained',int((captures[v.mode]<0).sum())==v.negative_count)
 # Average all 5040 order-specific marginal contributions independently.
 attrs=pd.read_csv(O/f'ATRIBUCIONES_{seed}.csv').set_index(['n','metric','change'])
 for size in SIZES:
  for metric in METRICS:
   vals=rebuilt.xs(size,level='n')[metric].reindex(range(128)).to_numpy();contributions=[]
   for order in itertools.permutations(range(7)):
    mask=0;row=np.zeros(7)
    for j in order:
     nextmask=mask|(1<<j);row[j]=vals[nextmask]-vals[mask];mask=nextmask
    contributions.append(row)
   contribution=np.array(contributions);avg=contribution.mean(axis=0)
   eq('shapley_efficiency',avg.sum(),vals[127]-vals[0])
   previous=attrs.loc[(size,metric)].reindex(NAMES)
   eq('shapley_permutations',avg,previous.allocation.to_numpy());eq('min_order_marginal',contribution.min(axis=0),previous.min_order_marginal.to_numpy());eq('max_order_marginal',contribution.max(axis=0),previous.max_order_marginal.to_numpy())
 print(f'Separate reconstruction seed {seed} PASS',flush=True)
allhistory=pd.concat(allhistory,ignore_index=True);allbridge=pd.concat(allbridge,ignore_index=True)
drift={}
for label,df,keys,col,scale in [('table5',allhistory,['mode','rule'],'frequency',1.),('bridge',allbridge,['mask'],'B2_frequency_percent',.01)]:
 within=[]
 for seed,a in df.groupby('seed'):
  low=a.query('n==25000').set_index(keys)[col];high=a.query('n==50000').set_index(keys)[col]
  within.append(float(scale*(high-low).abs().max()))
 piv=df.query('n==50000').pivot(index=keys,columns='seed',values=col);between=float(scale*(piv.max(axis=1)-piv.min(axis=1)).max())
 drift[label]={'within_seed_25k_to_50k':max(within),'between_seeds_at_50k':between}
saved=json.loads((O/'RESUMEN_EJECUCION.json').read_text())
within=max(d['within_seed_25k_to_50k'] for d in drift.values());between=max(d['between_seeds_at_50k'] for d in drift.values())
eq('reported_within_seed',within,saved['max_25k_50k_difference'],1e-14);eq('reported_between_seed',between,saved['max_between_seed_range'],1e-14)
check('declared_threshold',max(within,between)<=.02)
result=dict(status='PASS',checks=len(checks),reconstructed_history_rows=len(allhistory),reconstructed_bridge_rows=len(allbridge),draw_subset_evaluations=3*128*50000,permutations_per_attribution=5040,attribution_vectors_verified=3*4*3,drift=drift,max_errors=worst,elapsed_seconds=time.perf_counter()-start,production_model_imported=False,interpretation='Separate computational implementation inside the project; not external empirical replication')
(O/'VERIFICACION_SEPARADA.json').write_text(json.dumps({'summary':result,'checks':checks},indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
