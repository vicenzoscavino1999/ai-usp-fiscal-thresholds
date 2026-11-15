"""Read-only scientific inputs; current coverage and legacy-claim evidence."""
from pathlib import Path
import sys,json,itertools,os
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3];B=ROOT/'revision_jpm_v2';O=ROOT/'extensions/scope/resultados';O.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(B/'paso_07d/costos_transicion_03/scripts'))
import common03 as cm
import pandas as pd,numpy as np
cf=cm.cf
x=pd.read_csv(B/'paso_07d/costos_transicion_03/resultados/FRONTERAS_ANUALES_480.csv')
keys=['country_id','scenario_id','regime_id','policy_variant_id'];checks=[]
def check(label,v,**facts):
 checks.append(dict(check=label,passed=bool(v),**facts))
 if not v:raise AssertionError((label,facts))
check('480_unique_cells',len(x)==480 and not x.duplicated(keys).any())
z=x[keys+['policy_id','H','benefits','F_recurring_author','spb']].copy()
for mode in ['reference','uniform','possible']:
 z['Fmax_B2_'+mode]=x['Fmax_B2_'+mode]
 z['margin_B2_'+mode]=x['Fmax_B2_'+mode]-x.F_recurring_author
 z['covers_B2_'+mode]=z['margin_B2_'+mode]>=0
 check('stored_flags:'+mode,np.array_equal(z['covers_B2_'+mode],x['covers_recurring_B2_'+mode]))
check('domain_encloses_reference',((~z.covers_B2_uniform|z.covers_B2_reference)&(~z.covers_B2_reference|z.covers_B2_possible)).all())
z['coverage_class']=np.select([z.covers_B2_uniform,z.covers_B2_possible],['uniform_within_declared_domain','possible_not_uniform'],default='no_crossing_within_declared_domain')
z['reference_class']=np.where(z.covers_B2_reference,'reference_crosses','reference_does_not_cross')
z['scenario_role']=np.where(z.scenario_id=='stress','disruptive_stress','nonstress')
z['scope']='H=10; B2; recurring author F; fixed 2024 macro; alpha [0,.3], kW/kN [0,1]; not long-run or financing certification'
z.to_csv(O/'CLASIFICACION_COBERTURA_V2_480.csv',index=False)
summary=[]
for (c,pol),a in z.groupby(['country_id','policy_variant_id'],sort=False):
 r=dict(country_id=c,policy_variant_id=pol)
 for role,b in a.groupby('scenario_role'):
  r[role+'_cells']=len(b)
  for mode in ['reference','uniform','possible']:r[role+'_'+mode+'_crossings']=int(b['covers_B2_'+mode].sum())
 r['interpretation']='counts within evaluated menu; variants retained; no legacy robust/fragile label'
 summary.append(r)
pd.DataFrame(summary).to_csv(O/'COBERTURA_PAIS_VARIANTE_24.csv',index=False)
check('24_country_policy_variants',len(summary)==24)
nominal=[];monotonic=[]
for (c,sc,reg),a in x.groupby(['country_id','scenario_id','regime_id'],sort=False):
 a=a.set_index('policy_variant_id');R=(a.Fmax_B2_reference+1.1*a.benefits+a.spb).to_numpy()
 check(f'common_receipts:{c}:{sc}:{reg}',np.ptp(R)<2e-12)
 for pi,pj in itertools.combinations(a.index,2):
  u,v=a.loc[pi],a.loc[pj];cu=1.1*u.benefits+u.F_recurring_author+u.spb;cv=1.1*v.benefits+v.F_recurring_author+v.spb
  mu=u.Fmax_B2_reference-u.F_recurring_author;mv=v.Fmax_B2_reference-v.F_recurring_author
  monotonic.append(dict(country_id=c,scenario_id=sc,regime_id=reg,policy_a=pi,policy_b=pj,commitment_a=cu,commitment_b=cv,margin_difference=mu-mv,commitment_difference=cu-cv,identity_error=(mu-mv)+(cu-cv)))
 if sc=='mid':
  for gmi in ['GMI:GMI_ideal_aggregate','GMI:GMI_loaded_aggregate']:
   for pi,pj in [('PEN',gmi),('MUT',gmi),(gmi,'PBI'),('PBI','UBI')]:
    u,v=a.loc[pi],a.loc[pj]
    nominal.append(dict(country_id=c,regime_id=reg,gmi_variant=gmi,expected_cheaper=pi,expected_dearer=pj,benefit_cost_a=u.benefits,benefit_cost_b=v.benefits,benefit_order_holds=u.benefits<=v.benefits,commitment_a=1.1*u.benefits+u.F_recurring_author+u.spb,commitment_b=1.1*v.benefits+v.F_recurring_author+v.spb))
pd.DataFrame(nominal).to_csv(O/'H1_ORDEN_NOMINAL_POLITICAS.csv',index=False)
pd.DataFrame(monotonic).to_csv(O/'H1_MONOTONICIDAD_COMPROMISO.csv',index=False)
check('H1_cost_identity',max(abs(v['identity_error']) for v in monotonic)<2e-12)
base=z.query("regime_id=='r0'").set_index(['country_id','scenario_id','policy_variant_id'])
regrows=[]
for r in z.query("regime_id!='r0'").itertuples():
 a=base.loc[(r.country_id,r.scenario_id,r.policy_variant_id)]
 regrows.append(dict(country_id=r.country_id,scenario_id=r.scenario_id,regime_id=r.regime_id,policy_variant_id=r.policy_variant_id,margin_B2_r0=a.margin_B2_reference,margin_B2_regime=r.margin_B2_reference,delta_margin=r.margin_B2_reference-a.margin_B2_reference,r0_crosses=bool(a.covers_B2_reference),regime_crosses=bool(r.covers_B2_reference),gained_crossing=not a.covers_B2_reference and r.covers_B2_reference,lost_crossing=a.covers_B2_reference and not r.covers_B2_reference))
pd.DataFrame(regrows).to_csv(O/'H4_COMPARACION_REGIMENES_384.csv',index=False)
# Adoption-side removal only. No invented informal-tax response is supplied.
class WithoutInformality(cf.Central):
 def array(self,name,**kw):
  if name=='I_adopt_informality':return np.zeros(1)
  return super().array(name,**kw)
h3=[]
for c in cf.ta.COUNTRIES:
 for sc in cf.ta.SCENARIOS:
  ca=cf.Central();cb=WithoutInformality()
  a=cf.mc.build_country_scenario_draws(ca,cf.x,c,sc,ca.array('E_prod_frontier'))
  b=cf.mc.build_country_scenario_draws(cb,cf.x,c,sc,cb.array('E_prod_frontier'))
  for reg in cf.ta.REGIMES:
   rd=cf.mc.build_regime_draws(ca,reg);pa,ra,*_=cf.build(ca,c,sc,reg,a,rd,cf.policies(c)[0]);pb,rb,*_=cf.build(cb,c,sc,reg,b,rd,cf.policies(c)[0])
   s=lambda a:float(np.asarray(a).ravel()[0])
   h3.append(dict(country_id=c,scenario_id=sc,regime_id=reg,informality_original=s(a['informality']),q_bar_original=s(a['q_bar']),q_bar_without_informality=s(b['q_bar']),q_original=s(a['q_prod']),q_without_informality=s(b['q_prod']),g_original=s(a['g_ai_level']),g_without_informality=s(b['g_ai_level']),revenue_original=s(ra['revenue']),revenue_without_informality=s(rb['revenue']),fiscal_counterfactual_identified=False))
h=pd.DataFrame(h3);h['revenue_change']=h.revenue_without_informality-h.revenue_original
h.to_csv(O/'H3_MARGEN_ADOPCION_80.csv',index=False)
summary=dict(status='PASS',source_policy_cells=480,policy_variant_summaries=len(summary),coverage_counts=z.groupby('scenario_role')[['covers_B2_reference','covers_B2_uniform','covers_B2_possible']].sum().to_dict('index'),H1_named_order_pairs=len(nominal),H1_named_order_holds=sum(bool(v['benefit_order_holds']) for v in nominal),H1_commitment_monotonicity_pairs=len(monotonic),H4_gained_crossings=sum(bool(v['gained_crossing']) for v in regrows),H4_lost_crossings=sum(bool(v['lost_crossing']) for v in regrows),H3_max_abs_revenue_change=float(h.revenue_change.abs().max()),H3_max_abs_q_change=float((h.q_without_informality-h.q_original).abs().max()),H3_fiscal_counterfactual_identified=False,checks=len(checks),new_stochastic_draws=False,model_modified=False)
(O/'VERIFICACION_DERIVACIONES.json').write_text(json.dumps({'summary':summary,'checks':checks},indent=2)+'\n')
print(json.dumps(summary,indent=2))
