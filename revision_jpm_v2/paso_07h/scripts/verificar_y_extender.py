from pathlib import Path
from decimal import Decimal as D, localcontext
from itertools import product
import json,sys,importlib.util,hashlib
sys.dont_write_bytecode=True
import numpy as np,pandas as pd
S=Path(__file__).resolve().parents[1];R=S.parent;E=S/'evidencia';O=S/'resultados'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
run=json.loads((O/'EJECUCION.json').read_text())
for name,h in run['source_hashes'].items():assert sha(R/name)==h,name
cfg=json.loads((E/'CONFIGURACIONES_FLUJOS.json').read_text());flows=pd.read_csv(O/'FLUJOS_DIAGNOSTICOS.csv').set_index('flow_id');allrows=pd.read_csv(O/'FRONTERAS_DIAGNOSTICAS.csv')
errors=[];values={};checks=0
with localcontext() as lc:
 lc.prec=45
 cv=lambda x:D(str(x))
 for item in cfg:
  idx=item['flow_id'];ctx=item['context'];p=ctx['prepared'];a,w,n=map(cv,item['coefficients']);ls=cv(p['ls']);q=cv(ctx['q']);eps=cv(ctx['epsilon'])
  tr=min(D(1),(eps+(1-eps)*cv(ctx['exposure']))**cv(ctx['beta'])*(eps+(1-eps)*q)**cv(ctx['gamma'])/cv(ctx['s_frontier']))
  g=(1+cv(ctx['phi'])*tr)**10-1;sp=1/(1+(-((ls/(1-ls)).ln()+q*cv(ctx['pressure_per_q']))).exp())
  dw=sp*(1+g)-ls;dn=g-dw
  tl=(cv(p['ssc'])+(1-a)*cv(p['pit']))/ls*cv(p['ul']);tn=(cv(p['cit'])*cv(p['relative_base'])+a*cv(p['pit']))/(1-ls)*cv(p['uk'])
  taxw=tl*dw;taxn=tn*dn;taxa=cv(ctx['lambda_ai'])*cv(ctx['tau_ai'])*max(D(0),1-cv(ctx['erosion_ai'])*cv(ctx['tau_ai']))*g
  vat=cv(p['vat_yield'])*cv(p['uc'])*(w*(dw-taxw)+n*(dn-taxn-taxa));rev=taxw+taxn+taxa+vat
  values[idx]=float(rev)
  for name,v in [('g',g),('share_prime',sp),('dw',dw),('revenue',rev)]:
   err=abs(float(v)-float(flows.loc[idx,name]));errors.append(err);assert err<2e-13,(idx,name,err);checks+=1
  assert abs(float(dw+dn-g))<1e-40;checks+=1
  # Baseline tax receipts remain allocated once between labour and non-labour.
  anchor=(cv(p['ssc'])+(1-a)*cv(p['pit']))+(cv(p['cit'])+a*cv(p['pit']))
  assert abs(anchor-(cv(p['ssc'])+cv(p['cit'])+cv(p['pit'])))<D('1e-40');checks+=1
revenue=allrows.flow_id.map(values).to_numpy();ff=revenue-1.1*allrows.benefits.to_numpy()-allrows.spb.to_numpy();gg=ff-allrows.F_recurring_author.to_numpy()
assert np.max(abs(ff-allrows.Fmax))<3e-13 and np.max(abs(gg-allrows.gap))<3e-13
assert (np.greater_equal(gg,-1e-12)==allrows.B2).all();checks+=3*len(allrows)
critical=pd.read_csv(O/'UMBRALES_CALIBRACION_480.csv')
assert (critical.vat_w_slope>0).all() and (critical.vat_n_slope>0).all()
for _,z in critical.iterrows():
 for k,rev in [('k_w_required_kn_fixed',lambda x:z.direct+x*z.vat_w_slope+z.k_n*z.vat_n_slope),('k_n_required_kw_fixed',lambda x:z.direct+z.k_w*z.vat_w_slope+x*z.vat_n_slope),('k_required_kn_half_kw',lambda x:z.direct+x*(z.vat_w_slope+.5*z.vat_n_slope))]:
  assert abs(rev(z[k])-z.required)<2e-13;assert rev(z[k]-1e-7)<z.required<rev(z[k]+1e-7);checks+=3
 assert abs(z.F_multiplier_critical*z.F_recurring_author-z.Fmax)<2e-13;checks+=1
# Pressure is multi-affine in each of the seven primitive coordinates. Enumerate
# their corners independently, then use monotonicity of the logistic and the
# affine revenue dependence on its share to establish endpoint sufficiency.
params=pd.read_csv(E/'PARAMETROS_DISTRIBUCION.csv');vv=pd.read_csv(O/'VERTICES_PRESION_512.csv')
for _,v in vv.iterrows():
 expected=v.lambda_LS*(-v.delta_s*v.E_auto+v.zeta_s*v.RST*v.E_auto+v.psi_s*v.E_aug)
 assert abs(expected-v.pressure)<1e-14;checks+=1
for country in ['PER','CHL','COL','MEX']:
 z=vv[vv.country_id.eq(country)]
 assert len(z)==128 and z.pressure.min()<=0<=z.pressure.max();checks+=1
 for name in ['lambda_LS','delta_s','zeta_s','RST','E_auto','psi_s','E_aug']:
  p=params[params.country_id.eq(country)&params.name.eq(name)].iloc[0]
  assert set(z[name])=={p.low_value,p.high_value};checks+=1

# Selected no-replacement paths quantify whether labour calibration changes the
# timing narrative. All macro, cost and coefficient assumptions stay at reference.
note='''\n\n### Comprobación consecuente de financiación\n\nTras revisar los cruces anuales, se añade una comparación de 56 trayectorias: siete casos × dos definiciones laborales × cuatro presiones (central, cero y extremos). Se mantiene el presupuesto B2, costos e inversión de referencia, macro 2024 y ausencia de reposición. Su objetivo es evaluar la dependencia de las fechas ilustrativas de la distribución; no reemplaza la sensibilidad conjunta macroeconómica 7g.\n'''
log=S/'NOTA_FINANCIACION_DISTRIBUCION.md'
if not log.exists():log.write_text('# Alcance complementario 7h\n'+note,encoding='utf-8')
spec=importlib.util.spec_from_file_location('frontier07g',R/'paso_07g/candidato/frontera_transicion.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
inputs=json.loads((R/'paso_07g/bloque_3_transicion/INSUMOS_CASOS.json').read_text());macro=pd.read_csv(R/'paso_04/MACROESCENARIOS_CONJUNTOS_40.csv')
prior=pd.read_csv(R/'paso_07g/bloque_3_transicion/COMBINACIONES_ILUSTRATIVAS.csv')
configmap={x['flow_id']:x for x in cfg};fin=[];finerrors=[];baseline_matches=0
for case in inputs:
 c,sc,reg=case['country_id'],case['scenario_id'],case['regime_id']
 old=prior[(prior.case_id==case['case_id'])&(prior.H==25)&(prior.macro_id=='historical_2024')&(prior.replacement_period==0)&(prior.budget=='B2_reserved')].iloc[0]
 sf=flows[(flows.country_id==c)&(flows.scenario_id==sc)&(flows.regime_id==reg)&(flows.coefficient_mode=='reference')&(flows.erosion_mode=='central')]
 for idx,z in sf.iterrows():
  conf=configmap[idx];ctx=conf['context'];coef=conf['coefficients'];years=np.arange(1,26)
  revenue=f.capture(ctx,coef,years=years)['revenue'];benefits=np.array(case['benefits']);need=1.1*benefits+old.spb
  sol=f.financing(revenue,need,old.F,old.I,old.interest,old.growth)
  # Separate nominal ledger in base-GDP units, not the candidate recursion.
  nominal=float(old.I);pv=[nominal];bb=[]
  for t in range(1,26):
   nominal=(1+old.interest)*nominal+(need[t-1]+old.F-revenue[t-1])*(1+old.growth)**t
   bb.append(nominal/(1+old.growth)**t);pv.append(nominal/(1+old.interest)**t)
  err=max(np.max(abs(np.array(bb)-sol['balance'])),abs(max(0,*pv)-sol['initial_capital'][-1]));assert err<1e-12;finerrors.append(float(err));checks+=26
  ret=np.flatnonzero(sol['balance']<=0);cover=np.flatnonzero(revenue-need-old.F>=0)
  if z.anchor=='PWT' and z.pressure_mode=='central':
   assert abs(sol['balance'][-1]-old.balance_H)<1e-12 and abs(sol['initial_capital'][-1]-old.initial_capital_gdp0_H)<1e-12;baseline_matches+=1
  fin.append(dict(case_id=case['case_id'],country_id=c,scenario_id=sc,regime_id=reg,policy_variant_id=case['policy_variant_id'],anchor=z.anchor,pressure_mode=z.pressure_mode,first_annual=int(cover[0]+1) if len(cover) else None,first_return=int(ret[0]+1) if len(ret) else None,capital_25=sol['initial_capital'][-1],balance_10=sol['balance'][9],balance_25=sol['balance'][-1]))
pd.DataFrame(fin).to_csv(O/'FINANCIACION_DISTRIBUCION_56.csv',index=False)
assert len(fin)==56 and baseline_matches==7
out={'status':'PASS','checks':checks,'independent_decimal_flows':len(flows),'annual_budget_rows':len(allrows),'critical_rows':len(critical),'pressure_vertices':len(vv),'financing_paths':len(fin),'financing_path_years':len(fin)*25,'reference_paths_preserved':baseline_matches,'max_decimal_error':max(errors),'max_nominal_financing_error':max(finerrors),'independence':'Different algebra/Decimal and nominal implementation within the project; not an external replication.','source_hashes':{str(p.relative_to(R)):sha(p) for p in [R/'paso_07g/bloque_3_transicion/INSUMOS_CASOS.json',R/'paso_07g/bloque_3_transicion/COMBINACIONES_ILUSTRATIVAS.csv']}}
(O/'VERIFICACION_INDEPENDIENTE.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8');print(json.dumps(out))
print(pd.DataFrame(fin).query('country_id=="CHL" and scenario_id=="mid"')[['regime_id','anchor','pressure_mode','first_annual','first_return','capital_25']].to_string(index=False))
