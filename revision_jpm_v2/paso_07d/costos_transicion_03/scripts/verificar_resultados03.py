"""Independent oracle: no import of candidate fiscal or financing functions."""
from pathlib import Path
import json,hashlib,sys
sys.dont_write_bytecode=True
import numpy as np,pandas as pd
from decimal import Decimal as D,localcontext
T=Path(__file__).resolve().parents[1];O=T/'resultados';E=T/'evidencia';N=T.parent/'conciliacion_fiscal_02'
contexts=json.loads((E/'CONTEXTOS_80.json').read_text(encoding='utf-8'))
ctxs={(x['country_id'],x['scenario_id'],x['regime_id']):x['context'] for x in contexts}
channels=pd.read_csv(O/'CANALES_HORIZONTES_2000.csv');annual=pd.read_csv(O/'FRONTERAS_ANUALES_480.csv');inv=pd.read_csv(O/'INVERSAS_RECALCULADAS.csv');h=pd.read_csv(O/'HORIZONTES_RECALCULADOS.csv');fp=pd.read_parquet(O/'SENDAS_FINANCIACION.parquet');ff=pd.read_csv(O/'FRONTERAS_TRANSICION.csv')
from itertools import product
vertices=list(product([0.,.3],[0.,1.],[0.,1.]))
def dec(v):return D(str(v))
def oracle(c,coef,*,H=10,g=None,q=None,exposure=None,tau=None):
    p=c['prepared'];s=dec(p['ls']);q=dec(c['q'] if q is None else q);ep=dec(c['exposure'] if exposure is None else exposure);eps=dec(c['epsilon'])
    if g is None:
        score=(eps+(1-eps)*ep)**dec(c['beta'])*(eps+(1-eps)*q)**dec(c['gamma'])
        tr=min(D(1),score/dec(c['s_frontier'])) if q>0 and ep>0 else D(0)
        gain=(1+dec(c['phi'])*tr)**H-1
    else:gain=dec(g)
    if gain<=0 or q<=0:return 0.
    sp=1/(1+(-(s/(1-s)).ln()-dec(c['pressure_per_q'])*q).exp())
    dw=sp*(1+gain)-s;dn=gain-dw;a,w,n=map(dec,coef)
    tl=(dec(p['ssc'])+(1-a)*dec(p['pit']))/s*dw*dec(p['ul'])
    tk=dec(p['cit'])/(1-s)*dn*dec(p['relative_base'])*dec(p['uk'])
    tpk=a*dec(p['pit'])/(1-s)*dn*dec(p['uk'])
    tt=dec(c['tau_ai'] if tau is None else tau);tai=dec(c['lambda_ai'])*gain*tt*max(0,1-dec(c['erosion_ai'])*tt)
    vat=dec(p['vat_yield'])*dec(p['uc'])*(w*(dw-tl)+n*(dn-tk-tpk-tai))
    return float(tl+tk+tpk+tai+vat)

errors=[];count=0
with localcontext() as dc:
 dc.prec=40
 for r in channels.itertuples(index=False):
  c=ctxs[(r.country_id,r.scenario_id,r.regime_id)];vals=[]
  for mode,coef in [('reference',c['reference'])]+[(f'v{i}',v) for i,v in enumerate(vertices)]:
   expected=oracle(c,coef,H=int(r.H));actual=getattr(r,'revenue_'+mode);errors.append(abs(expected-actual));count+=1
   assert np.isclose(expected,actual,rtol=2e-11,atol=2e-12),(r,mode,expected,actual)
   if mode!='reference':vals.append(expected)
  assert np.isclose(min(vals),r.revenue_uniform,atol=2e-12,rtol=2e-11)
  assert np.isclose(max(vals),r.revenue_possible,atol=2e-12,rtol=2e-11)
print('Decimal fiscal flows PASS',count,flush=True)

# Affine gain inversion, net AI-tax inversion and full-system operational roots.
root_errors=[];roots=0
for r in inv.itertuples(index=False):
 c=ctxs[(r.country_id,r.scenario_id,r.regime_id)];coef=(r.alpha,r.k_w,r.k_n);req=r.required_revenue
 assert abs(r.M_required*r.g_registered-req)<2e-12
 for variable,col,statuscol in [('g','g_required','gain_status'),('tau','tau_ai_required','ai_status'),('q','q_required','q_status'),('exposure','exposure_required','exposure_status')]:
  x=getattr(r,col);status=getattr(r,statuscol)
  if not np.isfinite(x):continue
  with localcontext() as dc:
   dc.prec=32;got=oracle(c,coef,**{variable:x})
  if (variable=='tau' and x==0) or (variable in ['q','exposure'] and status.startswith('already')):
   assert got>=req-2e-12
  elif variable=='g' and x==0:
   assert r.gain_intercept>=req-2e-12
  else:
   delta=abs(got-req);root_errors.append(delta);assert delta<2e-10,(variable,r,got,req);roots+=1
 if r.ai_status=='no_root_in_effective_rate_domain':
  with localcontext() as dc:dc.prec=32;assert oracle(c,coef,tau=r.ai_peak_rate)<req+2e-12
 for variable in ['q','exposure']:
  if getattr(r,variable+'_status')=='not_reachable_within_declared_domain':
   assert getattr(r,variable+'_monotonic_certified')
   end=c['q_bar']-c['epsilon_mu'] if variable=='q' else 1.
   with localcontext() as dc:dc.prec=32;assert oracle(c,coef,**{variable:end})<req+2e-12
print('Inverse substitutions PASS',len(inv),flush=True)

# Independent nominal ledger, then divide by no-AI GDP of each year.
group=['country_id','scenario_id','regime_id','policy_variant_id','mode','budget','replacement']
finerr=[];frontiererr=[];initialerr=[];ngroups=0
for key,z in fp.groupby(group,sort=False):
 z=z.sort_values('H');r=z.iloc[0];stock=float(r.setup_author);f=float(r.F_recurring_author);i=r.interest;n=r.nominal_growth;initial_pv=[stock];pv_cum=stock
 for x in z.itertuples(index=False):
  Y=(1+n)**x.H
  cash=Y*(x.commitments_before_f+f+x.investment-x.revenue)
  stock=stock*(1+i)+cash
  expected=stock/Y;finerr.append(abs(expected-x.balance_ratio_noAI));assert np.isclose(expected,x.balance_ratio_noAI,rtol=3e-11,atol=3e-12)
  pv_cum+=cash/(1+i)**x.H;initial_pv.append(pv_cum)
  cap=max(0,max(initial_pv));initialerr.append(abs(cap-x.initial_capital_gdp0));assert np.isclose(cap,x.initial_capital_gdp0,rtol=3e-11,atol=3e-12)
  # Sum spending volumes financed by one unit of constant f/GDP.
  factor=sum((1+i)**(x.H-t)*(1+n)**t for t in range(1,x.H+1))/Y
  expected2=(f-x.Fmax_path)*factor;frontiererr.append(abs(expected2-expected));assert np.isclose(expected2,expected,rtol=3e-11,atol=3e-12)
 ngroups+=1
print('Nominal financing ledger PASS',len(fp),flush=True)

# First crossing and persistence, independently assembled from saved fiscal paths.
aid=annual.set_index(['country_id','scenario_id','regime_id','policy_variant_id']).sort_index()
paths=fp.query("mode=='reference' and budget=='cash' and replacement=='none'").set_index(['country_id','scenario_id','regime_id','policy_variant_id','H']).sort_index()
cd=channels.set_index(['country_id','scenario_id','regime_id','H']).sort_index()
def eq_nullable(a,b):return (pd.isna(a) and b is None) or (pd.notna(a) and a==b)
hcount=0
for r in h.itertuples(index=False):
 key=(r.country_id,r.scenario_id,r.regime_id,r.policy_variant_id);a=aid.loc[key];z=paths.loc[key].sort_index();ch=cd.loc[key[:3]].sort_index();revenue=ch['revenue_'+r.mode].to_numpy()
 req=z.benefits.to_numpy()*(1 if r.rule=='B0' else 1.1)+a.F_recurring_author+(a.spb if r.rule=='B2' else 0)
 hits=np.where(revenue>=req)[0];expected=int(hits[0]+1) if len(hits) else None
 assert eq_nullable(r.H_star_recurring,expected)
 if r.mode!='possible':
  tails=[t for t in range(1,26) if (revenue[t-1:]>=req[t-1:]).all()];assert eq_nullable(r.H_persistent_to25,tails[0] if tails else None)
 hcount+=1
print('Horizons re-enumerated PASS',hcount,flush=True)

# Transition frontiers aggregate fixed coefficients over time, never per-year maxima.
endpoints=fp[fp.H.isin([10,25])]
fs={tuple(getattr(r,k) for k in group)+ (r.H,):(r.Fmax_path,r.initial_capital_gdp0) for r in endpoints.itertuples(index=False)}
assert len(fs)==len(endpoints)
for r in ff.itertuples(index=False):
 base=(r.country_id,r.scenario_id,r.regime_id,r.policy_variant_id)
 vals=[fs[base+(f'v{i}',r.budget,r.replacement,r.H)][0] for i in range(8)]
 assert abs(min(vals)-r.Fmax_path_uniform)<2e-12
 assert abs(max(vals)-r.Fmax_path_possible)<2e-12
 vals=[fs[base+(f'v{i}',r.budget,r.replacement,r.H)][1] for i in range(8)]
 assert np.isclose(max(vals),r.initial_capital_worst_domain_gdp0,rtol=1e-11,atol=2e-12)
print('Transition frontiers PASS',len(ff),flush=True)

# Reaggregate Monte Carlo summaries from preserved draws and compare the old stage.
draws=pd.read_parquet(N/'resultados/SORTEOS_CONCILIADOS_80x5000.parquet');mc=pd.read_csv(O/'FRONTERAS_MC_5000.csv');mcerr=[]
admins=pd.read_parquet(T.parent/'evidencia/insumos/policy_admin_transition_cost.parquet').set_index(['country_id','policy_id'])
for key,z in draws.groupby(['country_id','scenario_id','regime_id'],sort=False):
 for r in mc[(mc.country_id==key[0])&(mc.scenario_id==key[1])&(mc.regime_id==key[2])].itertuples(index=False):
  a=aid.loc[key+(r.policy_variant_id,)];col={'reference':'M_reference','uniform':'M_low','possible':'M_high'}[r.mode]
  vals=z.g*z[col]-(1 if r.rule=='B0' else 1.1)*a.benefits-(a.spb if r.rule=='B2' else 0)
  qq=np.quantile(vals,[.05,.5,.95]);assert np.allclose(qq,[r.Fmax_p05,r.Fmax_p50,r.Fmax_p95],atol=2e-12,rtol=1e-11)
  assert int((vals>=a.F_recurring_author).sum())==r.recurring_author_crossings
  assert int((vals>=0).sum())==r.nonnegative_frontier_count
  admin=admins.loc[(r.country_id,a.policy_id)]
  drawcost=admin.admin_cost_new_gdp-admin.admin_savings_existing_gdp+admin.transition_recurring_gdp+admin.leakage_fixed_gdp*z.leakage_multiplier
  assert int((vals>=drawcost).sum())==r.registered_leakage_crossings
oldmc=pd.read_csv(N/'resultados/MONTE_CARLO_5000_TODAS_CELDAS.csv')
oldmc=oldmc[(oldmc.timing=='endpoint_without_setup_obligation')&oldmc['mode'].isin(['reference','uniform','possible'])]
joined=oldmc.merge(mc,on=['country_id','scenario_id','regime_id','policy_variant_id','mode','rule'],validate='one_to_one')
assert len(joined)==2880;assert (joined.crossings==joined.registered_leakage_crossings).all()

loans=pd.read_csv(O/'PRESTAMOS_INSTALACION_3_ANOS.csv')
for key,z in loans.groupby(['country_id','policy_id']):
 assert abs(z.principal_nominal_gdp0.sum()-z.setup_author.iloc[0])<2e-12
 assert abs(z.closing_nominal_gdp0.iloc[-1])<2e-12
 assert np.allclose(z.interest_nominal_gdp0+z.principal_nominal_gdp0,z.payment_nominal_gdp0,atol=2e-12)

manifest={'status':'PASS','independent_oracle_imports_candidate':False,'decimal_fiscal_flow_checks':count,'max_fiscal_abs_error':max(errors),'inverse_rows':len(inv),'root_substitutions':roots,'max_root_abs_error':max(root_errors),'financing_rows_nominal_oracle':len(fp),'financing_paths':ngroups,'max_financing_abs_error':max(finerr),'max_frontier_identity_error':max(frontiererr),'max_initial_capital_error':max(initialerr),'horizon_rows_reenumerated':hcount,'transition_frontier_rows':len(ff),'MC_rows_reaggregated':len(mc),'prior_MC_rows_exact_counts':len(joined),'loan_rows':len(loans),'conditional_model_only':True}
(E/'VERIFICACION_INDEPENDIENTE.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(manifest,ensure_ascii=False),flush=True)
