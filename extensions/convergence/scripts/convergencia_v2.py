"""Additional V2 stability experiment; no modification of the frozen model."""
from pathlib import Path
import os,sys,json,time,copy,itertools,hashlib
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3];B=ROOT/'revision_jpm_v2'
O=ROOT/'extensions/convergence/resultados';O.mkdir(exist_ok=True,parents=True)
sys.path.insert(0,str(B/'paso_07d/conciliacion_fiscal_02/scripts'))
import comun as cf
import numpy as np,pandas as pd
from scipy.stats import spearmanr
mc=cf.mc; start=time.perf_counter()
SEEDS=[20261114,20261215,20261316];SIZES=[5000,10000,25000,50000]
KEY=['country_id','scenario_id','regime_id','policy_variant_id','rule','mode']
PF=['recurring_author_frequency','registered_leakage_frequency','nonnegative_frontier_frequency']
QF=['Fmax_p05','Fmax_p50','Fmax_p95']
annual=pd.read_csv(B/'paso_07d/costos_transicion_03/resultados/FRONTERAS_ANUALES_480.csv')
cases=pd.read_csv(B/'paso_07e/resultados/CASOS_PUBLICABLES.csv')
casecontexts=set(map(tuple,cases[['country_id','scenario_id','regime_id']].values))
checks=[];marginals=[];rankcorr=[];driverrows=[]

def record(name,passed,**detail):
 checks.append(dict(check=name,passed=bool(passed),**detail))
 if not passed:raise AssertionError((name,detail))

def oracle(p,w):
 # Expanded independently from aggregate anchors, including tax-consumption feedback.
 a=.15;v=p['vat_yield']*p['uc'];kw=w;kn=.5*w
 tl=(p['ssc']+(1-a)*p['pit'])/p['ls']*p['ul']
 tn=(p['cit']*p['relative_base']+a*p['pit'])/(1-p['ls'])*p['uk']
 return (tl*(1-v*kw)+v*kw)*p['dw']+(tn*(1-v*kn)+v*kn)*p['dn']+(1-v*kn)*p['ai']

def grid(sampler,seed,dependency,sizes,drivers=False):
 rows=[];targets={};front=sampler.array('E_prod_frontier');max_oracle=0.;all_valid=0
 for c in cf.ta.COUNTRIES:
  for sc in cf.ta.SCENARIOS:
   cs=mc.build_country_scenario_draws(sampler,cf.x,c,sc,front)
   for reg in cf.ta.REGIMES:
    rd=mc.build_regime_draws(sampler,reg)
    p,z,env,ext,old=cf.build(sampler,c,sc,reg,cs,rd,cf.policies(c)[0])
    g=cs['g_ai_level'];rev={'reference':g*z['M'],'uniform':g*env['M_low'],'possible':g*env['M_high']}
    valid=np.isfinite(g)&(g>0)&cs['support_ok']
    for a in rev.values():valid&=np.isfinite(a)
    # Frozen frontiers used all draws. Invalid new support must not be silently dropped.
    record(f'valid_support:{seed}:{dependency}:{c}:{sc}:{reg}',valid.all(),invalid=int((~valid).sum()))
    all_valid+=int(valid.sum());err=float(np.max(np.abs(oracle(p,cf.value('mpc_W',country=c))-rev['reference'])))
    max_oracle=max(max_oracle,err)
    if drivers and (c,sc,reg) in casecontexts:targets[(c,sc,reg)]=rev['reference'].copy()
    ad=annual.query('country_id==@c and scenario_id==@sc and regime_id==@reg')
    for r in ad.itertuples():
     admin=cf.x['policy_admin_transition_cost'].query('country_id==@c and policy_id==@r.policy_id').iloc[0]
     fr=admin.admin_cost_new_gdp-admin.admin_savings_existing_gdp+admin.transition_recurring_gdp+admin.leakage_fixed_gdp*rd['leakage_multiplier']
     for rule,xi,sp in [('B0',0.,False),('B1',.1,False),('B2',.1,True)]:
      req=(1+xi)*r.benefits+(r.spb if sp else 0.)
      for mode,rv in rev.items():
       fmax=rv-req
       for n in sizes:
        f=fmax[:n];q=np.quantile(f,[.05,.5,.95]);ca=int((f>=r.F_recurring_author).sum());cr=int((f>=fr[:n]).sum());cn=int((f>=0).sum())
        rows.append(dict(seed=seed,dependency=dependency,country_id=c,scenario_id=sc,regime_id=reg,policy_variant_id=r.policy_variant_id,rule=rule,mode=mode,n=n,valid=n,Fmax_p05=q[0],Fmax_p50=q[1],Fmax_p95=q[2],nonnegative_frontier_count=cn,nonnegative_frontier_frequency=cn/n,recurring_author_crossings=ca,recurring_author_frequency=ca/n,registered_leakage_crossings=cr,registered_leakage_frequency=cr/n))
 record(f'oracle:{seed}:{dependency}',max_oracle<2e-12,max_abs_error=max_oracle,valid_context_draws=all_valid)
 if drivers:
  for (c,sc,reg),target in targets.items():
   scores=[]
   for key,a in sampler.cache.items():
    if key.country not in (None,c) or key.scenario not in (None,sc) or key.regime not in (None,reg) or key.policy is not None:continue
    if key.name.startswith('phi_raw_') and key.name!='phi_raw_'+sc:continue
    if np.ptp(a)==0:continue
    val=float(spearmanr(a,target).statistic)
    scores.append((str(key),key.name,val))
   scores.sort(key=lambda v:(-abs(v[2]),v[0]))
   for rank,(key,name,v) in enumerate(scores,1):driverrows.append(dict(seed=seed,dependency=dependency,country_id=c,scenario_id=sc,regime_id=reg,parameter=key,name=name,spearman=v,rank=rank))
 return pd.DataFrame(rows)

def correlated(source,seed):
 out=copy.copy(source);out.cache=source.cache.copy()
 matrix=mc.dependency_matrix(mc.MC_FACTOR_NOMINAL);mc.assert_psd(matrix,label='V2 nominal rank sensitivity')
 for ci,c in enumerate(cf.ta.COUNTRIES):
  scores=mc.dependency_scores(mc.MC_FACTOR_NOMINAL,source.size,np.random.default_rng(np.random.SeedSequence([seed,6001,ci])))
  for name in mc.DEPENDENCY_VARIABLES:
   key=mc.ValueKey(name,country=c);a=source.cache[key];b=mc.reorder_to_scores(a,scores[name]);out.cache[key]=b
   same=np.array_equal(np.sort(a),np.sort(b));record(f'marginals:{seed}:{c}:{name}',same)
   marginals.append(dict(seed=seed,country_id=c,parameter=name,n=len(a),exact_sorted_equality=same,is_constant=bool(np.ptp(a)==0),latent_rho=.5,psd_min_eigenvalue=float(np.linalg.eigvalsh(matrix).min())))
  for na,nb in itertools.combinations(mc.DEPENDENCY_VARIABLES,2):
   a=out.cache[mc.ValueKey(na,country=c)];b=out.cache[mc.ValueKey(nb,country=c)]
   rho=float(spearmanr(a,b).statistic) if np.ptp(a)>0 and np.ptp(b)>0 else None
   rankcorr.append(dict(seed=seed,country_id=c,variable_a=na,variable_b=nb,realized_spearman=rho,latent_correlation=float(matrix.loc[na,nb])))
 return out

def compare_baseline(result):
 ref=pd.read_csv(B/'paso_07d/costos_transicion_03/resultados/FRONTERAS_MC_5000.csv').set_index(KEY).sort_index()
 got=result.set_index(KEY).sort_index()
 record('baseline_grid_keys',got.index.equals(ref.index),rows=len(got))
 for col in ['nonnegative_frontier_count','recurring_author_crossings','registered_leakage_crossings']:
  record('baseline_exact:'+col,np.array_equal(got[col],ref[col]))
 for col in QF+PF[:2]:
  delta=float(np.max(np.abs(got[col]-ref[col])));record('baseline_float:'+col,np.allclose(got[col],ref[col],atol=1e-10,rtol=1e-8),max_abs_difference=delta)

def paired(seed):
 n=50000;s=mc.ValueSampler(cf.x['values'],n,seed,record_parameters=False);front=s.array('E_prod_frontier')
 cs=mc.build_country_scenario_draws(s,cf.x,'CHL','mid',front);rd=mc.build_regime_draws(s,'r0');pol=next(p for p in cf.policies('CHL') if p['policy_variant_id']=='GMI:GMI_ideal_aggregate')
 # Preserve historical old-module call order before the reconciled model.
 oldbase=cf.old_module().compute_cell_arrays(s,cf.x,'CHL','mid','r0',pol,cs,rd)
 p,z,env,ext,old=cf.build(s,'CHL','mid','r0',cs,rd,pol)
 g=cs['g_ai_level'];F=oldbase['fixed']['f_fix'];ann=cf.annuity('CHL','GMI');rows=[]
 for timing,f in [('annual_equivalent',F),('endpoint_without_setup_obligation',F-ann)]:
  for mode,M in [('reference',z['M']),('uniform',env['M_low']),('possible',env['M_high'])]:
   for rule,req in [('B0',pol['cost_gross_gdp']),('B2',1.1*pol['cost_gross_gdp'])]:
    hit=g*M-f>=req
    for n in SIZES:rows.append(dict(seed=seed,timing=timing,mode=mode,rule=rule,n=n,crossings=int(hit[:n].sum()),frequency=float(hit[:n].mean())))
 result=pd.DataFrame(rows)
 if seed==SEEDS[0]:
  keys=['timing','mode','rule'];ref=pd.read_csv(B/'paso_07d/conciliacion_fiscal_02/resultados/CHILE_EMPAREJADO_50000.csv').query("mode in ['reference','uniform','possible']").set_index(keys).sort_index();got=result.query('n==50000').set_index(keys).sort_index()
  record('paired_chile_50000_keys',got.index.equals(ref.index))
  record('paired_chile_50000_counts',np.array_equal(got.crossings,ref.crossings),rows=len(got))
 return result

print('Guard: rebuilding baseline 5000',flush=True)
guard=grid(mc.ValueSampler(cf.x['values'],5000,SEEDS[0],record_parameters=False),SEEDS[0],'independent_guard',[5000]);compare_baseline(guard)
guard.to_csv(O/'GUARD_BASELINE_5000.csv',index=False)
(O/'VALIDACION_ADAPTADOR.json').write_text(json.dumps(checks,indent=2)+'\n')
frames=[];paired_frames=[]
for seed in SEEDS:
 s=mc.ValueSampler(cf.x['values'],50000,seed,record_parameters=False)
 for dep in ['independent','rank_factor_nominal']:
  print(f'Start seed={seed} mode={dep}',flush=True)
  sampler=s if dep=='independent' else correlated(s,seed)
  z=grid(sampler,seed,dep,SIZES,drivers=True)
  z.to_csv(O/f'MC_{seed}_{dep}.csv',index=False);frames.append(z)
  if seed==SEEDS[0] and dep=='independent':compare_baseline(z.query('n==5000'))
  print(f'Completed {seed} {dep}: {len(z)} rows elapsed={time.perf_counter()-start:.1f}s',flush=True)
 paired_frames.append(paired(seed))
 del s,sampler

allrows=pd.concat(frames,ignore_index=True);paired_all=pd.concat(paired_frames,ignore_index=True)
paired_all.to_csv(O/'CHILE_EMPAREJADO_TRES_SEMILLAS.csv',index=False)
pd.DataFrame(marginals).to_csv(O/'PRESERVACION_MARGINALES.csv',index=False)
pd.DataFrame(rankcorr).to_csv(O/'CORRELACIONES_REALIZADAS.csv',index=False)
drivers=pd.DataFrame(driverrows);drivers.to_csv(O/'DRIVERS_SPEARMAN.csv',index=False)
rank_stability=[]
for keys,z in drivers.groupby(['dependency','country_id','scenario_id','regime_id']):
 for a,b in itertools.combinations(SEEDS,2):
  xa=z.query('seed==@a').set_index('parameter');xb=z.query('seed==@b').set_index('parameter');common=xa.index.intersection(xb.index)
  ta=set(xa.query('rank<=3').index);tb=set(xb.query('rank<=3').index)
  rank_stability.append(dict(zip(['dependency','country_id','scenario_id','regime_id'],keys),seed_a=a,seed_b=b,top3_overlap=len(ta&tb),top3_identical=ta==tb,max_rank_change=int((xa.loc[common,'rank']-xb.loc[common,'rank']).abs().max())))
rankstab=pd.DataFrame(rank_stability);rankstab.to_csv(O/'ESTABILIDAD_DRIVERS.csv',index=False)
changes=[]
for (seed,dep),z in allrows.groupby(['seed','dependency']):
 for na,nb in zip(SIZES[:-1],SIZES[1:]):
  a=z.query('n==@na').set_index(KEY);b=z.query('n==@nb').set_index(KEY)
  for col in PF+QF:
   d=(a[col]-b[col]).abs();idx=d.idxmax()
   changes.append(dict(seed=seed,dependency=dep,n_a=na,n_b=nb,metric=col,max_abs_difference=float(d.max()),over_001=int((d>.01).sum()) if col in PF else None,over_002=int((d>.02).sum()) if col in PF else None,worst_cell='|'.join(idx)))
conv=pd.DataFrame(changes);conv.to_csv(O/'CONVERGENCIA_POR_TAMANO.csv',index=False)
disp=[];tolerances=[]
for dep,z in allrows.query('n==50000').groupby('dependency'):
 for col in PF+QF:
  pivot=z.pivot(index=KEY,columns='seed',values=col);d=pivot.max(axis=1)-pivot.min(axis=1)
  disp.append(dict(dependency=dep,metric=col,max_between_seed_range=float(d.max()),over_001=int((d>.01).sum()) if col in PF else None,over_002=int((d>.02).sum()) if col in PF else None,worst_cell='|'.join(d.idxmax())))
  tolerances.append(dict(dependency=dep,metric=col,observed_max=float(d.max()),historical_factor=10,mechanical_proposal_atol=10*float(d.max()),auto_applied=False,role='empirical three-seed proposal; not scientific acceptance or fixed-seed tolerance'))
disp=pd.DataFrame(disp);disp.to_csv(O/'DISPERSION_ENTRE_SEMILLAS.csv',index=False)
pd.DataFrame(tolerances).to_csv(O/'CALIBRACION_TOLERANCIAS_PROPUESTA.csv',index=False)
paired_delta=[]
for seed,z in paired_all.groupby('seed'):
 a=z.query('n==25000').set_index(['timing','mode','rule']);b=z.query('n==50000').set_index(['timing','mode','rule'])
 paired_delta.append(float((a.frequency-b.frequency).abs().max()))
pivot=paired_all.query('n==50000').pivot(index=['timing','mode','rule'],columns='seed',values='frequency');paired_spread=float((pivot.max(axis=1)-pivot.min(axis=1)).max())
within=float(conv.query("n_a==25000 and metric in @PF").max_abs_difference.max());between=float(disp.query('metric in @PF').max_between_seed_range.max())
report=dict(execution_status='PASS',frequency_convergence_status='PASS' if max(within,between,max(paired_delta),paired_spread)<=.02 else 'FAIL',threshold=.02,max_25k_50k_frequency_difference=within,max_between_seed_frequency_range=between,paired_max_25k_50k=max(paired_delta),paired_max_between_seed_range=paired_spread,driver_top3_strong_stability_status='PASS' if rankstab.top3_identical.all() else 'MIXED',driver_pairs=len(rankstab),driver_top3_identical=int(rankstab.top3_identical.sum()),driver_min_top3_overlap=int(rankstab.top3_overlap.min()),guard_checks=len(checks),all_checks_passed=all(r['passed'] for r in checks),grid_summary_rows=len(allrows),seeds=SEEDS,sizes=SIZES,elapsed_seconds=time.perf_counter()-start,model_changed=False,paper_changed=False,r4_tolerance_changed=False,unknown_coefficients_sampled=False)
(O/'CHECKS.json').write_text(json.dumps(checks,indent=2)+'\n')
(O/'RESUMEN_MC.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
