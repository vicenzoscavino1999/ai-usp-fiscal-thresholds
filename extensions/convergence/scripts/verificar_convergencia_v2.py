from pathlib import Path
import os,sys,json,itertools
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3];B=ROOT/'revision_jpm_v2';O=ROOT/'extensions/convergence/resultados'
sys.path.insert(0,str(B/'paso_07d/costos_transicion_03/scripts'))
import common03 as cm
import numpy as np,pandas as pd
from scipy.optimize import brentq
keys=['country_id','scenario_id','regime_id','policy_variant_id','rule','mode']
metrics=['recurring_author_frequency','registered_leakage_frequency','nonnegative_frontier_frequency']
tests=[]
def check(name,v,**detail):
 tests.append(dict(check=name,passed=bool(v),**detail))
 if not v:raise AssertionError((name,detail))
frames=[]
for file in sorted(O.glob('MC_*.csv')):
 x=pd.read_csv(file);check(file.name+':shape',len(x)==17280 and not x.duplicated(keys+['n']).any())
 check(file.name+':finite',np.isfinite(x.select_dtypes('number')).all().all())
 check(file.name+':support',(x.n==x.valid).all())
 check(file.name+':quantile_order',((x.Fmax_p05<=x.Fmax_p50)&(x.Fmax_p50<=x.Fmax_p95)).all())
 for col,count in zip(metrics,['recurring_author_crossings','registered_leakage_crossings','nonnegative_frontier_count']):
  check(file.name+':'+col,np.allclose(x[col],x[count]/x.n,atol=2e-15,rtol=0) and x[col].between(0,1).all())
 for col in metrics+['Fmax_p05','Fmax_p50','Fmax_p95']:
  z=x.pivot(index=keys[:-1]+['n'],columns='mode',values=col)
  check(file.name+':bounds:'+col,((z.uniform<=z.reference+2e-15)&(z.reference<=z.possible+2e-15)).all())
 frames.append(x)
check('six_full_experiments',len(frames)==6)
d=pd.concat(frames,ignore_index=True)
changes=[]
for dep,z in d.query('n==50000').groupby('dependency'):
 for sa,sb in itertools.combinations(sorted(z.seed.unique()),2):
  a=z.query('seed==@sa').set_index(keys);b=z.query('seed==@sb').set_index(keys)
  check(f'seeds_keys:{dep}:{sa}:{sb}',a.index.equals(b.index))
  changes.extend((a[m]-b[m]).abs().max() for m in metrics)
between=float(max(changes));within=0.
for (seed,dep),z in d.groupby(['seed','dependency']):
 a=z.query('n==25000').set_index(keys);b=z.query('n==50000').set_index(keys)
 within=max(within,max(float((a[m]-b[m]).abs().max()) for m in metrics))
saved=json.loads((O/'RESUMEN_MC.json').read_text())
check('reported_convergence_recomputed',abs(between-saved['max_between_seed_frequency_range'])<2e-15 and abs(within-saved['max_25k_50k_frequency_difference'])<2e-15)
check('predeclared_frequency_threshold',max(within,between)<=.02)
differences=[]
for seed,z in d.query('n==50000').groupby('seed'):
 a=z.query("dependency=='independent'").set_index(keys);b=z.query("dependency=='rank_factor_nominal'").set_index(keys)
 for metric in metrics:
  delta=b[metric]-a[metric];idx=delta.abs().idxmax()
  differences.append(dict(seed=int(seed),metric=metric,max_abs_difference=float(delta.abs().max()),signed_difference_at_max=float(delta.loc[idx]),worst_cell='|'.join(idx)))
pd.DataFrame(differences).to_csv(O/'SENSIBILIDAD_DEPENDENCIA.csv',index=False)
case=pd.read_csv(B/'paso_07e/resultados/CASOS_PUBLICABLES.csv')
case_keys=['country_id','scenario_id','regime_id','policy_variant_id']
h=d.query("n==50000 and rule=='B2' and mode=='reference'").merge(case[case_keys],on=case_keys,validate='many_to_one')
h.to_csv(O/'FRECUENCIAS_SIETE_CASOS.csv',index=False)
# Follow-up to the failed zero-crossing expectation, without changing its verdict.
ctx=cm.context('CHL','stress','r0');coef=ctx['reference'];r=case.query("country_id=='CHL' and scenario_id=='stress' and regime_id=='r0'").iloc[0]
required=1.1*r.benefits+r.spb+r.F_recurring_author
f=lambda e:float(cm.capture(ctx,coef,exposure=e)['revenue'])-required
root=brentq(f,1e-9,ctx['exposure'],xtol=1e-14)
# Separately invert the affine gain and the production translation equation.
p=ctx['prepared'];a,w,n=coef;v=p['vat_yield']*p['uc']
tl=(p['ssc']+(1-a)*p['pit'])/p['ls']*p['ul'];tn=(p['cit']*p['relative_base']+a*p['pit'])/(1-p['ls'])*p['uk']
L=tl*(1-v*w)+v*w;N=tn*(1-v*n)+v*n
share=1/(1+np.exp(-(np.log(p['ls']/(1-p['ls']))+ctx['pressure_per_q']*ctx['q'])))
ai=ctx['lambda_ai']*ctx['tau_ai']*max(0,1-ctx['erosion_ai']*ctx['tau_ai'])
slope=L*share+N*(1-share)+(1-v*n)*ai;intercept=(L-N)*(share-p['ls'])
gstar=(required-intercept)/slope;Tstar=np.expm1(np.log1p(gstar)/10)/ctx['phi'];eps=ctx['epsilon']
analytic=((Tstar*ctx['s_frontier']/(eps+(1-eps)*ctx['q'])**ctx['gamma'])**(1/ctx['beta'])-eps)/(1-eps)
check('low_exposure_root_independent_formula',abs(root-analytic)<1e-12 and abs(f(root))<1e-12)
check('low_exposure_survival_consistent_with_threshold',root<.035 and f(.035)>0.)
followup=dict(country_id='CHL',scenario_id='stress',regime_id='r0',policy_variant_id=r.policy_variant_id,reference_exposure=ctx['exposure'],tested_exposure=.035,minimum_exposure_B2_numeric=root,minimum_exposure_B2_analytic=float(analytic),required_revenue=required,required_gain=float(gstar),test_gain=float(cm.capture(ctx,coef,exposure=.035)['g']),test_revenue=float(cm.capture(ctx,coef,exposure=.035)['revenue']),test_margin_B2=f(.035),g_zero_redistribution_intercept=float(intercept),zero_crossing_expectation_status='FAIL_RETAINED',interpretation='The stress growth shock remains large enough at low positive exposure. This is consistent with the current budget threshold, not a failure of the no-AI anchor. Zero crossings cannot be claimed for this diagnostic.')
(O/'ANALISIS_CONTROL_EXPOSICION.json').write_text(json.dumps(followup,indent=2)+'\n')
# Every stored economic diagnostic reconciles its budget and classifications.
diag=pd.read_csv(O/'DIAGNOSTICOS_ACTUALES_480.csv')
check('diagnostic_keys_unique',not diag.duplicated(case_keys+['diagnostic']).any())
check('diagnostic_budget_identity',np.allclose(diag.margin_B2,diag.revenue-1.1*diag.benefits-diag.spb-diag.F_recurring,atol=1e-13,rtol=0))
check('diagnostic_classification_identity',np.array_equal(diag.covers_B2,diag.margin_B2>=0))
result=dict(status='PASS',checks=len(tests),max_between_seed=between,max_within_seed=within,all_checks_passed=True)
(O/'VERIFICACION_SEPARADA.json').write_text(json.dumps({'summary':result,'checks':tests},indent=2)+'\n')
print(json.dumps(result,indent=2));print(json.dumps(followup,indent=2))
