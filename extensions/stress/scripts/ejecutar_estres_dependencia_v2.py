from pathlib import Path
import os,sys,ast,json,math,copy,itertools,time,hashlib
sys.dont_write_bytecode=True
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
import numpy as np,pandas as pd
from scipy.stats import spearmanr
ROOT=Path(__file__).resolve().parents[3];B=ROOT/'revision_jpm_v2';O=ROOT/'extensions/stress/resultados';PRIOR=ROOT/'extensions/convergence';start=time.perf_counter()
contract=json.loads((ROOT/'extensions/config/CONTRATO_ALCANCE_V2.json').read_text());cfg=contract['stress_extension']
sys.path.insert(0,str(B/'paso_07d/conciliacion_fiscal_02/scripts'))
import comun as cf
mc=cf.mc;SEEDS=contract['between_seed']['seeds'];SIZES=contract['between_seed']['sizes'];MODE=cfg['mode']
KEY=['country_id','scenario_id','regime_id','policy_variant_id','rule','mode'];PF=['recurring_author_frequency','registered_leakage_frequency','nonnegative_frontier_frequency'];QF=['Fmax_p05','Fmax_p50','Fmax_p95']
annual=pd.read_csv(B/'paso_07d/costos_transicion_03/resultados/FRONTERAS_ANUALES_480.csv');cases=pd.read_csv(B/'paso_07e/resultados/CASOS_PUBLICABLES.csv');casecontexts=set(map(tuple,cases[['country_id','scenario_id','regime_id']].values))
checks=[];driverrows=[];marginals=[];correlations=[];tails=[];frames=[];deltas=[];allcases=[]
source=PRIOR/'scripts/convergencia_v2.py';tree=ast.parse(source.read_text(encoding='utf-8'));functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['record','oracle','grid']]
if len(functions)!=3:raise RuntimeError('Missing frozen functions')
env=dict(cf=cf,mc=mc,np=np,pd=pd,spearmanr=spearmanr,annual=annual,casecontexts=casecontexts,checks=checks,driverrows=driverrows)
exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),'exec'),env);grid=env['grid'];check=env['record']
check('country_order',list(cf.ta.COUNTRIES)==cfg['country_order'])
check('block_variables',list(mc.DEPENDENCY_VARIABLES)==cfg['variables'])
check('registered_latent_stress',mc.FACTOR_RHO_BY_MODE[mc.MC_FACTOR_RHO08]==cfg['latent_rho']==.8)
sha=lambda a:hashlib.sha256(np.asarray(a,dtype=np.float64).tobytes()).hexdigest()
(O/'FUNCIONES_REUTILIZADAS.json').write_text(json.dumps({'source':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'functions':[n.name for n in functions],'AST_only':True},indent=2)+'\n')

for seed in SEEDS:
 print(f'Reconstruct independent cache seed {seed}',flush=True)
 independent=mc.ValueSampler(cf.x['values'],50000,seed,record_parameters=False)
 baseline=grid(independent,seed,'independent',SIZES,drivers=False)
 previous=pd.read_csv(PRIOR/f'resultados/MC_{seed}_independent.csv')
 a=baseline.set_index(KEY+['n']).sort_index();b=previous.set_index(KEY+['n']).sort_index()
 check(f'baseline_keys:{seed}',a.index.equals(b.index),rows=len(a))
 for col in ['valid','nonnegative_frontier_count','recurring_author_crossings','registered_leakage_crossings']:check(f'baseline_exact:{seed}:{col}',np.array_equal(a[col],b[col]))
 for col in PF+QF:check(f'baseline_float:{seed}:{col}',np.allclose(a[col],b[col],atol=1e-10,rtol=1e-8),max_abs_difference=float((a[col]-b[col]).abs().max()))
 before={str(k):sha(v) for k,v in independent.cache.items()};(O/f'CACHE_INDEPENDIENTE_{seed}.json').write_text(json.dumps(before,indent=2)+'\n')
 stress=copy.copy(independent);stress.cache=independent.cache.copy();factors={}
 matrix=mc.dependency_matrix(mc.MC_FACTOR_RHO08);mc.assert_psd(matrix,label=MODE)
 check('matrix_PSD',float(np.linalg.eigvalsh(matrix).min())>=0.,min_eigenvalue=float(np.linalg.eigvalsh(matrix).min()))
 for ci,c in enumerate(cfg['country_order']):
  rng=np.random.default_rng(np.random.SeedSequence([seed,8001,ci]));scores=mc.dependency_scores(mc.MC_FACTOR_RHO08,50000,rng)
  factors[c]=np.random.default_rng(np.random.SeedSequence([seed,8001,ci])).standard_normal(50000)
  for name in cfg['variables']:
   key=mc.ValueKey(name,country=c);old=independent.cache[key];new=mc.reorder_to_scores(old,scores[name]);stress.cache[key]=new
   exact=np.array_equal(np.sort(old),np.sort(new));check(f'marginal:{seed}:{c}:{name}',exact)
   marginals.append(dict(seed=seed,country_id=c,parameter=name,n=50000,before_sha256=sha(old),after_sha256=sha(new),sorted_sha256=sha(np.sort(old)),sorted_exact=exact,constant=bool(np.ptp(old)==0),latent_rho=.8))
  for na,nb in itertools.combinations(cfg['variables'],2):
   aa=stress.cache[mc.ValueKey(na,country=c)];bb=stress.cache[mc.ValueKey(nb,country=c)];rho=float(spearmanr(aa,bb).statistic) if np.ptp(aa)>0 and np.ptp(bb)>0 else None
   correlations.append(dict(seed=seed,country_id=c,variable_a=na,variable_b=nb,latent_correlation=float(matrix.loc[na,nb]),realized_spearman=rho))
 changed={mc.ValueKey(name,country=c) for c in cfg['country_order'] for name in cfg['variables']}
 check(f'only_registered_vectors_changed:{seed}',all(sha(stress.cache[k])==before[str(k)] for k in independent.cache if k not in changed))
 print(f'Start stress grid seed {seed}',flush=True)
 z=grid(stress,seed,MODE,SIZES,drivers=True);z.to_csv(O/f'MC_ESTRES_{seed}.csv',index=False);frames.append(z)
 check(f'independent_cache_preserved:{seed}',{str(k):sha(v) for k,v in independent.cache.items()}==before)
 for c,sc,reg in sorted(casecontexts):
  cs=mc.build_country_scenario_draws(stress,cf.x,c,sc,stress.array('E_prod_frontier'));rd=mc.build_regime_draws(stress,reg)
  p,ref,*_=cf.build(stress,c,sc,reg,cs,rd,cf.policies(c)[0]);order=np.argsort(factors[c],kind='mergesort')
  for r in cases.query('country_id==@c and scenario_id==@sc and regime_id==@reg').itertuples():
   hit=ref['revenue']-r.F_recurring_author>=1.1*r.benefits+r.spb
   for label,ix in [('lower_factor_decile',order[:5000]),('upper_factor_decile',order[-5000:])]:tails.append(dict(seed=seed,country_id=c,scenario_id=sc,regime_id=reg,policy_variant_id=r.policy_variant_id,stratum=label,n=len(ix),crossings=int(hit[ix].sum()),frequency=float(hit[ix].mean()),factor_min=float(factors[c][ix].min()),factor_max=float(factors[c][ix].max()),role='conditional on constructed latent-factor tail; not observed risk probability'))
 for comp,other in [('independent',previous),('rank_factor_nominal',pd.read_csv(PRIOR/f'resultados/MC_{seed}_rank_factor_nominal.csv'))]:
  a=z.query('n==50000').set_index(KEY);b=other.query('n==50000').set_index(KEY)
  check(f'comparison_keys:{seed}:{comp}',a.index.equals(b.index))
  for metric in PF+QF:
   d=a[metric]-b[metric];idx=d.abs().idxmax();deltas.append(dict(seed=seed,comparison=comp,metric=metric,max_abs_difference=float(d.abs().max()),signed_difference_at_max=float(d.loc[idx]),worst_cell='|'.join(idx)))
  selected=other.query("n==50000 and rule=='B2'").merge(cases[['country_id','scenario_id','regime_id','policy_variant_id']],on=['country_id','scenario_id','regime_id','policy_variant_id'],validate='many_to_one');allcases.append(selected)
 allcases.append(z.query("n==50000 and rule=='B2'").merge(cases[['country_id','scenario_id','regime_id','policy_variant_id']],on=['country_id','scenario_id','regime_id','policy_variant_id'],validate='many_to_one'))
 print(f'Completed seed {seed}: elapsed={time.perf_counter()-start:.1f}s',flush=True)

d=pd.concat(frames,ignore_index=True);d.to_csv(O/'MC_ESTRES_TRES_SEMILLAS.csv',index=False)
pd.DataFrame(marginals).to_csv(O/'PRESERVACION_MARGINALES.csv',index=False);pd.DataFrame(correlations).to_csv(O/'CORRELACIONES_REALIZADAS.csv',index=False);pd.DataFrame(tails).to_csv(O/'DECILES_FACTOR_SIETE_CASOS.csv',index=False);pd.DataFrame(deltas).to_csv(O/'SENSIBILIDAD_ENTRE_DEPENDENCIAS.csv',index=False);pd.concat(allcases,ignore_index=True).to_csv(O/'SIETE_CASOS_TRES_DEPENDENCIAS.csv',index=False)
conv=[];disp=[]
for seed,a in d.groupby('seed'):
 for na,nb in zip(SIZES[:-1],SIZES[1:]):
  x=a.query('n==@na').set_index(KEY);y=a.query('n==@nb').set_index(KEY)
  for metric in PF+QF:
   err=(y[metric]-x[metric]).abs();conv.append(dict(seed=seed,n_from=na,n_to=nb,metric=metric,max_abs_difference=float(err.max()),cells_over_002=int((err>.02).sum()) if metric in PF else None,worst_cell='|'.join(err.idxmax())))
for metric in PF+QF:
 p=d.query('n==50000').pivot(index=KEY,columns='seed',values=metric);gap=p.max(axis=1)-p.min(axis=1)
 disp.append(dict(metric=metric,max_between_seed_range=float(gap.max()),cells_over_002=int((gap>.02).sum()) if metric in PF else None,worst_cell='|'.join(gap.idxmax())))
conv=pd.DataFrame(conv);disp=pd.DataFrame(disp);conv.to_csv(O/'CONVERGENCIA_ESCALERA.csv',index=False);disp.to_csv(O/'DISPERSION_ENTRE_SEMILLAS.csv',index=False)
drivers=pd.DataFrame(driverrows);drivers.to_csv(O/'DRIVERS_ESTRES.csv',index=False);ranks=[]
for keys,z in drivers.groupby(['country_id','scenario_id','regime_id']):
 for a,b in itertools.combinations(SEEDS,2):
  ra=z.query('seed==@a').set_index('parameter');rb=z.query('seed==@b').set_index('parameter');ta=set(ra.query('rank<=3').index);tb=set(rb.query('rank<=3').index)
  ranks.append(dict(zip(['country_id','scenario_id','regime_id'],keys),seed_a=a,seed_b=b,top3_overlap=len(ta&tb),top3_identical=ta==tb,max_rank_change=int((ra['rank']-rb['rank']).abs().max())))
ranks=pd.DataFrame(ranks);ranks.to_csv(O/'ESTABILIDAD_DRIVERS.csv',index=False)
prior_drivers=pd.read_csv(PRIOR/'resultados/DRIVERS_SPEARMAN.csv');comp_ranks=[]
for (seed,c,sc,reg),z in drivers.groupby(['seed','country_id','scenario_id','regime_id']):
 for dep in ['independent','rank_factor_nominal']:
  a=prior_drivers.query('seed==@seed and country_id==@c and scenario_id==@sc and regime_id==@reg and dependency==@dep');ta=set(z.query('rank<=3').name);tb=set(a.query('rank<=3').name)
  comp_ranks.append(dict(seed=seed,country_id=c,scenario_id=sc,regime_id=reg,comparison=dep,top3_overlap=len(ta&tb),stress_top3=';'.join(z.query('rank<=3').sort_values('rank').name),comparison_top3=';'.join(a.query('rank<=3').sort_values('rank').name)))
pd.DataFrame(comp_ranks).to_csv(O/'DRIVERS_ENTRE_DEPENDENCIAS.csv',index=False)
within=float(conv.query('n_from==25000 and metric in @PF').max_abs_difference.max());between=float(disp.query('metric in @PF').max_between_seed_range.max())
report=dict(execution_status='PASS',frequency_convergence_status='PASS' if max(within,between)<=.02 else 'FAIL',threshold=.02,max_25k_50k_frequency_difference=within,max_between_seed_frequency_range=between,marginals_exact=all(r['sorted_exact'] for r in marginals),marginal_vectors=len(marginals),driver_top3_status='PASS' if ranks.top3_identical.all() else 'MIXED',driver_pairs=len(ranks),driver_top3_identical=int(ranks.top3_identical.sum()),summary_rows=len(d),baseline_rows_reproduced=3*17280,checks=len(checks),elapsed_seconds=time.perf_counter()-start,latent_rho=.8,seeds=SEEDS,sizes=SIZES,model_changed=False,paper_changed=False,unknown_coefficients_randomized=False,interpretation='Numerical convergence is distinct from sensitivity across dependence assumptions')
(O/'CHECKS_EJECUCION.json').write_text(json.dumps(checks,indent=2)+'\n');(O/'RESUMEN_EJECUCION.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)
