from pathlib import Path
import json,hashlib,shutil
import numpy as np,pandas as pd
from scipy.stats import beta
R=Path(__file__).resolve().parents[3];P=R.parent;S=R/'paso_07e';D=R/'paso_07d';T=D/'costos_transicion_03';N=D/'conciliacion_fiscal_02';W=Path(__file__).parent;O=S/'resultados';I=W/'inputs'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
annual=pd.read_csv(I/'FRONTERAS_ANUALES_480.csv');annual['R_reference']=annual.Fmax_B0_reference+annual.benefits
oldpath=R/'paso_04/evidencia/SORTEOS_EMPAREJADOS.parquet';newpath=N/'resultados/SORTEOS_CHILE_50000.parquet'
old=pd.read_parquet(oldpath);new=pd.read_parquet(newpath)
assert len(old)==len(new)==50000 and np.array_equal(old.draw_id,new.draw_id) and np.array_equal(old.g_ai_level,new.g)
cell=annual[(annual.country_id=='CHL')&(annual.scenario_id=='mid')&(annual.regime_id=='r0')&(annual.policy_variant_id=='GMI:GMI_ideal_aggregate')].iloc[0]
assert cell.spb==0 and abs(new.benefits.iloc[0]-cell.benefits)<1e-14
captures={'reference':new.M_reference,'uniform_bound':new.M_low,'possible_bound':new.M_high}
captures.update({c[len('mfc__'):]:old[c] for c in old.columns if c.startswith('mfc__') and c!='mfc__structural'})
rows=[];freq={}
for mode,M in captures.items():
 for rule,mult in [('B0',1.),('B2',1.1)]:
  hit=np.isfinite(M)&(new.g*M-cell.F_recurring_author>=mult*cell.benefits+cell.spb);k=int(hit.sum());n=len(hit)
  rows.append({'mode':mode,'rule':rule,'n':n,'crossings':k,'frequency':k/n,'mc95_low':0 if k==0 else beta.ppf(.025,k,n-k+1),'mc95_high':1 if k==n else beta.ppf(.975,k+1,n-k),'M_p50':float(np.median(M)),'F_recurring':cell.F_recurring_author,'benefits':cell.benefits,'role':'conditional channel reference' if mode=='reference' else ('pointwise bound not a probability over unknown coefficients' if mode.endswith('_bound') else 'external historical comparator not AI causal')})
  freq[(mode,rule)]=k/n
hist=pd.DataFrame(rows);hist.to_csv(O/'COMPARADORES_CAPTURA_ACTUALIZADOS.csv',index=False)
previous=pd.read_csv(N/'resultados/CHILE_EMPAREJADO_50000.csv');previous=previous[previous.timing.eq('endpoint_without_setup_obligation')]
for mode,oldmode in [('reference','reference'),('uniform_bound','uniform'),('possible_bound','possible')]:
 for rule in ['B0','B2']:
  k=hist[(hist['mode']==mode)&hist.rule.eq(rule)].crossings.iloc[0];pk=previous[(previous['mode']==oldmode)&previous.rule.eq(rule)].crossings.iloc[0];assert k==pk
macro=pd.read_csv(R/'paso_04/MACROESCENARIOS_CONJUNTOS_40.csv')
mr=annual.merge(macro,on='country_id',validate='many_to_many');assert len(mr)==4800
mr['Fmax_B2_macro_reference']=mr.R_reference-1.1*mr.benefits-mr.spb_variant
mr['covers_B2_macro_reference']=mr.F_recurring_author<=mr.Fmax_B2_macro_reference
assert (mr.loc[mr.macro_year.eq(2024),'covers_B2_macro_reference']==mr.loc[mr.macro_year.eq(2024),'covers_recurring_B2_reference']).all()
keys=['country_id','scenario_id','regime_id','policy_variant_id']
mr[keys+['macro_year','spb_variant','Fmax_B2_macro_reference','F_recurring_author','covers_B2_macro_reference']].to_csv(O/'MACROESCENARIOS_ACTUALIZADOS_4800.csv',index=False)
ms=mr.groupby(keys,sort=False).agg(n=('macro_year','size'),B2_pass=('covers_B2_macro_reference','sum'),Fmax_min=('Fmax_B2_macro_reference','min'),Fmax_max=('Fmax_B2_macro_reference','max')).reset_index();ms.to_csv(O/'RESUMEN_MACROESCENARIOS.csv',index=False)
selected=[('CHL','GMI:GMI_ideal_aggregate','mid','r0'),('CHL','GMI:GMI_ideal_aggregate','mid','r4'),('CHL','GMI:GMI_ideal_aggregate','stress','r0'),('PER','PEN','stress','r0'),('PER','PEN','stress','r4'),('COL','PEN','stress','r4'),('MEX','GMI:GMI_ideal_aggregate','stress','r4')]
inv=pd.read_csv(I/'INVERSAS_RECALCULADAS.csv');hh=pd.read_csv(I/'HORIZONTES_RECALCULADOS.csv');ff=pd.read_csv(I/'FRONTERAS_TRANSICION.csv');samples=[]
for country,policy,sc,reg in selected:
 mask=lambda z:(z.country_id==country)&(z.policy_variant_id==policy)&(z.scenario_id==sc)&(z.regime_id==reg)
 r=annual[mask(annual)].iloc[0].to_dict();rv=inv[mask(inv)&inv.rule.eq('B2')&inv.cost_treatment.eq('recurring_author')&inv['mode'].eq('reference')].iloc[0]
 r.update({'g_required':rv.g_required,'M_required':rv.M_required,'T_required_frozen_distribution':rv.T_required_frozen_distribution,'gain_status':rv.gain_status,'q_required':rv.q_required,'q_status':rv.q_status,'tau_ai_required':rv.tau_ai_required,'ai_status':rv.ai_status})
 for rule in ['B0','B1','B2']:r['H_'+rule]=hh[mask(hh)&hh['mode'].eq('reference')&hh.rule.eq(rule)].H_star_recurring.iloc[0]
 for H in [10,25]:
  for budget in ['cash','B2_reserved']:
   z=ff[mask(ff)&ff.budget.eq(budget)&ff.replacement.eq('none')&ff.H.eq(H)].iloc[0]
   for col in ['Fmax_path_reference','balance_reference_noAI','H_return_reference','initial_capital_reference_gdp0']:r[f'{col}_{budget}_{H}']=z[col]
 r['macro_B2_pass']=ms[mask(ms)].B2_pass.iloc[0];samples.append(r)
sel=pd.DataFrame(samples);sel.to_csv(O/'CASOS_PUBLICABLES.csv',index=False)
summary=annual.assign(domain=np.where(annual.scenario_id.eq('stress'),'stress','nonstress')).groupby('domain').agg(cells=('H','size'),B0_reference=('covers_recurring_B0_reference','sum'),B1_reference=('covers_recurring_B1_reference','sum'),B2_reference=('covers_recurring_B2_reference','sum'),B2_uniform=('covers_recurring_B2_uniform','sum'),B2_possible=('covers_recurring_B2_possible','sum')).reset_index();summary.to_csv(O/'RESUMEN_COBERTURA.csv',index=False)
for src in [O/'COMPARADORES_CAPTURA_ACTUALIZADOS.csv',O/'RESUMEN_MACROESCENARIOS.csv',O/'CASOS_PUBLICABLES.csv',O/'RESUMEN_COBERTURA.csv']:
 for dest in [I/src.name,S/'evidencia/inputs'/src.name]:shutil.copy2(src,dest)
meta={'status':'PASS','paired_n':len(new),'draw_id_and_gain_exact':True,'new_random_draws':False,'paired_rows':len(hist),'macro_rows':len(mr),'selected_cases':len(sel),'sources':{str(p):sha(p) for p in [oldpath,newpath,R/'paso_04/MACROESCENARIOS_CONJUNTOS_40.csv',I/'FRONTERAS_ANUALES_480.csv']},'comparison_changes':'New reconciled capture and recurring F; historical draws retained, gain and benefits exactly matched; macro vectors retained as joint historical scenarios.'}
(S/'evidencia/COMPARADORES_ACTUALIZADOS.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(summary.to_string(index=False));print(sel[['country_id','scenario_id','regime_id','policy_variant_id','R_reference','Fmax_B2_reference','F_recurring_author','H_B2','g_required','gain_status','macro_B2_pass']].to_string(index=False));print(hist[hist['mode'].isin(['reference','hist_tax_mixture','hist_total_revenue_mixture'])][['mode','rule','crossings','frequency','M_p50']].to_string(index=False))
