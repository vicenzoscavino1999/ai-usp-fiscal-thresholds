from common03 import *
import json,hashlib,time
start=time.perf_counter()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
# Retained local UN-WPP source has the years required beyond the input slice.
src=R/'paso_03/candidato_corregido/ai-usp-fiscal-thresholds/data/raw_snapshots/v1.1.0-official-4c/wpp/wpp_projections.parquet'
wpp=pd.read_parquet(src);wpp=wpp[wpp.ISO3_code.isin(cf.ta.COUNTRIES)&wpp.Time.between(2024,2049)].copy()
oldw=cf.x['wpp'];keys=['ISO3_code','Time','AgeGrpStart']
z=oldw.merge(wpp,on=keys,suffixes=('_old','_full'),validate='one_to_one')
assert len(z)==len(oldw)
for col in ['PopTotal','PopMale','PopFemale']:assert np.array_equal(z[col+'_old'],z[col+'_full'])
wpp.to_parquet(E/'wpp_2024_2049.parquet',index=False)
(E/'FUENTE_DEMOGRAFICA.json').write_text(json.dumps({'source':str(src),'source_sha256':sha(src),'slice_sha256':sha(E/'wpp_2024_2049.parquet'),'years':[2024,2049],'old_slice_rows_exact':len(z),'new_external_download':False},indent=2)+'\n')
debt=pd.read_parquet(E/'debt_guardrail_anchor.parquet').query('year==2024').set_index('country_id')
prior=pd.read_csv(N/'resultados/DETERMINISTA_CONCILIADO_960.csv').query("timing=='endpoint_without_setup_obligation'").set_index(['country_id','scenario_id','regime_id','policy_variant_id'])
channels=[];annual=[];inverses=[];horizons=[];finframes=[];finfront=[];schedules=[];colombia=[];contexts=[]
years=np.arange(1,26);rules={'B0':(0.,False),'B1':(.1,False),'B2':(.1,True)}

def first(mask):
    z=np.flatnonzero(mask);return int(z[0]+1) if len(z) else None
def persistent(mask):return first(np.logical_and.accumulate(np.asarray(mask)[::-1])[::-1])

for country in cf.ta.COUNTRIES:
 dr=debt.loc[country];interest=float(dr.nominal_interest_rate);growth=float(dr.nominal_growth_rate);spb=cf.value('sPB_plus_gdp_ratio',country=country)
 assert abs(spb-max(0,(interest-growth)/(1+growth)*dr.gross_debt_gdp/100-dr.primary_balance_gdp/100))<1e-12
 for sc in cf.ta.SCENARIOS:
  for reg in cf.ta.REGIMES:
   ctx=context(country,sc,reg);modes={'reference':ctx['reference'],**{f'v{i}':v for i,v in enumerate(VERTICES)}}
   rev={k:np.asarray(capture(ctx,v,years=years)['revenue']) for k,v in modes.items()}
   gain=np.asarray(capture(ctx,ctx['reference'],years=years)['g']);vr=np.array([rev[f'v{i}'] for i in range(8)])
   rev['uniform']=vr.min(axis=0);rev['possible']=vr.max(axis=0)
   contexts.append({'country_id':country,'scenario_id':sc,'regime_id':reg,'context':ctx})
   for j,t in enumerate(years):
    channels.append({'country_id':country,'scenario_id':sc,'regime_id':reg,'H':t,'g':gain[j],**{f'revenue_{k}':v[j] for k,v in rev.items()},**{f'M_{k}':v[j]/gain[j] for k,v in rev.items()}})
   for pol in cf.policies(country):
    key={'country_id':country,'scenario_id':sc,'regime_id':reg,'policy_id':pol['policy_id'],'policy_variant_id':pol['policy_variant_id']}
    c=cost_path(country,pol,wpp);f,I,ann=costs(country,pol['policy_id'],ctx)
    pr=prior.loc[(country,sc,reg,pol['policy_variant_id'])]
    assert abs(c[9]-pr.benefits)<1e-13
    assert abs(f-pr.F)<1e-13
    for mode,saved in [('reference','reference'),('uniform','low'),('possible','high')]:
     assert abs(rev[mode][9]-pr['M_'+saved]*pr.g)<2e-12
    row={**key,'H':10,'g':gain[9],'benefits':c[9],'F_recurring_author':f,'setup_author':I,'annuity_author_comparator':ann,'spb':spb}
    for rule,(xi,addspb) in rules.items():
     req=(1+xi)*c+(spb if addspb else 0)
     for mode,r in rev.items():
      fmax=r-req
      if mode in ['reference','uniform','possible']:
       row[f'Fmax_{rule}_{mode}']=fmax[9];row[f'covers_recurring_{rule}_{mode}']=bool(fmax[9]>=f);row[f'covers_equivalent_{rule}_{mode}']=bool(fmax[9]>=f+ann)
      hit=r>=req+f
      horizons.append({**key,'rule':rule,'mode':mode,'H_star_recurring':first(hit),'H_persistent_to25':persistent(hit) if mode!='possible' else None,'crossing_years':';'.join(str(t) for t in years[hit]),'censored_no_crossing_1_25':not hit.any(),'mode_role':'pointwise possibility; not one coefficient path' if mode=='possible' else ('all coefficients at this year' if mode=='uniform' else 'fixed coefficients')})
     for label,F in [('recurring_author',f),('annual_equivalent_comparator',f+ann)]:
      required=req[9]+F
      for mode,coef in modes.items():
       inv={**key,'rule':rule,'cost_treatment':label,'mode':mode,'alpha':coef[0],'k_w':coef[1],'k_n':coef[2],'required_revenue':required,'g_registered':gain[9],'M_required':required/gain[9],**invert_gain(ctx,coef,required),**invert_ai(ctx,coef,required)}
       for var in ['q','exposure']:
        d=invert_operational(ctx,coef,required,var)
        inv.update({var+'_'+k:v for k,v in d.items()})
       qreq=inv['q_required'];lam=ctx['lambda_q']
       quse=(qreq-(1-lam)*ctx['q'])/lam if np.isfinite(qreq) and lam>0 else np.nan
       inv['q_use_required_one_step']=quse;inv['q_use_within_ceiling']=bool(np.isfinite(quse) and quse<=ctx['q_bar']-ctx['epsilon_mu']+1e-12)
       inverses.append(inv)
    annual.append(row)
    # Two explicit investment schedules; terminal investment at t=H is included.
    for replacement in ['none','every3_author_sensitivity']:
     rep=np.zeros(25) if replacement=='none' else np.where(years%3==0,I,0.)
     for budget in ['cash','B2_reserved']:
      commit=c if budget=='cash' else 1.1*c+spb
      runs={m:financing(rev[m],commit,f,I,interest,growth,rep) for m in modes}
      for m,z in runs.items():
       finframes.append(pd.DataFrame({**key,'mode':m,'budget':budget,'replacement':replacement,'H':years,'g':gain,'benefits':c,'commitments_before_f':commit,'F_recurring_author':f,'setup_author':I,'investment':rep,'revenue':rev[m],'interest':interest,'nominal_growth':growth,'balance_ratio_noAI':z['balance'],'balance_ratio_withAI':z['balance']/(1+gain),'Fmax_path':z['fmax'],'initial_capital_gdp0':z['initial_capital'],'net_primary_cost':z['net_primary']}))
      for H in [10,25]:
       j=H-1;vals=np.array([runs[f'v{i}']['fmax'][j] for i in range(8)]);r0=runs['reference']
       capvals=[runs[f'v{i}']['initial_capital'][j] for i in range(8)]
       # Max of coordinatewise convex prefix balances attains a vertex maximum.
       finfront.append({**key,'H':H,'budget':budget,'replacement':replacement,'F_recurring_author':f,'setup_author':I,'Fmax_path_reference':r0['fmax'][j],'Fmax_path_uniform':vals.min(),'Fmax_path_possible':vals.max(),'initial_capital_reference_gdp0':r0['initial_capital'][j],'initial_capital_worst_domain_gdp0':max(capvals),'balance_reference_noAI':r0['balance'][j],'balance_reference_withAI':r0['balance'][j]/(1+gain[j]),'peak_balance_reference_noAI':max(I,float(r0['balance'][:H].max()),0.),'H_return_reference':first(r0['balance'][:H]<=0),'H_return_persistent_to_H':persistent(r0['balance'][:H]<=0),'return_by_H_reference':bool(r0['balance'][j]<=0)})
    if country=='COL' and pol['policy_id']=='PEN':
     hc=cost_path(country,pol,wpp,harmonized=True)
     for mode in ['reference','uniform','possible']:
      hit=rev[mode]>=1.1*hc+spb+f
      colombia.append({**key,'mode':mode,'cost10_recorded':c[9],'cost10_harmonized':hc[9],'H_star_recorded':first(rev[mode]>=1.1*c+spb+f),'H_star_harmonized':first(hit),'Fmax10_B2_harmonized':rev[mode][9]-1.1*hc[9]-spb})
 print('Completed country',country,flush=True)
 for policy in cf.ta.POLICIES:
  ctx=context(country,'mid','r0');f,I,ann=costs(country,policy,ctx)
  for r in annuity_schedule(I,interest,growth):schedules.append({'country_id':country,'policy_id':policy,'setup_author':I,'interest_scenario':interest,'growth_scenario':growth,'old_equivalent_annuity':ann,**r})

ad=pd.DataFrame(annual);ad.to_csv(O/'FRONTERAS_ANUALES_480.csv',index=False)
pd.DataFrame(channels).to_csv(O/'CANALES_HORIZONTES_2000.csv',index=False)
pd.DataFrame(inverses).to_csv(O/'INVERSAS_RECALCULADAS.csv',index=False)
pd.DataFrame(horizons).to_csv(O/'HORIZONTES_RECALCULADOS.csv',index=False)
pd.concat(finframes,ignore_index=True).to_parquet(O/'SENDAS_FINANCIACION.parquet',index=False)
pd.DataFrame(finfront).to_csv(O/'FRONTERAS_TRANSICION.csv',index=False)
pd.DataFrame(schedules).to_csv(O/'PRESTAMOS_INSTALACION_3_ANOS.csv',index=False)
pd.DataFrame(colombia).to_csv(O/'SENSIBILIDAD_PENSION_COLOMBIA.csv',index=False)
(E/'CONTEXTOS_80.json').write_text(json.dumps(contexts,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
# Conditional quantiles of an unknown-cost frontier; no cost distribution.
draws=pd.read_parquet(N/'resultados/SORTEOS_CONCILIADOS_80x5000.parquet');mcrows=[]
for keys,z in draws.groupby(['country_id','scenario_id','regime_id'],sort=False):
 country,sc,reg=keys
 for _,r in ad[(ad.country_id==country)&(ad.scenario_id==sc)&(ad.regime_id==reg)].iterrows():
  admin=cf.x['policy_admin_transition_cost'].query('country_id==@country and policy_id==@r.policy_id').iloc[0]
  registered_F=admin.admin_cost_new_gdp-admin.admin_savings_existing_gdp+admin.transition_recurring_gdp+admin.leakage_fixed_gdp*z.leakage_multiplier
  for rule,(xi,addspb) in rules.items():
   req=(1+xi)*r.benefits+(r.spb if addspb else 0)
   for mode,col in [('reference','M_reference'),('uniform','M_low'),('possible','M_high')]:
    fmax=z.g*z[col]-req;qq=np.quantile(fmax,[.05,.5,.95]);hit=fmax>=r.F_recurring_author
    inherited_hit=fmax>=registered_F
    mcrows.append({'country_id':country,'scenario_id':sc,'regime_id':reg,'policy_variant_id':r.policy_variant_id,'rule':rule,'mode':mode,'n':len(z),'Fmax_p05':qq[0],'Fmax_p50':qq[1],'Fmax_p95':qq[2],'nonnegative_frontier_count':int((fmax>=0).sum()),'recurring_author_crossings':int(hit.sum()),'recurring_author_frequency':float(hit.mean()),'registered_leakage_crossings':int(inherited_hit.sum()),'registered_leakage_frequency':float(inherited_hit.mean()),'interpretation':'conditional frequency; recurring_author fixes f; registered_leakage preserves the previous regime leakage draws' if mode=='reference' else 'pointwise frequency bound; not a probability distribution on unknown coefficients'})
pd.DataFrame(mcrows).to_csv(O/'FRONTERAS_MC_5000.csv',index=False)
summary=ad.assign(domain=np.where(ad.scenario_id.eq('stress'),'stress','nonstress')).groupby('domain').agg(cells=('H','size'),recurring_B2_reference=('covers_recurring_B2_reference','sum'),recurring_B2_uniform=('covers_recurring_B2_uniform','sum'),recurring_B2_possible=('covers_recurring_B2_possible','sum'),equivalent_B2_reference=('covers_equivalent_B2_reference','sum')).reset_index();summary.to_csv(O/'RESUMEN_ANUAL.csv',index=False)
manifest={'status':'PASS','elapsed_seconds':time.perf_counter()-start,'annual_cells':len(annual),'channel_years':len(channels),'inverse_rows':len(inverses),'horizon_rows':len(horizons),'financing_rows':sum(len(z) for z in finframes),'transition_frontier_rows':len(finfront),'MC_frontier_rows':len(mcrows),'design_sha256':sha(T/'DISENO_PREVIO.md'),'matches_prior_endpoint':480,'calibration_changed':False,'paper_changed':False}
(E/'EJECUCION.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(summary.to_string(index=False));print(json.dumps(manifest,ensure_ascii=False),flush=True)
