from comun import *
import json,hashlib,time
O=N/'resultados';start=time.perf_counter();rows=[];channels=[];cn=Central();front=cn.array('E_prod_frontier')
previous=pd.read_csv(S/'resultados_candidatos/CANALES_80.csv')
for c in ta.COUNTRIES:
 for sc in ta.SCENARIOS:
  cs=mc.build_country_scenario_draws(cn,x,c,sc,front)
  for reg in ta.REGIMES:
   rd=mc.build_regime_draws(cn,reg);pols=policies(c);p,z,env,ext,old=build(cn,c,sc,reg,cs,rd,pols[0]);g=float(cs['g_ai_level'][0])
   prior=previous[previous.country_id.eq(c)&previous.scenario_id.eq(sc)&previous.regime_id.eq(reg)].iloc[0]
   assert np.allclose(old['mfc_gross'],prior.M_IVA_destino,atol=2e-12,rtol=1e-12)
   ch={'country_id':c,'scenario_id':sc,'regime_id':reg,'g':g,'M_IVA_only':float(old['mfc_gross'][0]),'M_reference':float(z['M'][0]),'M_low':float(env['M_low'][0]),'M_high':float(env['M_high'][0]),'M_extreme_low':float(ext['M_low'][0]),'M_extreme_high':float(ext['M_high'][0]),'min_vertex':str(env['vertices'][int(env['argmin'][0])]),'max_vertex':str(env['vertices'][int(env['argmax'][0])]),'relative_corporate_base':float(p['relative_base'][0])}
   ch.update({k:float(z[k][0]) for k in ['tax_l','tax_cit','tax_pit_k','tax_ai','tax_vat','disposable_w','disposable_n','consumption']});channels.append(ch)
   for pol in pols:
    f=float(mc.fixed_cost_arrays(x['policy_admin_transition_cost'],c,pol['policy_id'],rd['leakage_multiplier'])['f_fix'][0]);a=annuity(c,pol['policy_id']);cost=pol['cost_gross_gdp'];spb=value('sPB_plus_gdp_ratio',country=c)
    for timing,F in [('annual_equivalent',f),('endpoint_without_setup_obligation',f-a)]:
     r={'country_id':c,'scenario_id':sc,'regime_id':reg,'policy_id':pol['policy_id'],'policy_variant_id':pol['policy_variant_id'],'timing':timing,'F':F,'benefits':cost,'spb':spb,**{k:ch[k] for k in ['g','M_reference','M_low','M_high','M_extreme_low','M_extreme_high']}}
     for mode in ['reference','low','high','extreme_low','extreme_high']:
      flow=g*r['M_'+mode]-F;r['V_'+mode]=flow/cost
      for name,req in [('B0',cost),('B1',1.1*cost),('B2',1.1*cost+spb)]:r[name+'_'+mode]=bool(flow>=req);r['F_max_'+name+'_'+mode]=g*r['M_'+mode]-req
     r['classification_B2']='uniform_crossing' if r['B2_low'] else ('conditional_crossing' if r['B2_high'] else 'no_crossing_in_domain')
     rows.append(r)
d=pd.DataFrame(rows);d.to_csv(O/'DETERMINISTA_CONCILIADO_960.csv',index=False);pd.DataFrame(channels).to_csv(O/'CANALES_CONCILIADOS_80.csv',index=False)
summary=d.assign(domain=np.where(d.scenario_id.eq('stress'),'stress','nonstress')).groupby(['timing','domain'],sort=False).agg(cells=('B0_reference','size'),B0_reference=('B0_reference','sum'),B2_reference=('B2_reference','sum'),B0_uniform=('B0_low','sum'),B0_possible=('B0_high','sum'),B2_uniform=('B2_low','sum'),B2_possible=('B2_high','sum'),B2_possible_extreme=('B2_extreme_high','sum')).reset_index()
summary.to_csv(O/'RESUMEN_DETERMINISTA.csv',index=False)
for rule in ['B0','B1','B2']:assert (~d[rule+'_low']|d[rule+'_reference']).all() and (~d[rule+'_reference']|d[rule+'_high']).all()
print('Determinista PASS',len(d),flush=True);print(summary.to_string(index=False),flush=True)
# Complete grid, 5,000 shared draws per cell. Unknown a/k stay set-valued.
seed=20261114;n=5000;sampler=mc.ValueSampler(x['values'],n,seed,record_parameters=False);front=sampler.array('E_prod_frontier');mcrows=[];drawframes=[];scope=[]
for c in ta.COUNTRIES:
 for sc in ta.SCENARIOS:
  cs=mc.build_country_scenario_draws(sampler,x,c,sc,front)
  for reg in ta.REGIMES:
   rd=mc.build_regime_draws(sampler,reg);pols=policies(c);p,z,env,ext,old=build(sampler,c,sc,reg,cs,rd,pols[0]);g=cs['g_ai_level'];modes={'iva_only':old['mfc_gross'],'reference':z['M'],'uniform':env['M_low'],'possible':env['M_high']}
   valid=np.isfinite(g)&(g>0)&cs['support_ok']
   for M in modes.values():valid &= np.isfinite(M)
   scope.append({'country_id':c,'scenario_id':sc,'regime_id':reg,'n':n,'valid':int(valid.sum()),'invalid':int((~valid).sum())})
   drawframes.append(pd.DataFrame({'country_id':c,'scenario_id':sc,'regime_id':reg,'draw_id':np.arange(n),'g':g,'M_iva_only':modes['iva_only'],'M_reference':z['M'],'M_low':env['M_low'],'M_high':env['M_high'],'leakage_multiplier':rd['leakage_multiplier'],'valid':valid}))
   for pol in pols:
    f=mc.fixed_cost_arrays(x['policy_admin_transition_cost'],c,pol['policy_id'],rd['leakage_multiplier'])['f_fix'];a=annuity(c,pol['policy_id']);cost=pol['cost_gross_gdp'];spb=value('sPB_plus_gdp_ratio',country=c)
    for timing,F in [('annual_equivalent',f),('endpoint_without_setup_obligation',f-a)]:
     for mode,M in modes.items():
      for rule,req in [('B0',cost),('B2',1.1*cost+spb)]:
       hit=valid&(g*M-F>=req)
       mcrows.append({'country_id':c,'scenario_id':sc,'regime_id':reg,'policy_variant_id':pol['policy_variant_id'],'timing':timing,'mode':mode,'rule':rule,'n':n,'valid':int(valid.sum()),'crossings':int(hit.sum()),'frequency_all_draw':float(hit.mean()),'role':'conditional frequency' if mode in ['reference','iva_only'] else 'pointwise guarantee/possibility frequency bound, not a mixture probability'})
 print('Monte Carlo país terminado',c,flush=True)
pd.DataFrame(mcrows).to_csv(O/'MONTE_CARLO_5000_TODAS_CELDAS.csv',index=False);pd.DataFrame(scope).to_csv(O/'SOPORTE_MC_80.csv',index=False);pd.concat(drawframes,ignore_index=True).to_parquet(O/'SORTEOS_CONCILIADOS_80x5000.parquet',index=False)
# Exact match against the retained 50k original case before applying new model.
n=50000;sampler=mc.ValueSampler(x['values'],n,seed,record_parameters=False);front=sampler.array('E_prod_frontier');cs=mc.build_country_scenario_draws(sampler,x,'CHL','mid',front);rd=mc.build_regime_draws(sampler,'r0');pol=next(q for q in policies('CHL') if q['policy_variant_id']=='GMI:GMI_ideal_aggregate')
base=old_module().compute_cell_arrays(sampler,x,'CHL','mid','r0',pol,cs,rd);saved=pd.read_parquet(I/'sorteos.parquet')
assert np.array_equal(base['mfc_gross'],saved.mfc__structural.to_numpy())
for key in ['g_ai_level','translation_factor','phi_y_nominal']:assert np.array_equal(cs[key],saved[key].to_numpy())
p,z,env,ext,old=build(sampler,'CHL','mid','r0',cs,rd,pol);g=cs['g_ai_level'];f=base['fixed']['f_fix'];a=annuity('CHL','GMI');cost=pol['cost_gross_gdp'];matched=[]
draws=pd.DataFrame({'draw_id':np.arange(n),'g':g,'F_annual_equivalent':f,'benefits':cost,'M_original':base['mfc_gross'],'M_iva_only':old['mfc_gross'],'M_reference':z['M'],'M_low':env['M_low'],'M_high':env['M_high']})
for timing,F in [('annual_equivalent',f),('endpoint_without_setup_obligation',f-a)]:
 for mode,M in [('original',base['mfc_gross']),('iva_only',old['mfc_gross']),('reference',z['M']),('uniform',env['M_low']),('possible',env['M_high'])]:
  for rule,req in [('B0',cost),('B2',1.1*cost)]:
   hit=np.isfinite(M)&(g*M-F>=req);matched.append({'timing':timing,'mode':mode,'rule':rule,'n':n,'crossings':int(hit.sum()),'frequency':float(hit.mean())})
draws.to_parquet(O/'SORTEOS_CHILE_50000.parquet',index=False);pd.DataFrame(matched).to_csv(O/'CHILE_EMPAREJADO_50000.csv',index=False)
case=d[d.country_id.eq('CHL')&d.scenario_id.eq('mid')&d.regime_id.eq('r0')&d.policy_variant_id.eq(pol['policy_variant_id'])];case.to_csv(O/'CHILE_DETERMINISTA_MODERADO_R0.csv',index=False)
manifest={'status':'PASS','seed':seed,'deterministic_rows':len(d),'unique_policy_cells':480,'full_MC_rows':len(mcrows),'draws_per_cell':5000,'full_MC_distinct_country_scenario_regime_vectors':80,'full_MC_valid':int(sum(r['valid'] for r in scope)),'full_MC_invalid':int(sum(r['invalid'] for r in scope)),'paired_draws':50000,'original_50000_exactly_reproduced':True,'unknown_coefficients_sampled':False,'design_sha256':hashlib.sha256((N/'DISENO_PREVIO.md').read_bytes()).hexdigest(),'elapsed_seconds':time.perf_counter()-start,'status_limits':'Conditional reconciled candidate; no empirical identification of a,k or F; no transition funding certificate; not promoted to Word.'}
(N/'evidencia/EJECUCION.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(pd.DataFrame(matched).query("rule=='B2'").to_string(index=False),flush=True);print(json.dumps(manifest,ensure_ascii=False),flush=True)
