from common03 import *
import json
checks=[]
def check(name,condition):
 assert condition,name
 checks.append(name)

for i,n in [(0.,0.),(.03,0.),(.03,.06),(.08,.02)]:
 for horizon in [1,3,10,25]:
  H=horizon;zeros=np.zeros(H);f=.002;I=.003;cost=np.full(H,.01)
  z=financing(cost+f,cost,f,0,i,n)
  check(f'balanced_{i}_{n}_{H}',np.max(np.abs(z['balance']))<1e-13)
  z=financing(zeros,zeros,0,I,i,n)
  check(f'setup_not_free_{i}_{n}_{H}',np.allclose(z['balance'],I*((1+i)/(1+n))**np.arange(1,H+1)))
  check(f'no_positive_f_without_revenue_{i}_{n}_{H}',np.all(z['fmax']<0))
  z=financing(np.linspace(.001,.02,H),cost,f,I,i,n)
  capital=z['initial_capital'][-1];net=z['balance']-capital*z['a']**np.arange(1,H+1)
  check(f'capital_covers_all_years_{i}_{n}_{H}',np.all(net<=1e-12) and I-capital<=1e-12)
  check(f'capital_minimal_{i}_{n}_{H}',abs(max(np.r_[I-capital,net]))<1e-12)
  loan=annuity_schedule(I,i,n,3)
  check(f'loan_conserves_principal_{i}_{n}_{H}',abs(sum(r['principal_nominal_gdp0'] for r in loan)-I)<1e-12)

# Domain interiors must lie inside annual and whole-path envelopes, with fixed
# coefficients along each path. Also verify claimed inversion minima against
# an independent fine grid of the full fiscal function.
rng=np.random.default_rng(20261114);cases=json.loads((E/'CONTEXTOS_80.json').read_text(encoding='utf-8'))
for item in cases:
 ctx=item['context'];label='_'.join(item[k] for k in ['country_id','scenario_id','regime_id']);years=np.arange(1,26)
 values=np.stack([capture(ctx,c,years=years)['revenue'] for c in VERTICES]);discount=.97**years
 for j in range(8):
  coef=(rng.uniform(0,.3),rng.uniform(),rng.uniform());revenue=capture(ctx,coef,years=years)['revenue']
  check(f'domain_annual_{label}_{j}',np.all(revenue>=values.min(axis=0)-1e-12) and np.all(revenue<=values.max(axis=0)+1e-12))
  weighted=values@discount;check(f'domain_path_{label}_{j}',weighted.min()-1e-12<=revenue@discount<=weighted.max()+1e-12)
 for j,coef in enumerate([ctx['reference']]+VERTICES):
  grid=np.linspace(ctx['q'],ctx['q_bar']-ctx['epsilon_mu'],2049);revenue=capture(ctx,coef,q=grid)['revenue']
  for factor in [.9,1.0,1.1]:
   req=float(revenue.max())*factor
   inv=invert_operational(ctx,coef,req,'q')
   if inv['status'] in ['not_reachable_within_declared_domain','not_reachable_interval_certified']:
    check(f'no_false_impossibility_{label}_{j}_{factor}',np.max(revenue)<req+1e-12)
   elif np.isfinite(inv['required']):
    earlier=revenue[grid<inv['required']-1e-9]
    check(f'no_earlier_sampled_crossing_{label}_{j}_{factor}',len(earlier)==0 or np.all(earlier<req+1e-12))
   else:
    check(f'honest_precision_limit_{label}_{j}_{factor}',inv['status']=='precision_limited_interval_unresolved')
 # Zero adoption implies zero AI-related receipts, including redistribution.
 check(f'zero_adoption_{label}',float(capture(ctx,ctx['reference'],q=0)['revenue'])==0.)

data={'status':'PASS','checks':len(checks),'names':checks,'random_seed':20261114,'role':'boundary, conservation, interior-domain and operational-inversion tests; no empirical validation'}
(E/'PRUEBAS_MODELO.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in data.items() if k!='names'}),flush=True)
