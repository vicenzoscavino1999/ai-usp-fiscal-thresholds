from pathlib import Path
import sys,json,hashlib,itertools,zipfile,xml.etree.ElementTree as ET
from collections import defaultdict
sys.dont_write_bytecode=True
import numpy as np,pandas as pd
S=Path(__file__).resolve().parents[1];R=S.parent;O=S/'resultados';hashes={};rows=[]
def src(p):hashes[p.relative_to(R).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest();return p
ctxs=json.loads(src(R/'paso_07g/evidencia/CONTEXTOS_80.json').read_text())
# Rigorous interval sign certificates under the registered beta=gamma=1.
# They certify monotonicity on each side of the cap independently of the
# production solver and of the numerical scan in auditar_nucleo.py.
def certify(c,k,var):
 p=c['prepared'];a,w,n=k;s=p['ls'];v=p['vat_yield']*p['uc'];tl=(p['ssc']+(1-a)*p['pit'])/s*p['ul'];tn=(p['cit']*p['relative_base']+a*p['pit'])/(1-s)*p['uk'];L=tl+v*w*(1-tl);N=tn+v*n*(1-tn);J=(1-v*n)*c['lambda_ai']*c['tau_ai']*max(0,1-c['erosion_ai']*c['tau_ai'])
 assert c['beta']==c['gamma']==1
 eps=c['epsilon'];other=c['exposure'] if var=='q' else c['q'];tr_scale=(eps+(1-eps)*other)/c['s_frontier'];cap=(1/tr_scale-eps)/(1-eps);phi=c['phi'];pr=c['pressure_per_q']
 lo=c['q'] if var=='q' else c['exposure'];hi=c['q_bar']-c['epsilon_mu'] if var=='q' else 1.;cuts=[lo]+([cap] if lo<cap<hi else [])+[hi]
 def share(x):q=x if var=='q' else c['q'];return 1/(1+(1-s)/s*np.exp(-pr*q))
 certified=[];pending=[(x,y,0) for x,y in zip(cuts[:-1],cuts[1:])]
 while pending:
  left,right,depth=pending.pop();slo,shi=sorted([share(left),share(right)]);tlo=min(1,tr_scale*(eps+(1-eps)*left));thi=min(1,tr_scale*(eps+(1-eps)*right));glo=(1+phi*tlo)**10-1;ghi=(1+phi*thi)**10-1
  Alo,Ahi=sorted([L*slo+N*(1-slo)+J,L*shi+N*(1-shi)+J])
  if left>=cap-1e-15:gp=[0.,0.]
  else:gp=[10*phi*tr_scale*(1-eps)*(1+phi*tlo)**9,10*phi*tr_scale*(1-eps)*(1+phi*thi)**9]
  product=[aa*b for aa in [Alo,Ahi] for b in gp]
  ff=[slo*(1-slo),shi*(1-shi)];fl=min(ff);fh=.25 if slo<=.5<=shi else max(ff);d=(L-N)*pr if var=='q' else 0.
  shift=[d*x*(1+y) for x in [fl,fh] for y in [glo,ghi]];lower=min(product)+min(shift);upper=max(product)+max(shift)
  if lower>=-1e-15 or upper<=1e-15:certified.append((left,right,lower,upper))
  else:
   assert depth<40,(var,k,left,right,lower,upper)
   mid=(left+right)/2;pending.extend([(left,mid,depth+1),(mid,right,depth+1)])
 return certified
for item in ctxs:
 c=item['context']
 for mode,k in [('reference',c['reference'])]+[(str(i),k) for i,k in enumerate(itertools.product([0.,.3],[0.,1.],[0.,1.]))]:
  for var in ['q','exposure']:
   intervals=certify(c,k,var)
   for left,right,lower,upper in intervals:rows.append(dict(country_id=item['country_id'],scenario_id=item['scenario_id'],regime_id=item['regime_id'],mode=mode,variable=var,left=left,right=right,derivative_lower=lower,derivative_upper=upper,sign='nonnegative' if lower>=-1e-15 else 'nonpositive'))
pd.DataFrame(rows).to_csv(O/'CERTIFICADOS_DERIVADA_POR_TRAMOS.csv',index=False)

# Recompute the 56 labour-calibration financing cases in nominal units.
configs=json.loads(src(R/'paso_07h/evidencia/CONFIGURACIONES_FLUJOS.json').read_text());configmap={x['flow_id']:x for x in configs}
flow=pd.read_csv(src(R/'paso_07h/resultados/FLUJOS_DIAGNOSTICOS.csv'))
cases=json.loads(src(R/'paso_07g/bloque_3_transicion/INSUMOS_CASOS.json').read_text());old=pd.read_csv(src(R/'paso_07g/bloque_3_transicion/COMBINACIONES_ILUSTRATIVAS.csv'));saved=pd.read_csv(src(R/'paso_07h/resultados/FINANCIACION_DISTRIBUCION_56.csv'));finance=[];maxerr=0.
for case in cases:
 cid=case['case_id'];base=old[(old.case_id==cid)&(old.H==25)&old.macro_id.eq('historical_2024')&old.replacement_period.eq(0)&old.budget.eq('B2_reserved')].iloc[0]
 ff=flow[(flow.country_id==case['country_id'])&(flow.scenario_id==case['scenario_id'])&(flow.regime_id==case['regime_id'])&flow.coefficient_mode.eq('reference')&flow.erosion_mode.eq('central')]
 for row in ff.itertuples(index=False):
  conf=configmap[row.flow_id];c=conf['context'];p=c['prepared'];a,w,n=conf['coefficients'];s=p['ls'];tr=min(1,(c['epsilon']+(1-c['epsilon'])*c['exposure'])*(c['epsilon']+(1-c['epsilon'])*c['q'])/c['s_frontier']);sp=1/(1+(1-s)/s*np.exp(-c['pressure_per_q']*c['q']));year=np.arange(1,26);gain=(1+c['phi']*tr)**year-1;dw=(sp-s)+sp*gain;dn=gain-dw
  labor=(p['ssc']+(1-a)*p['pit'])/s*p['ul']*dw;nonlabor=(p['cit']*p['relative_base']+a*p['pit'])/(1-s)*p['uk']*dn;ai=c['lambda_ai']*c['tau_ai']*max(0,1-c['erosion_ai']*c['tau_ai'])*gain;rev=labor+nonlabor+ai+p['vat_yield']*p['uc']*(w*(dw-labor)+n*(dn-nonlabor-ai));need=1.1*np.asarray(case['benefits'])+base.spb
  debt=float(base.I);cap=max(0,debt);balances=[]
  for t in range(1,26):
   debt=(1+base.interest)*debt+(need[t-1]+base.F-rev[t-1])*(1+base.growth)**t;cap=max(cap,debt/(1+base.interest)**t);balances.append(debt/(1+base.growth)**t)
  first=lambda m:int(np.flatnonzero(m)[0]+1) if np.any(m) else np.nan
  res=dict(case_id=cid,anchor=row.anchor,pressure_mode=row.pressure_mode,first_annual=first(rev-need-base.F>=0),first_return=first(np.asarray(balances)<=0),capital_25=cap,balance_10=balances[9],balance_25=balances[24]);prior=saved[(saved.case_id==cid)&saved.anchor.eq(row.anchor)&saved.pressure_mode.eq(row.pressure_mode)].iloc[0]
  for k in ['first_annual','first_return']:assert np.isclose(res[k],prior[k],equal_nan=True)
  for k in ['capital_25','balance_10','balance_25']:err=abs(res[k]-prior[k]);maxerr=max(maxerr,err);assert err<1e-12
  finance.append(res)
ff=pd.DataFrame(finance);ch=ff[ff.case_id.eq(1)];assert set(ch.first_return)=={14.,15.} and (ch.first_annual==9).all()
ff.to_csv(O/'FINANCIACION_LABORAL_56_RECONSTRUIDA.csv',index=False)
out={'status':'PASS','certified_context_coefficient_variable_combinations':1440,'certified_intervals':len(rows),'certificate_scope':'Analytical derivative intervals, registered beta=gamma=1, each side of the translation cap. Positive registered domain only.','labour_financing_paths':len(ff),'max_nominal_error':maxerr,'Chile_moderate_r4_return_years':sorted(ch.first_return.unique().tolist()),'source_hashes':hashes}
(O/'VERIFICACION_COMPLEMENTOS.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in out.items() if k!='source_hashes'}))
