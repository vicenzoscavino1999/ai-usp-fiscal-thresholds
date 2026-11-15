from pathlib import Path
import sys,json,itertools,importlib.util,shutil
sys.dont_write_bytecode=True
import numpy as np,pandas as pd
S=Path(__file__).resolve().parents[1];R=S.parent;T=R/'paso_07d/costos_transicion_03';O=S/'bloque_3_transicion'
sys.path.insert(0,str(T/'scripts'));import common03 as old
spec=importlib.util.spec_from_file_location('new_frontier_07g',S/'candidato/frontera_transicion.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
cases=pd.read_csv(R/'paso_07e/resultados/CASOS_PUBLICABLES.csv');macro=pd.read_csv(R/'paso_04/MACROESCENARIOS_CONJUNTOS_40.csv');wpp=pd.read_parquet(T/'evidencia/wpp_2024_2049.parquet');ctxs=json.loads((S/'evidencia/CONTEXTOS_80.json').read_text())
shutil.copy2(R/'paso_04/MACROESCENARIOS_CONJUNTOS_40.csv',O/'MACROESCENARIOS_CONJUNTOS_40.csv')
base=pd.read_csv(T/'resultados/FRONTERAS_TRANSICION.csv');Y=np.arange(1,26);rows=[];meta=[];mats={k:[] for k in ['revenue','cost','replacement','balance','frontier','capital','benefits']};baseline_checks=0;inputs=[]
for cid,case in cases.iterrows():
 country,scenario,regime,variant=case[['country_id','scenario_id','regime_id','policy_variant_id']]
 ctx=next(z['context'] for z in ctxs if (z['country_id'],z['scenario_id'],z['regime_id'])==(country,scenario,regime))
 pol=next(p for p in old.cf.policies(country) if p['policy_variant_id']==variant);benefits=old.cost_path(country,pol,wpp);f0,i0,ann=old.costs(country,pol['policy_id'],ctx)
 inputs.append({'case_id':cid,'country_id':country,'scenario_id':scenario,'regime_id':regime,'policy_variant_id':variant,'benefits':benefits.tolist(),'F_reference':f0,'I_reference':i0,'context':ctx})
 mm=macro[macro.country_id.eq(country)].copy();mm['macro_id']=mm.macro_year.map(lambda y:f'historical_{y}')
 adverse=mm[mm.macro_year.eq(2024)].iloc[0].copy();adverse['macro_id']='diagnostic_i_plus2_n_minus2';adverse['nominal_interest_rate']+=.02;adverse['nominal_growth_rate']-=.02
 mm=pd.concat([mm,pd.DataFrame([adverse])],ignore_index=True)
 coefs=[('reference',ctx['reference'])]+[(f'vertex_{j}',v) for j,v in enumerate(f.VERTICES)]
 for mr in mm.itertuples():
  interest,growth=mr.nominal_interest_rate,mr.nominal_growth_rate;spb=max(0,(interest-growth)/(1+growth)*mr.target_debt_ratio_2024-mr.primary_balance_ratio)
  if mr.macro_id.startswith('historical'):assert abs(spb-mr.spb_variant)<1e-13
  for ff,ii,period,(mode,coef),budget in itertools.product([.75,1.,1.25],[.5,1.,1.5],[0,2,3,5],coefs,['cash','B2_reserved']):
   revenue=np.asarray(f.capture(ctx,coef,years=Y)['revenue']);F=f0*ff;I=i0*ii;rep=np.where(Y%period==0,I,0.) if period else np.zeros(25)
   cost=benefits if budget=='cash' else 1.1*benefits+spb
   z=f.financing(revenue,cost,F,I,interest,growth,rep);bid=len(meta)
   fields=dict(path_id=bid,case_id=cid,country_id=country,scenario_id=scenario,regime_id=regime,policy_variant_id=variant,macro_id=mr.macro_id,interest=interest,growth=growth,spb=spb,primary_balance=mr.primary_balance_ratio,target_debt=mr.target_debt_ratio_2024,F_factor=ff,I_factor=ii,replacement_period=period,mode=mode,alpha=coef[0],k_w=coef[1],k_n=coef[2],budget=budget,F=F,I=I)
   meta.append(fields)
   for k,v in [('revenue',revenue),('cost',cost),('replacement',rep),('balance',z['balance']),('frontier',z['fmax']),('capital',z['initial_capital']),('benefits',benefits)]:mats[k].append(v)
   annual=revenue-cost-F>=0;returned=z['balance']<=0;persistent=np.logical_and.accumulate(returned[::-1])[::-1]
   first=lambda x:int(np.flatnonzero(x)[0]+1) if x.any() else None
   for H in [10,25]:
    row={**fields,'H':H,'annual_coverage_H':bool(annual[H-1]),'first_annual_coverage_by_H':first(annual[:H]),'balance_H':float(z['balance'][H-1]),'Fmax_H':float(z['fmax'][H-1]),'initial_capital_gdp0_H':float(z['initial_capital'][H-1]),'peak_balance_ratio_H':float(max(I,z['balance'][:H].max())),'first_return_by_H':first(returned[:H]),'persistent_return_to_25':first(persistent),'no_return_by_H':not returned[:H].any(),'ending_balance_positive':bool(z['balance'][H-1]>0)}
    rows.append(row)
    if mr.macro_id=='historical_2024' and ff==ii==1 and mode=='reference' and period in [0,3]:
     prev=base[(base.country_id==country)&(base.scenario_id==scenario)&(base.regime_id==regime)&(base.policy_variant_id==variant)&(base.H==H)&(base.budget==budget)&(base.replacement==('none' if period==0 else 'every3_author_sensitivity'))];assert len(prev)==1
     prev=prev.iloc[0]
     for nk,pk in [('balance_H','balance_reference_noAI'),('Fmax_H','Fmax_path_reference'),('initial_capital_gdp0_H','initial_capital_reference_gdp0'),('peak_balance_ratio_H','peak_balance_reference_noAI')]:assert abs(row[nk]-prev[pk])<2e-12,(cid,H,nk,row[nk],prev[pk])
     baseline_checks+=1
 print(json.dumps({'case_completed':int(cid),'paths':len(meta)}),flush=True)
meta=pd.DataFrame(meta);res=pd.DataFrame(rows);meta.to_csv(O/'TRAYECTORIAS_CONFIGURACION.csv',index=False);res.to_csv(O/'SENSIBILIDAD_H10_H25.csv',index=False)
np.savez_compressed(O/'TRAYECTORIAS_COMPLETAS.npz',**{k:np.asarray(v) for k,v in mats.items()})
(O/'INSUMOS_CASOS.json').write_text(json.dumps(inputs,indent=2)+'\n',encoding='utf-8')
# Compact, predetermined illustrative combinations; no selection by outcome.
sel=res[(res['mode']=='reference')&((res.macro_id.eq('historical_2024')&res.F_factor.eq(1)&res.I_factor.eq(1)&res.replacement_period.isin([0,3]))|(res.macro_id.eq('diagnostic_i_plus2_n_minus2')&res.F_factor.eq(1.25)&res.I_factor.eq(1.5)&res.replacement_period.isin([0,2,3,5])))].copy()
sel.to_csv(O/'COMBINACIONES_ILUSTRATIVAS.csv',index=False)
domain=res.groupby(['case_id','budget','H']).agg(paths=('path_id','size'),annual_pass=('annual_coverage_H','sum'),no_return=('no_return_by_H','sum'),balance_min=('balance_H','min'),balance_max=('balance_H','max'),capital_min=('initial_capital_gdp0_H','min'),capital_max=('initial_capital_gdp0_H','max'),return_min=('first_return_by_H','min'),return_max_among_returns=('first_return_by_H','max')).reset_index();domain.to_csv(O/'RANGOS_DOMINIO_DIAGNOSTICO.csv',index=False)
manifest={'status':'BUILT','paths':len(meta),'path_years':len(meta)*25,'horizon_rows':len(res),'baseline_rows_matched':baseline_checks,'macro_vectors_per_country':11,'coefficient_paths':9,'F_factors':[.75,1,1.25],'I_factors':[.5,1,1.5],'replacement_periods':[0,2,3,5],'horizons':[10,25],'domain_is_probabilistic':False}
(O/'EJECUCION.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8');print(json.dumps(manifest))
