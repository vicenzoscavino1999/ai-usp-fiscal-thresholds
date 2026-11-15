from pathlib import Path
from copy import deepcopy
from itertools import product
import sys, json, hashlib, shutil, importlib.util
sys.dont_write_bytecode=True
import numpy as np
import pandas as pd
S=Path(__file__).resolve().parents[1];R=S.parent;G=R/'paso_07g';E=S/'evidencia';O=S/'resultados'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inputs={
 'CONTEXTOS_80.json':G/'evidencia/CONTEXTOS_80.json',
 'PARAMETROS_DISTRIBUCION.csv':G/'bloque_1_matematica/PARAMETROS_PARTICIPACION_LABORAL.csv',
 'ANUAL_480.csv':R/'paso_07d/costos_transicion_03/resultados/FRONTERAS_ANUALES_480.csv',
 'CASOS_7.csv':R/'paso_07e/resultados/CASOS_PUBLICABLES.csv',
 'LS_RAW_CAMBIOS.csv':R/'paso_03/candidato_corregido/ai-usp-fiscal-thresholds/reports/value_assignment_changes_baseline-official-v3_to_robustness-lsraw-v1.csv',
 'COSTOS_COMPARABLES.csv':R/'paso_07d/resultados_candidatos/COSTOS_COMPARABLES_VERIFICADOS.csv',
 'BFJZ_ETR_4_construction.do':R/'paso_07d/conciliacion_fiscal_02/fuentes/BFJZ_ETR_4_construction.do',
 'BFJZ_MANIFIESTO.json':R/'paso_07d/conciliacion_fiscal_02/evidencia/MANIFIESTO_FUENTES.json'}
for name,p in inputs.items():shutil.copy2(p,E/name)
I=R/'paso_07d/evidencia/insumos'
vals=pd.read_parquet(I/'values.parquet');cost=pd.read_parquet(I/'policy_admin_transition_cost.parquet')
vals.to_csv(E/'PARAMETROS_COMPLETOS.csv',index=False);cost.to_csv(E/'COSTOS_REGISTRADOS.csv',index=False)
macro=pd.read_parquet(I/'macro_anchor.parquet').query('year==2024');macro.to_csv(E/'MACRO_2024.csv',index=False)
spec=importlib.util.spec_from_file_location('frontier07g',G/'candidato/frontera_transicion.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
source_hashes={str(p.relative_to(R)):sha(p) for p in list(inputs.values())+[I/'values.parquet',I/'policy_admin_transition_cost.parquet',I/'macro_anchor.parquet',G/'candidato/frontera_transicion.py']}
contexts=json.loads((E/'CONTEXTOS_80.json').read_text());annual=pd.read_csv(E/'ANUAL_480.csv');cases=pd.read_csv(E/'CASOS_7.csv')
raw=pd.read_csv(E/'LS_RAW_CAMBIOS.csv').query('name=="LS_labor_share"').set_index('country_id')
def val(name,country=None):
 q=vals[vals.name.eq(name)]
 if country is not None:q=q[q.country_id.eq(country)]
 assert len(q)==1,(name,country,len(q))
 return q.iloc[0]
def response(t0,d,e):return (1+d)*max(0,1-e*t0*(1+d))/(1-e*t0)
def pressure(z):return z['lambda_LS']*(-(z['delta_s']-z['zeta_s']*z['RST'])*z['E_auto']+z['psi_s']*z['E_aug'])
names=['lambda_LS','delta_s','zeta_s','RST','E_auto','psi_s','E_aug'];boundrows=[];bounds={}
for country in ['PER','CHL','COL','MEX']:
 for j,point in enumerate(product(*[(float(val(k,country).low_value),float(val(k,country).high_value)) for k in names])):
  d=dict(zip(names,point));boundrows.append(dict(country_id=country,vertex=j,pressure=pressure(d),**d))
 a=[r['pressure'] for r in boundrows if r['country_id']==country];bounds[country]=(min(a),max(a))
pd.DataFrame(boundrows).to_csv(O/'VERTICES_PRESION_512.csv',index=False)
flowrows=[];configs=[];fid=0
for item in contexts:
 c,sc,r=item['country_id'],item['scenario_id'],item['regime_id'];ctx=item['context'];a,w,n=ctx['reference'];p=ctx['prepared']
 assert abs(w-float(macro.set_index('country_id').loc[c,'final_consumption_gdp_share'])/100)<1e-12
 coefs=[('reference',a,w,n),('pit_0',0,w,n),('pit_30',.3,w,n),('pit_100',1,w,n),('spend_none',a,0,0),('spend_all',a,1,1),('spend_equal_reference',a,w,w)]
 coefs += [('vertex_'+str(j),*z) for j,z in enumerate(product([0.,.3],[0.,1.],[0.,1.]))]
 coefs += [('vertex100_'+str(j),*z) for j,z in enumerate(product([1.],[0.,1.],[0.,1.]))]
 variants=[]
 for anchor in ['PWT','CoE']:
  base=deepcopy(ctx)
  if anchor=='CoE':
   base['prepared']['ls']=float(raw.loc[c,'robustness_value'])
   for ch,pkey,t0 in [('L','ul',(p['ssc']+p['pit'])/base['prepared']['ls']),('K','uk',p['cit']/(1-base['prepared']['ls']))]:
    base['prepared'][pkey]=response(t0,float(val(f'tau_{ch}_relative_delta_{r}').baseline_value),float(val(f'epsilon_ero_{ch}_{r}').baseline_value))
  for label,pr in [('central',ctx['pressure_per_q']),('zero',0.),('support_min',bounds[c][0]),('support_max',bounds[c][1])]:
   b=deepcopy(base);b['pressure_per_q']=pr;variants.append((anchor,label,'central',b))
 # Companion for the registered behavioural response support, one group at a time.
 for label,field in [('low','low_value'),('high','high_value')]:
  b=deepcopy(ctx)
  for ch,key,t0 in [('L','ul',(p['ssc']+p['pit'])/p['ls']),('K','uk',p['cit']/(1-p['ls'])),('C','uc',p['vat_yield'])]:
   b['prepared'][key]=response(t0,float(val(f'tau_{ch}_relative_delta_{r}').baseline_value),float(val(f'epsilon_ero_{ch}_{r}')[field]))
  b['erosion_ai']=float(val(f'epsilon_ero_AI_{r}')[field]);variants.append(('PWT','central',label,b))
 for anchor,press,eros,cc in variants:
  for mode,aa,ww,nn in coefs:
   out=f.capture(cc,(aa,ww,nn));g,dw,rev,sp=(float(out[k]) for k in ['g','dw','revenue','share_prime'])
   pp=cc['prepared'];tl=(pp['ssc']+(1-aa)*pp['pit'])/pp['ls']*pp['ul'];tn=(pp['cit']*pp['relative_base']+aa*pp['pit'])/(1-pp['ls'])*pp['uk'];v=pp['vat_yield']*pp['uc'];ta=cc['lambda_ai']*cc['tau_ai']*max(0,1-cc['erosion_ai']*cc['tau_ai'])*g
   dn=g-dw;tlflow=tl*dw;tnflow=tn*dn;cw=v*(dw-tlflow);cn=v*(dn-tnflow-ta);direct=tlflow+tnflow+ta
   assert abs(rev-(direct+ww*cw+nn*cn))<1e-14
   row=dict(flow_id=fid,country_id=c,scenario_id=sc,regime_id=r,anchor=anchor,pressure_mode=press,erosion_mode=eros,coefficient_mode=mode,alpha=aa,k_w=ww,k_n=nn,pressure=cc['pressure_per_q'],share=pp['ls'],share_prime=sp,g=g,dw=dw,dn=dn,t_l=tl,t_n=tn,vat=v,direct=direct,vat_w_slope=cw,vat_n_slope=cn,revenue=rev,M=rev/g)
   flowrows.append(row);configs.append(dict(flow_id=fid,context=cc,coefficients=[aa,ww,nn]));fid+=1
flow=pd.DataFrame(flowrows);flow.to_csv(O/'FLUJOS_DIAGNOSTICOS.csv',index=False)
(E/'CONFIGURACIONES_FLUJOS.json').write_text(json.dumps(configs,separators=(',',':'))+'\n',encoding='utf-8')
keys=['country_id','scenario_id','regime_id'];keep=keys+['policy_id','policy_variant_id','benefits','F_recurring_author','setup_author','spb','Fmax_B2_reference','covers_recurring_B2_reference']
full=flow.merge(annual[keep],on=keys,validate='many_to_many')
full['Fmax']=full.revenue-1.1*full.benefits-full.spb;full['gap']=full.Fmax-full.F_recurring_author;full['B2']=full.gap.ge(-1e-12)
full.to_csv(O/'FRONTERAS_DIAGNOSTICAS.csv',index=False)
baseline=full.query('anchor=="PWT" and pressure_mode=="central" and erosion_mode=="central" and coefficient_mode=="reference"').copy()
assert len(baseline)==480 and np.max(abs(baseline.Fmax-baseline.Fmax_B2_reference))<2e-14
assert (baseline.B2==baseline.covers_recurring_B2_reference).all()
for which,part in [('nonstress',baseline[baseline.scenario_id!='stress']),('stress',baseline[baseline.scenario_id=='stress'])]:print(which,len(part),int(part.B2.sum()))
base=flow.query('anchor=="PWT" and pressure_mode=="central" and erosion_mode=="central" and coefficient_mode=="reference"')
critical=baseline.copy();critical['required']=1.1*critical.benefits+critical.spb+critical.F_recurring_author
critical['k_w_required_kn_fixed']=(critical.required-critical.direct-critical.k_n*critical.vat_n_slope)/critical.vat_w_slope
critical['k_n_required_kw_fixed']=(critical.required-critical.direct-critical.k_w*critical.vat_w_slope)/critical.vat_n_slope
critical['k_required_kn_half_kw']=(critical.required-critical.direct)/(critical.vat_w_slope+.5*critical.vat_n_slope)
critical['F_multiplier_critical']=critical.Fmax/critical.F_recurring_author
critical['F_percent_benefit']=100*critical.F_recurring_author/critical.benefits
critical['Fmax_percent_benefit']=100*critical.Fmax/critical.benefits
critical['additional_revenue_required']=np.maximum(0,critical.required-critical.revenue)
critical.to_csv(O/'UMBRALES_CALIBRACION_480.csv',index=False)
selected=critical.merge(cases[keys+['policy_variant_id']],on=keys+['policy_variant_id'],validate='one_to_one');selected.to_csv(O/'UMBRALES_CASOS_7.csv',index=False)
summary=full.groupby(['anchor','pressure_mode','erosion_mode','coefficient_mode','scenario_id']).agg(cells=('B2','size'),B2=('B2','sum')).reset_index();summary.to_csv(O/'RESUMEN_CRUCES.csv',index=False)
envelopes=[]
for anchor in ['PWT','CoE']:
 for domain,mask in [('standard',full.coefficient_mode.str.match(r'^vertex_')),('expanded',full.coefficient_mode.str.match(r'^vertex'))]:
  sub=full[(full.anchor==anchor)&full.pressure_mode.isin(['support_min','support_max'])&(full.erosion_mode=='central')&mask]
  for key,grp in sub.groupby(keys+['policy_variant_id']):
   lo,hi=grp.Fmax.min(),grp.Fmax.max();fr=grp.F_recurring_author.iloc[0]
   envelopes.append(dict(zip(keys+['policy_variant_id'],key),anchor=anchor,domain=domain,Fmax_min=lo,Fmax_max=hi,F=fr,uniform=lo>=fr-1e-12,possible=hi>=fr-1e-12,points=len(grp)))
env=pd.DataFrame(envelopes);env.to_csv(O/'ENVOLVENTES_DISTRIBUCION_CAPTURA.csv',index=False)
env.merge(cases[keys+['policy_variant_id']],on=keys+['policy_variant_id']).to_csv(O/'ENVOLVENTES_CASOS_7.csv',index=False)
# Individual distribution effects at fixed illustrative coefficients.
ind=full.query('erosion_mode=="central" and coefficient_mode=="reference"')
ind.merge(cases[keys+['policy_variant_id']],on=keys+['policy_variant_id']).to_csv(O/'DISTRIBUCION_CASOS_7.csv',index=False)
result={'status':'BUILT_PENDING_INDEPENDENT_VERIFICATION','flows':len(flow),'annual_rows':len(full),'pressure_vertices':len(boundrows),'baseline_rows_preserved':len(baseline),'baseline_max_abs_difference':float(np.max(abs(baseline.Fmax-baseline.Fmax_B2_reference))),'new_random_draws':False,'new_empirical_numeric_inputs':False,'pressure_bounds':bounds,'source_hashes':source_hashes,'design_hash':sha(S/'ADENDA_CALIBRACIONES_DECISIVAS.md')}
(O/'EJECUCION.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='source_hashes'}))
print(selected[['country_id','scenario_id','regime_id','k_w','k_n','k_required_kn_half_kw','F_multiplier_critical','B2']].to_string(index=False))
