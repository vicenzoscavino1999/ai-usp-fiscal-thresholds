from pathlib import Path
import sys,os,json,copy,time
sys.dont_write_bytecode=True
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
ROOT=Path(__file__).resolve().parents[3];B=ROOT/'revision_jpm_v2';O=ROOT/'extensions/convergence/resultados'
sys.path.insert(0,str(B/'paso_07d/costos_transicion_03/scripts'))
import common03 as cm
import numpy as np,pandas as pd
cf=cm.cf;start=time.perf_counter();rows=[];checks=[]
annual=pd.read_csv(B/'paso_07d/costos_transicion_03/resultados/FRONTERAS_ANUALES_480.csv')
cases=pd.read_csv(B/'paso_07e/resultados/CASOS_PUBLICABLES.csv')
K=['country_id','scenario_id','regime_id','policy_variant_id']
headline=set(map(tuple,cases[K].values))
grd=cf.x['grd_revenue_contrast'];sources=[];factors={}
for c in cf.ta.COUNTRIES:
 z=grd[grd.country_id.eq(c)&grd.government_level.eq('general_government')].copy()
 ok=z.grd_tax_including_sc_gdp.between(.01,.6)&z.oecd_tax_including_sc_gdp.between(.01,.6)
 v=z[ok];factor=None;year=None
 if len(v):
  year=int(v.year.max());latest=v[v.year.eq(year)]
  unique=latest[['grd_tax_including_sc_gdp','oecd_tax_including_sc_gdp']].drop_duplicates()
  if len(unique)==1:
   factor=float(unique.iloc[0,0]/unique.iloc[0,1]);factors[c]=factor;status='AVAILABLE_AGGREGATE_CONTRAST'
  else:status='AMBIGUOUS_LATEST_YEAR'
 else:status='UNAVAILABLE_COMPARABLE_GENERAL_GOVERNMENT'
 sources.append(dict(country_id=c,status=status,matched_year=year,ratio_grd_oecd=factor,total_candidate_rows=len(z),excluded_missing_or_implausible=int((~ok).sum()),latest_unique_value_pairs=len(unique) if len(v) else 0,grd_tax_including_sc_gdp=float(unique.iloc[0,0]) if factor is not None else None,oecd_tax_including_sc_gdp=float(unique.iloc[0,1]) if factor is not None else None,role='aggregate ratio only; tax composition and current economic inputs held fixed; not a complete OECD-free rebuild'))
pd.DataFrame(sources).to_csv(O/'COBERTURA_CONTRASTE_GRD.csv',index=False)

def check(name,value,**detail):
 checks.append(dict(check=name,passed=bool(value),**detail))
 if not value:raise AssertionError((name,detail))

def evalp(p,coef):return float(cf.evaluate(p,alpha_pit_k=coef[0],k_w=coef[1],k_n=coef[2])['revenue'])

for c in cf.ta.COUNTRIES:
 for sc in cf.ta.SCENARIOS:
  for reg in cf.ta.REGIMES:
   ctx=cm.context(c,sc,reg);coef=ctx['reference'];p=ctx['prepared'];base=float(cm.capture(ctx,coef)['revenue'])
   check('capture_vs_channels:'+':'.join((c,sc,reg)),abs(base-evalp(p,coef))<2e-12)
   noai=cm.capture(ctx,coef,q=0.,g=0.);zero_g=cm.capture(ctx,coef,g=0.)
   check('joint_no_AI:'+':'.join((c,sc,reg)),float(noai['revenue'])==0. and float(noai['dw'])==0. and np.isnan(noai['M_average']))
   low=cm.capture(ctx,coef,exposure=.035)
   variations={'baseline':base,'joint_no_AI':float(noai['revenue']),'zero_growth_distribution_retained':float(zero_g['revenue']),'low_exposure_0035':float(low['revenue'])}
   for label,changes in [('without_labor',{'ul':0.}),('without_capital',{'uk':0.}),('without_AI',{'ai':0.}),('without_VAT',{'vat_yield':0.}),('without_all_taxes',{'ul':0.,'uk':0.,'ai':0.,'vat_yield':0.})]:
    variations[label]=evalp({**p,**changes},coef)
   check('all_taxes_zero:'+':'.join((c,sc,reg)),variations['without_all_taxes']==0.)
   check('no_AI_channel_feedback:'+':'.join((c,sc,reg)),abs(variations['without_AI']-float(cm.capture(ctx,coef,tau=0.)['revenue']))<2e-12)
   if c in factors:
    alt={**p,**{k:p[k]*factors[c] for k in ['pit','cit','ssc','vat_yield']}}
    variations['aggregate_GRD_contrast']=evalp(alt,coef)
   for r in annual.query('country_id==@c and scenario_id==@sc and regime_id==@reg').itertuples():
    key=dict(zip(K,[c,sc,reg,r.policy_variant_id]));req=1.1*r.benefits+r.spb
    check('baseline_frontier:'+'|'.join(key.values()),abs(base-req-r.Fmax_B2_reference)<2e-12)
    admin=cf.x['policy_admin_transition_cost'].query('country_id==@c and policy_id==@r.policy_id').iloc[0]
    high_f=float(admin.admin_cost_new_gdp-admin.admin_savings_existing_gdp+admin.transition_recurring_gdp+admin.leakage_fixed_gdp)
    if ctx['leak_multiplier']<=1:check('leakage_monotonic:'+'|'.join(key.values()),high_f>=r.F_recurring_author-1e-14)
    for diagnostic,revenue in {**variations,'leakage_multiplier_1':base}.items():
     f=high_f if diagnostic=='leakage_multiplier_1' else r.F_recurring_author
     margin=revenue-req-f
     rows.append(dict(**key,diagnostic=diagnostic,headline=tuple(key.values()) in headline,revenue=revenue,revenue_change=revenue-base,benefits=r.benefits,spb=r.spb,F_recurring=f,Fmax_B2=revenue-req,margin_B2=margin,covers_B2=margin>=0.,baseline_margin_B2=base-req-r.F_recurring_author,baseline_covers_B2=base>=req+r.F_recurring_author,low_exposure_g=float(low['g']) if diagnostic=='low_exposure_0035' else None))

d=pd.DataFrame(rows);d['classification_changed']=d.covers_B2!=d.baseline_covers_B2
# Rank four countries only within like scenario/regime/policy, in GDP-share margin.
group=['diagnostic','scenario_id','regime_id','policy_variant_id']
d['country_rank']=d.groupby(group).margin_B2.rank(method='min',ascending=False)
baseline=d.query("diagnostic=='baseline'")[K+['country_rank']].rename(columns={'country_rank':'baseline_country_rank'})
d=d.merge(baseline,on=K,validate='many_to_one');d['rank_change']=d.country_rank-d.baseline_country_rank
# A source rank comparison must cover all four countries; do not compare partial ranks.
sizes=d.groupby(group).country_id.transform('nunique');d.loc[sizes<4,['country_rank','rank_change']]=np.nan
d.to_csv(O/'DIAGNOSTICOS_ACTUALES_480.csv',index=False)
summ=[]
for (name,scope),z in d.assign(scope=np.where(d.scenario_id.eq('stress'),'stress','nonstress')).groupby(['diagnostic','scope']):
 summ.append(dict(diagnostic=name,scope=scope,cells=len(z),crossings_B2=int(z.covers_B2.sum()),changed_class=int(z.classification_changed.sum()),max_abs_rank_change=float(z.rank_change.abs().max()) if z.rank_change.notna().any() else None))
pd.DataFrame(summ).to_csv(O/'RESUMEN_DIAGNOSTICOS.csv',index=False)
hd=d[d.headline];hd.to_csv(O/'DIAGNOSTICOS_SIETE_CASOS.csv',index=False)
negative=hd.query("diagnostic=='low_exposure_0035'")
report=dict(execution_status='PASS',algebra_checks=len(checks),all_checks_passed=all(x['passed'] for x in checks),distinct_policy_cells=len(annual),diagnostic_rows=len(d),zero_AI_anchor='PASS',all_taxes_zero='PASS',low_exposure_no_headline_B2_crossing='PASS' if not negative.covers_B2.any() else 'FAIL',low_exposure_surviving_headline_B2=int(negative.covers_B2.sum()),aggregate_source_countries=list(factors),aggregate_source_class_changes=int(d.query("diagnostic=='aggregate_GRD_contrast'").classification_changed.sum()),full_Tier_D_status='PARTIAL_NOT_CERTIFIED',elapsed_seconds=time.perf_counter()-start,scientific_equations_changed=False)
(O/'CHECKS_DIAGNOSTICOS.json').write_text(json.dumps(checks,indent=2)+'\n')
(O/'RESUMEN_DIAGNOSTICOS.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
