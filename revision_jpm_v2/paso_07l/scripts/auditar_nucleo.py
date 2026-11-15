from pathlib import Path
import sys,json,hashlib,importlib.util,itertools,math,time
from decimal import Decimal as D,localcontext
from collections import defaultdict
sys.dont_write_bytecode=True
import numpy as np,pandas as pd
from scipy.optimize import brentq
S=Path(__file__).resolve().parents[1];R=S.parent;G=R/'paso_07g';T=R/'paso_07d/costos_transicion_03';O=S/'resultados'
sources={};checks=defaultdict(int);errors=defaultdict(float);failures=[]
def path(p):
 p=R/p;sources[p.relative_to(R).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest();return p
def eq(group,a,b,tol=2e-12):
 a=np.asarray(a);b=np.asarray(b);err=float(np.max(np.abs(a-b))) if a.size else 0.
 errors[group]=max(errors[group],err);checks[group]+=int(a.size)
 if not np.isfinite(err) or err>tol:raise AssertionError((group,err,tol))
def yes(group,x):
 a=np.asarray(x);checks[group]+=int(a.size)
 if not np.all(a):raise AssertionError((group,'false'))
spec=importlib.util.spec_from_file_location('candidate_math_7l',path('paso_07g/candidato/frontera_transicion.py'));f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
items=json.loads(path('paso_07g/evidencia/CONTEXTOS_80.json').read_text());ctxs={tuple(x[k] for k in ['country_id','scenario_id','regime_id']):x['context'] for x in items}
vals=pd.read_parquet(path('paso_07d/evidencia/insumos/values.parquet'));fiscal=pd.read_parquet(path('paso_07d/evidencia/insumos/fiscal_anchor.parquet')).query('year==2024').set_index('country_id')
debt=pd.read_parquet(path('paso_07d/costos_transicion_03/evidencia/debt_guardrail_anchor.parquet'));debt=debt.query('year==2024').set_index('country_id')
def value(n,c=None):
 z=vals[vals.name.eq(n)]
 if c is not None:z=z[z.country_id.eq(c)]
 assert len(z)==1,(n,c,len(z));return float(z.iloc[0].baseline_value)
def response(t,d,e):return (1+d)*max(0,1-e*t*(1+d))/(1-e*t)
def calc(c,k,years=10,g=None,q=None,exposure=None,tau=None):
 # Direct tax accounting; this oracle never calls candidate helpers.
 p=c['prepared'];a,w,n=k;s=p['ls'];q=c['q'] if q is None else np.asarray(q);e=c['exposure'] if exposure is None else np.asarray(exposure)
 score=(c['epsilon']+(1-c['epsilon'])*q)**c['gamma']*(c['epsilon']+(1-c['epsilon'])*e)**c['beta']
 tr=np.where((q>0)&(e>0),np.minimum(1,score/c['s_frontier']),0.)
 gg=np.expm1(np.asarray(years)*np.log1p(c['phi']*tr)) if g is None else np.asarray(g)
 sp=np.where(q==0,s,1/(1+((1-s)/s)*np.exp(-c['pressure_per_q']*q)))
 dw=(sp-s)+sp*gg;dn=(s-sp)+(1-sp)*gg
 tl=(p['ssc']+(1-a)*p['pit'])/s*p['ul'];tn=(p['cit']*p['relative_base']+a*p['pit'])/(1-s)*p['uk'];v=p['vat_yield']*p['uc']
 tau=c['tau_ai'] if tau is None else np.asarray(tau);j=c['lambda_ai']*tau*np.maximum(0,1-c['erosion_ai']*tau)
 labor=tl*dw;capital=tn*dn;ai=j*gg;cons=w*(dw-labor)+n*(dn-capital-ai);rev=labor+capital+ai+v*cons
 L=tl+v*w*(1-tl);N=tn+v*n*(1-tn);A=L*sp+N*(1-sp)+(1-v*n)*j;B=(L-N)*(sp-s)
 return dict(g=gg,T=tr,dw=dw,dn=dn,sp=sp,revenue=rev,A=A,B=B,L=L,N=N,v=v,j=j)
def decimal(c,k,g):
 with localcontext() as lc:
  lc.prec=50;z=lambda x:D(str(x));p=c['prepared'];a,w,n=map(z,k);s=z(p['ls']);q=z(c['q']);gg=z(g)
  sp=1/(1+((1-s)/s)*(-z(c['pressure_per_q'])*q).exp());dw=sp*(1+gg)-s;dn=gg-dw
  tl=(z(p['ssc'])+(1-a)*z(p['pit']))/s*z(p['ul'])*dw;tn=(z(p['cit'])*z(p['relative_base'])+a*z(p['pit']))/(1-s)*z(p['uk'])*dn
  ai=gg*z(c['lambda_ai'])*z(c['tau_ai'])*max(D(0),1-z(c['erosion_ai'])*z(c['tau_ai']))
  return float(tl+tn+ai+z(p['vat_yield'])*z(p['uc'])*(w*(dw-tl)+n*(dn-tn-ai)))

annual=pd.read_csv(path('paso_07d/costos_transicion_03/resultados/FRONTERAS_ANUALES_480.csv'));inverse=pd.read_csv(path('paso_07d/costos_transicion_03/resultados/INVERSAS_RECALCULADAS.csv'))
vertices=list(itertools.product([0.,.3],[0.,1.],[0.,1.]));revs={};rows=[];certificates=[]
for key,c in ctxs.items():
 country,scenario,reg=key;p=c['prepared'];fr=fiscal.loc[country]
 for param,col in [('pit','pit_gdp'),('cit','cit_gdp'),('ssc','social_contrib_gdp')]:eq('anclas_fiscales',p[param],fr[col]/100)
 for ch,pkey in [('L','ul'),('K','uk'),('C','uc')]:
  t=value('tau_'+ch+'_eff',country);d=value('tau_'+ch+'_relative_delta_'+reg);e=value('epsilon_ero_'+ch+'_'+reg)
  yes('dominio_respuesta',1-e*t>0 and d>=-1);eq('respuesta_regimen',p[pkey],response(t,d,e));eq('normalizacion_r0',response(t,0,e),1.)
 shift=value('psi_shift',country);broad=value('base_broadening_delta_'+reg)
 eq('base_corporativa_relativa',p['relative_base'],(1-shift*(1-broad))/(1-shift))
 pressure=value('lambda_LS',country)*(-(value('delta_s',country)-value('zeta_s',country)*value('RST',country))*value('E_auto',country)+value('psi_s',country)*value('E_aug',country))
 eq('presion_laboral',c['pressure_per_q'],pressure)
 yes('dominio_actual',0<p['ls']<1 and 0<c['q']<c['q_bar']-c['epsilon_mu'] and c['phi']>0 and c['beta']>0 and c['gamma']>0)
 d=debt.loc[country];ii=d.interest_payments_gdp*(1+d.nominal_growth_rate)/d.gross_debt_gdp_lag
 eq('interes_heredado',ii,d.nominal_interest_rate)
 spb=max(0,(ii-d.nominal_growth_rate)/(1+d.nominal_growth_rate)*d.gross_debt_gdp/100-d.primary_balance_gdp/100)
 eq('ajuste_primario',spb,value('sPB_plus_gdp_ratio',country))
 local=[]
 for mode,k in [('reference',c['reference'])]+[(f'v{i}',k) for i,k in enumerate(vertices)]:
  z=calc(c,k);rz=f.capture(c,k);A=float(z['A']);B=float(z['B']);local.append(float(z['revenue']))
  eq('nucleo_vs_contabilidad_directa',z['revenue'],rz['revenue']);eq('ganancia_preparada',z['g'],p['g']);yes('pendiente_positiva',A>0)
  for gg in [0.,1e-12,1e-8,float(z['g']),.1]:
   ref=decimal(c,k,gg);rr=f.capture(c,k,g=gg);eq('ingresos_precision50',rr['revenue'],ref,2e-14);eq('identidad_afin',ref,A*gg+B,2e-14)
  anchor=f.capture(c,k,q=0,g=0);eq('ancla_cero',anchor['revenue'],0.,0);yes('media_indefinida_cero',np.isnan(f.capture(c,k,g=0)['M_average']))
  pathz=calc(c,k,years=np.arange(1,26));pathf=f.capture(c,k,years=np.arange(1,26))
  eq('sendas_ingresos_25',pathz['revenue'],pathf['revenue']);eq('conservacion_ingreso',pathz['dw']+pathz['dn'],pathz['g'])
  frozen=dict(c,pressure_per_q=0.);eq('efecto_distributivo_total',z['revenue']-calc(frozen,k)['revenue'],B*(1+z['g']))
  for var,lo,hi in [('q',c['q'],c['q_bar']-c['epsilon_mu']),('exposure',c['exposure'],1.)]:
   points=np.linspace(lo+1e-5,hi-1e-5,97);step=1e-7
   diff=(calc(c,k,**{var:points+step})['revenue']-calc(c,k,**{var:points-step})['revenue'])/(2*step)
   tr=calc(c,k,**{var:points})['T'];smooth=np.abs(tr-1)>1e-5
   # On the capped branch the analytic derivative remains defined away from the corner.
   smooth|=(calc(c,k,**{var:points-step})['T']==1)
   eq('derivada_operacional',f.derivative(c,k,points,var)[smooth],diff[smooth],2e-8)
   bound=f.monotonic_bound(c,k,lo,hi,var)
   yes('cota_derivada_conservadora',np.all(f.derivative(c,k,points,var)>=bound-1e-12))
  rows.append(dict(country_id=country,scenario_id=scenario,regime_id=reg,mode=mode,g=float(z['g']),A=A,B=B,M=float(z['revenue']/z['g']),revenue=float(z['revenue'])))
 revs[key]=local
 # Exact vertex interpolation identity at predetermined interior points.
 for x,y,z in itertools.product([.17,.53,.89],[.13,.59],[.23,.71]):
  weights=[(x if a else 1-x)*(y if w else 1-y)*(z if n else 1-z) for a,w,n in itertools.product([0,1],repeat=3)]
  r=float(calc(c,(.3*x,y,z))['revenue']);eq('interpolacion_multiafin',r,np.dot(weights,local[1:]),2e-14);yes('envolvente_vertices',min(local[1:])-1e-14<=r<=max(local[1:])+1e-14)
print('Nucleo: 80 contextos, 720 combinaciones, anclas y derivadas comprobadas.',flush=True)

for r in annual.itertuples(index=False):
 rv=revs[(r.country_id,r.scenario_id,r.regime_id)]
 for rule,xi,spb in [('B0',0.,0.),('B1',.1,0.),('B2',.1,r.spb)]:
  for mode,rev in [('reference',rv[0]),('uniform',min(rv[1:])),('possible',max(rv[1:]))]:
   ceiling=rev-(1+xi)*r.benefits-spb;eq('fronteras_anuales',ceiling,getattr(r,f'Fmax_{rule}_{mode}'))
   yes('clasificacion_anual',(ceiling>=r.F_recurring_author)==getattr(r,f'covers_recurring_{rule}_{mode}'))

# Independent operational searches use roots of the analytical derivative plus the
# translation kink; reported unreachable cases are compared with the global maximum
# on these pieces. The search is paired with the candidate's interval certificates.
groups=['country_id','scenario_id','regime_id','alpha','k_w','k_n']
operational_total=0
for keys,sub in inverse.groupby(groups,sort=False):
 c=ctxs[keys[:3]];k=keys[3:];z=calc(c,k);Q=sub.required_revenue.to_numpy();A=float(z['A']);B=float(z['B'])
 gg=np.maximum(0,(Q-B)/A);eq('inversa_ganancia',sub.g_required,gg);eq('residuo_inversa_ganancia',calc(c,k,g=gg)['revenue'],Q)
 tr=np.expm1(np.log1p(gg)/10)/c['phi'];eq('inversa_traduccion',sub.T_required_frozen_distribution,tr)
 peak=min(1.,1/(2*c['erosion_ai'])) if c['erosion_ai']>0 else 1.
 base=float(calc(c,k,tau=0)['revenue']);peakrev=float(calc(c,k,tau=peak)['revenue']);eps=2e-12
 for r in sub.itertuples(index=False):
  if r.ai_status=='covered_without_additional_AI':yes('inversa_IA',base>=r.required_revenue-eps and r.tau_ai_required==0)
  elif r.ai_status=='no_root_in_effective_rate_domain':yes('inversa_IA',peakrev<r.required_revenue+eps)
  else:
   eq('inversa_IA',calc(c,k,tau=r.tau_ai_required)['revenue'],r.required_revenue);yes('raiz_IA_rama_creciente',0<=r.tau_ai_required<=peak+eps)
 for var,lo,hi in [('q',c['q'],c['q_bar']-c['epsilon_mu']),('exposure',c['exposure'],1.)]:
  def fun(x):return float(calc(c,k,**{var:x})['revenue'])
  # Stationary points are found independently by differentiating the expanded
  # identity. This avoids invoking production derivative/solver in the oracle.
  def der(x):
   zz=calc(c,k,**{var:x});q=x if var=='q' else c['q'];tr=float(zz['T']);gg=float(zz['g']);sp=float(zz['sp'])
   exponent=c['gamma'] if var=='q' else c['beta'];dt=0 if tr>=1 else exponent*tr*(1-c['epsilon'])/(c['epsilon']+(1-c['epsilon'])*x)
   out=float(zz['A'])*10*c['phi']*(1+c['phi']*tr)**9*dt
   if var=='q':out+=(zz['L']-zz['N'])*c['pressure_per_q']*sp*(1-sp)*(1+gg)
   return float(out)
  other=c['exposure'] if var=='q' else c['q'];exponent=c['gamma'] if var=='q' else c['beta'];otherpower=c['beta'] if var=='q' else c['gamma'];ee=c['epsilon']
  cap=((c['s_frontier']/(ee+(1-ee)*other)**otherpower)**(1/exponent)-ee)/(1-ee)
  cuts=[lo]+([cap] if lo<cap<hi else [])+[hi];turns=[]
  for left,right in zip(cuts[:-1],cuts[1:]):
   grid=np.linspace(left+1e-11,right-1e-11,65);ds=np.array([der(x) for x in grid])
   for x,y,dx,dy in zip(grid[:-1],grid[1:],ds[:-1],ds[1:]):
    if dx*dy<0:turns.append(brentq(der,x,y,xtol=1e-14))
  cuts=sorted(cuts+turns);maximum=max(map(fun,cuts));leftrev=fun(lo)
  for r in sub.itertuples(index=False):
   requirement=r.required_revenue;root=getattr(r,var+'_required');status=getattr(r,var+'_status')
   if status.startswith('already_covered'):
    yes('inversa_operacional_ya_cubierta',leftrev>=requirement-eps);eq('inversa_operacional_inicio',root,lo)
   elif status.startswith('not_reachable'):
    yes('inversa_operacional_sin_cruce',maximum<requirement+eps)
   else:
    eq('inversa_operacional_residuo',fun(root),requirement,2e-11)
    found=None
    for left,right in zip(cuts[:-1],cuts[1:]):
     if fun(left)>=requirement:found=left;break
     if fun(right)>=requirement:found=brentq(lambda x:fun(x)-requirement,left,right,xtol=1e-14);break
    yes('inversa_operacional_raiz_encontrada',found is not None);eq('inversa_operacional_minimo',root,found,2e-10)
   operational_total+=1
  certificates.append(dict(country_id=keys[0],scenario_id=keys[1],regime_id=keys[2],alpha=k[0],k_w=k[1],k_n=k[2],variable=var,stationary_points=len(turns),pieces=len(cuts)-1,maximum_revenue=maximum))
print('Inversas: 25.920 ganancias/IA y 51.840 adopcion/exposicion comprobadas.',flush=True)

# Explicit synthetic boundaries, distinct from scientific recalibration.
c=ctxs[('CHL','mid','r4')];k=c['reference'];z=calc(c,k);A=float(z['A']);B=float(z['B'])
yes('borde_cero_cubre',f.invert_gain(c,k,B)['g_required']==0)
for bad in [-1e-6,float('nan')]:
 try:f.capture(c,k,g=bad)
 except ValueError:checks['dominio_ganancia_rechazado']+=1
 else:raise AssertionError('invalid gain accepted')
zero=dict(c,prepared=dict(c['prepared'],pit=0.,cit=0.,ssc=0.,vat_yield=0.),lambda_ai=0.)
yes('inversa_pendiente_cero_explicitada',f.invert_gain(zero,k,.01)['gain_status']=='nonincreasing_requires_interval_analysis')

pd.DataFrame(rows).to_csv(O/'NUCLEO_720_RECONSTRUIDO.csv',index=False)
pd.DataFrame(certificates).to_csv(O/'DIAGNOSTICO_INVERSAS_1440.csv',index=False)
result={'status':'PASS','scope':'Algebra y correspondencia numerica del dominio registrado; oraculo separado y Decimal de 50 digitos.','contexts':80,'coefficient_contexts':720,'annual_rows':480,'gain_and_AI_inverse_rows':len(inverse),'operational_inverse_checks':operational_total,'checks_by_group':dict(checks),'max_absolute_error':dict(errors),'source_hashes':sources,'note':'El contraste de extremos operacionales combina busqueda separada por tramos con revision analitica de los certificados por intervalos; no atribuye pruebas globales a un muestreo aislado.'}
(O/'VERIFICACION_NUCLEO.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','total_scalar_checks':sum(checks.values()),'max_error':max(errors.values())}))
