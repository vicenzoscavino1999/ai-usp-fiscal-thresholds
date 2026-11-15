from pathlib import Path
import json
import pandas as pd,numpy as np
S=Path(__file__).resolve().parents[1];O=S/'resultados'
d=pd.read_csv(O/'FRONTERAS_DIAGNOSTICAS.csv');keys=['country_id','scenario_id','regime_id','policy_variant_id']
base=d.query('anchor=="PWT" and pressure_mode=="central" and erosion_mode=="central" and coefficient_mode=="reference"').set_index(keys).sort_index()
out={'status':'PASS','reference_nonstress':int(base[base.index.get_level_values('scenario_id')!='stress'].B2.sum()),'reference_stress':int(base[base.index.get_level_values('scenario_id')=='stress'].B2.sum()),'classification_changes':{}}
for mode in ['pit_0','pit_30','pit_100']:
 x=d[(d.anchor=='PWT')&(d.pressure_mode=='central')&(d.erosion_mode=='central')&(d.coefficient_mode==mode)].set_index(keys).sort_index()
 assert x.index.equals(base.index)
 assert np.array_equal(x.B2.to_numpy(),(x.Fmax-x.F_recurring_author>=-1e-12).to_numpy())
 n=int((x.B2!=base.B2).sum());out['classification_changes'][mode]=n
x=d.query('anchor=="CoE" and pressure_mode=="central" and erosion_mode=="central" and coefficient_mode=="reference"').set_index(keys).sort_index()
out['classification_changes']['CoE_central']=int((x.B2!=base.B2).sum())
critical=pd.read_csv(O/'UMBRALES_CASOS_7.csv');ch=critical.query('country_id=="CHL" and scenario_id=="mid" and regime_id=="r4"').iloc[0]
out['Chile_mid_r4']={k:float(ch[k]) for k in ['k_w','k_n','k_required_kn_half_kw','k_w_required_kn_fixed','k_n_required_kw_fixed','Fmax','F_recurring_author','F_multiplier_critical','F_percent_benefit']}
out['Chile_mid_r4']['cost_headroom_percent']=100*(ch.F_multiplier_critical-1)
env=pd.read_csv(O/'ENVOLVENTES_DISTRIBUCION_CAPTURA.csv');ss=[]
for (anchor,domain,stress),part in env.groupby(['anchor','domain',env.scenario_id.eq('stress')]):
 ss.append({'anchor':anchor,'domain':domain,'scenario_group':'stress' if stress else 'nonstress','cells':len(part),'uniform':int(part.uniform.sum()),'possible':int(part.possible.sum())})
out['joint_domain_counts']=ss
fin=pd.read_csv(O/'FINANCIACION_DISTRIBUCION_56.csv');r=[]
for key,part in fin.groupby(['case_id']+keys):
 r.append(dict(zip(['case_id']+keys,key),first_annual_min=part.first_annual.min(),first_annual_max=part.first_annual.max(),return_min=part.first_return.min(),return_max=part.first_return.max(),censored_paths=int(part.first_return.isna().sum()),capital_min=part.capital_25.min(),capital_max=part.capital_25.max()))
pd.DataFrame(r).to_csv(O/'RESUMEN_FINANCIACION_7.csv',index=False)
out['distribution_nonstress_reference_counts']={mode:int(d[(d.anchor=='PWT')&(d.pressure_mode==mode)&(d.erosion_mode=='central')&(d.coefficient_mode=='reference')&(d.scenario_id!='stress')].B2.sum()) for mode in ['central','zero','support_min','support_max']}
(O/'DECISIONES_VERIFICADAS.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(out,ensure_ascii=True))
