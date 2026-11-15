"""Separate ordinal reordering and expanded fiscal-accounting verification.
Uses the frozen structural sampler/preparation; does not import the stress runner
or its grid, dependency-score, reorder, evaluate or envelope functions.
"""
from pathlib import Path
import os,sys,json,copy,math,time,hashlib,itertools
sys.dont_write_bytecode=True
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
import numpy as np,pandas as pd
from scipy.stats import rankdata
ROOT=Path(__file__).resolve().parents[3];B=ROOT/'revision_jpm_v2';O=ROOT/'extensions/stress/resultados';start=time.perf_counter()
contract=json.loads((ROOT/'extensions/config/CONTRATO_ALCANCE_V2.json').read_text());cfg=contract['stress_extension'];SEEDS=contract['between_seed']['seeds'];SIZES=contract['between_seed']['sizes']
sys.path.insert(0,str(B/'paso_07d/conciliacion_fiscal_02/scripts'));import comun as cf
annual=pd.read_csv(B/'paso_07d/costos_transicion_03/resultados/FRONTERAS_ANUALES_480.csv');cases=pd.read_csv(B/'paso_07e/resultados/CASOS_PUBLICABLES.csv')
KEY=['country_id','scenario_id','regime_id','policy_variant_id','rule','mode'];PF=['recurring_author_frequency','registered_leakage_frequency','nonnegative_frontier_frequency'];QF=['Fmax_p05','Fmax_p50','Fmax_p95']
checks=[];maxerrors={};marginals=pd.read_csv(O/'PRESERVACION_MARGINALES.csv');savedcorr=pd.read_csv(O/'CORRELACIONES_REALIZADAS.csv');driver_saved=pd.read_csv(O/'DRIVERS_ESTRES.csv');frames=[];tails=[]
sha=lambda a:hashlib.sha256(np.asarray(a,dtype=np.float64).tobytes()).hexdigest()
def check(label,v,**detail):
 checks.append(dict(check=label,passed=bool(v),**detail))
 if not v:raise RuntimeError((label,detail))
def eq(label,a,b,tol=1e-10):
 a=np.asarray(a);b=np.asarray(b);d=float(np.max(np.abs(a-b)));maxerrors[label]=max(maxerrors.get(label,0.),d)
 check(label,a.shape==b.shape and np.isfinite(a).all() and np.isfinite(b).all() and d<=tol,max_abs_error=d)
def rho(a,b):return float(np.corrcoef(rankdata(a),rankdata(b))[0,1])
def revenue(p,alpha,kw,kn):
 t_l=(p['ssc']+(1-alpha)*p['pit'])/p['ls']*p['ul'];t_n=(p['cit']*p['relative_base']+alpha*p['pit'])/(1-p['ls'])*p['uk'];v=p['vat_yield']*p['uc']
 return (t_l*(1-v*kw)+v*kw)*p['dw']+(t_n*(1-v*kn)+v*kn)*p['dn']+(1-v*kn)*p['ai']
signs=np.array(cfg['signs']);matrix=(1-.8)*np.eye(6)+.8*np.outer(signs,signs)
check('independent_matrix_PSD',float(np.linalg.eigvalsh(matrix).min())>0.)
for seed in SEEDS:
 s=cf.mc.ValueSampler(cf.x['values'],50000,seed,record_parameters=False);front=s.array('E_prod_frontier')
 # Only warm the structural cache in the original order, without production summaries.
 for c in cf.ta.COUNTRIES:
  for sc in cf.ta.SCENARIOS:
   cs=cf.mc.build_country_scenario_draws(s,cf.x,c,sc,front)
   for reg in cf.ta.REGIMES:
    rd=cf.mc.build_regime_draws(s,reg);cf.build(s,c,sc,reg,cs,rd,cf.policies(c)[0])
 before=json.loads((O/f'CACHE_INDEPENDIENTE_{seed}.json').read_text());check(f'regenerated_all_independent_vectors:{seed}',{str(k):sha(v) for k,v in s.cache.items()}==before)
 stress=copy.copy(s);stress.cache=s.cache.copy();factors={}
 for ci,c in enumerate(cfg['country_order']):
  rng=np.random.default_rng(np.random.SeedSequence([seed,8001,ci]));factor=rng.standard_normal(50000);eps=rng.standard_normal((50000,6));factors[c]=factor
  for j,name in enumerate(cfg['variables']):
   scores=signs[j]*math.sqrt(.8)*factor+math.sqrt(1-.8)*eps[:,j]
   key=cf.mc.ValueKey(name,country=c);original=s.cache[key]
   new=np.sort(original)[rankdata(scores,method='ordinal').astype(int)-1];stress.cache[key]=new
   saved=marginals.query('seed==@seed and country_id==@c and parameter==@name').iloc[0]
   check(f'permutation_exact:{seed}:{c}:{name}',sha(original)==saved.before_sha256 and sha(new)==saved.after_sha256 and sha(np.sort(new))==saved.sorted_sha256 and np.array_equal(np.sort(original),np.sort(new)))
  for na,nb in itertools.combinations(cfg['variables'],2):
   a=stress.cache[cf.mc.ValueKey(na,country=c)];b=stress.cache[cf.mc.ValueKey(nb,country=c)]
   expected=savedcorr.query('seed==@seed and country_id==@c and variable_a==@na and variable_b==@nb').iloc[0].realized_spearman
   if np.ptp(a)>0 and np.ptp(b)>0:eq('rank_correlations',rho(a,b),expected,1e-13)
   else:check('undefined_correlation_for_constant',pd.isna(expected))
 rows=[];targets={}
 for c in cf.ta.COUNTRIES:
  for sc in cf.ta.SCENARIOS:
   cs=cf.mc.build_country_scenario_draws(stress,cf.x,c,sc,stress.array('E_prod_frontier'))
   for reg in cf.ta.REGIMES:
    rd=cf.mc.build_regime_draws(stress,reg);p,*ignored=cf.build(stress,c,sc,reg,cs,rd,cf.policies(c)[0])
    check(f'support:{seed}:{c}:{sc}:{reg}',bool(cs['support_ok'].all()) and np.all(cs['g_ai_level']>0));eq('income_conservation',p['dw']+p['dn'],p['g'],1e-14)
    kw=cf.value('mpc_W',country=c);r0=revenue(p,.15,kw,.5*kw);corners=np.array([revenue(p,a,w,n) for a,w,n in itertools.product([0.,.3],[0.,1.],[0.,1.])]);rv={'reference':r0,'uniform':corners.min(axis=0),'possible':corners.max(axis=0)}
    check('revenue_domain_encloses_reference',np.all(rv['uniform']<=r0+1e-14) and np.all(rv['possible']>=r0-1e-14))
    selected=cases.query('country_id==@c and scenario_id==@sc and regime_id==@reg')
    if len(selected):targets[(c,sc,reg)]=r0.copy()
    quant={(mode,n):np.quantile(a[:n],[.05,.5,.95]) for mode,a in rv.items() for n in SIZES}
    for r in annual.query('country_id==@c and scenario_id==@sc and regime_id==@reg').itertuples():
     admin=cf.x['policy_admin_transition_cost'].query('country_id==@c and policy_id==@r.policy_id').iloc[0];registered=admin.admin_cost_new_gdp-admin.admin_savings_existing_gdp+admin.transition_recurring_gdp+admin.leakage_fixed_gdp*rd['leakage_multiplier']
     for rule,xi,addspb in [('B0',0.,False),('B1',.1,False),('B2',.1,True)]:
      required=(1+xi)*r.benefits+(r.spb if addspb else 0.)
      for mode,a in rv.items():
       for n in SIZES:
        margin=a[:n]-required;count=int((margin>=r.F_recurring_author).sum());cr=int((margin>=registered[:n]).sum());cn=int((margin>=0).sum());q=quant[(mode,n)]-required
        rows.append(dict(seed=seed,country_id=c,scenario_id=sc,regime_id=reg,policy_variant_id=r.policy_variant_id,rule=rule,mode=mode,n=n,valid=n,Fmax_p05=q[0],Fmax_p50=q[1],Fmax_p95=q[2],nonnegative_frontier_count=cn,nonnegative_frontier_frequency=cn/n,recurring_author_crossings=count,recurring_author_frequency=count/n,registered_leakage_crossings=cr,registered_leakage_frequency=cr/n))
    if len(selected):
     order=np.argsort(factors[c],kind='mergesort')
     for r in selected.itertuples():
      hit=r0-r.F_recurring_author>=1.1*r.benefits+r.spb
      for label,ix in [('lower_factor_decile',order[:5000]),('upper_factor_decile',order[-5000:])]:tails.append(dict(seed=seed,country_id=c,scenario_id=sc,regime_id=reg,policy_variant_id=r.policy_variant_id,stratum=label,n=5000,crossings=int(hit[ix].sum()),frequency=float(hit[ix].mean())))
 z=pd.DataFrame(rows);previous=pd.read_csv(O/f'MC_ESTRES_{seed}.csv');a=z.set_index(KEY+['n']).sort_index();b=previous.set_index(KEY+['n']).sort_index()
 check(f'complete_grid:{seed}',len(z)==17280 and not z.duplicated(KEY+['n']).any() and a.index.equals(b.index))
 for col in ['valid','nonnegative_frontier_count','recurring_author_crossings','registered_leakage_crossings']:check(f'exact_counts:{seed}:{col}',np.array_equal(a[col],b[col]))
 for col in PF+QF:eq('stress_summary:'+col,a[col],b[col])
 frames.append(z)
 for (c,sc,reg),target in targets.items():
  scores=[]
  for key,a in stress.cache.items():
   if key.country not in (None,c) or key.scenario not in (None,sc) or key.regime not in (None,reg) or key.policy is not None:continue
   if key.name.startswith('phi_raw_') and key.name!='phi_raw_'+sc:continue
   if np.ptp(a)==0:continue
   scores.append((str(key),rho(a,target)))
  scores.sort(key=lambda t:(-abs(t[1]),t[0]));old=driver_saved.query('seed==@seed and country_id==@c and scenario_id==@sc and regime_id==@reg').set_index('parameter')
  for key,r in scores:eq('driver_spearman',r,float(old.loc[key,'spearman']),1e-13)
  check('driver_top3_set',set(k for k,_ in scores[:3])==set(old.query('rank<=3').index))
 print(f'Separate stress reconstruction {seed} PASS',flush=True)
allrows=pd.concat(frames,ignore_index=True);ta=pd.DataFrame(tails).set_index(['seed','country_id','scenario_id','regime_id','policy_variant_id','stratum']).sort_index();tb=pd.read_csv(O/'DECILES_FACTOR_SIETE_CASOS.csv').set_index(ta.index.names).sort_index()
check('tail_keys',ta.index.equals(tb.index));check('tail_counts',np.array_equal(ta.crossings,tb.crossings));eq('tail_frequencies',ta.frequency,tb.frequency)
within=0.
for seed,z in allrows.groupby('seed'):
 a=z.query('n==25000').set_index(KEY);b=z.query('n==50000').set_index(KEY)
 within=max(within,max(float((a[col]-b[col]).abs().max()) for col in PF))
between=0.
for col in PF:
 p=allrows.query('n==50000').pivot(index=KEY,columns='seed',values=col);between=max(between,float((p.max(axis=1)-p.min(axis=1)).max()))
report=json.loads((O/'RESUMEN_EJECUCION.json').read_text());eq('reported_within',within,report['max_25k_50k_frequency_difference'],1e-14);eq('reported_between',between,report['max_between_seed_frequency_range'],1e-14)
check('declared_convergence_threshold',max(within,between)<=.02)
summary=dict(status='PASS',checks=len(checks),summary_rows_reconstructed=len(allrows),marginal_vectors_reconstructed=72,context_draws_reconstructed=3*80*50000,max_errors=maxerrors,max_25k_50k=within,max_between_seed=between,elapsed_seconds=time.perf_counter()-start,method='Frozen structural sampler/prepared inputs shared; independent ordinal permutation, expanded fiscal expression, vertex extrema, quantile translation, counts, correlations and tails. Not external replication.')
(O/'VERIFICACION_SEPARADA.json').write_text(json.dumps({'summary':summary,'checks':checks},indent=2)+'\n');print(json.dumps(summary,indent=2),flush=True)
