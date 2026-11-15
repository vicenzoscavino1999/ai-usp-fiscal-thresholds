from pathlib import Path
import sys,json,hashlib,importlib.util,csv,math
from decimal import Decimal as D,localcontext
sys.dont_write_bytecode=True
import numpy as np,pandas as pd
S=Path(__file__).resolve().parents[1];R=S.parent;T=R/'paso_07d/costos_transicion_03';O=S/'bloque_1_matematica';E=S/'evidencia'
def module(name,p):
 spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
new=module('new_frontier',S/'candidato/frontera_transicion.py');old=module('old_frontier',E/'frontera_transicion_07d.py')
tax=module('new_capture',S/'candidato/captura_conciliada.py')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
items=json.loads((E/'CONTEXTOS_80.json').read_text(encoding='utf-8'));ctxs={tuple(x[k] for k in ['country_id','scenario_id','regime_id']):x['context'] for x in items}
checks=0;errors=[];rows=[];positive=0;core_checks=0
def check(c,msg):
 global checks
 assert c,msg;checks+=1
def oracle(ctx,coef,g):
 with localcontext() as lc:
  lc.prec=45
  dec=lambda v:D(str(v));p=ctx['prepared'];s=dec(p['ls']);q=dec(ctx['q']);a,w,n=map(dec,coef);gg=dec(g)
  sp=1/(1+(-(s/(1-s)).ln()-dec(ctx['pressure_per_q'])*q).exp())
  dw=sp*(1+gg)-s;dn=gg-dw
  tl=(dec(p['ssc'])+(1-a)*dec(p['pit']))/s*dw*dec(p['ul'])
  tk=(dec(p['cit'])*dec(p['relative_base'])+a*dec(p['pit']))/(1-s)*dn*dec(p['uk'])
  ta=dec(ctx['lambda_ai'])*gg*dec(ctx['tau_ai'])*max(D(0),1-dec(ctx['erosion_ai'])*dec(ctx['tau_ai']))
  tv=dec(p['vat_yield'])*dec(p['uc'])*(w*(dw-tl)+n*(dn-tk-ta))
  return float(tl+tk+ta+tv),float(dw),float(sp)
for key,ctx in ctxs.items():
 for mode,coef in [('reference',ctx['reference'])]+[(f'v{i}',v) for i,v in enumerate(new.VERTICES)]:
  A,B=new.affine_capture(ctx,coef)
  check(A>0,'positive slope')
  z0=new.capture(ctx,coef,g=0.);check(abs(float(z0['revenue'])-B)<2e-15,'zero endpoint intercept')
  check(np.isnan(z0['M_average']),'undefined average at zero')
  anchor=new.capture(ctx,coef,q=0);check(float(anchor['revenue'])==0 and float(anchor['dw'])==0,'joint no-AI anchor')
  for g in [0.,1e-12,1e-8,ctx['prepared']['g'],.1]:
   z=new.capture(ctx,coef,g=g);r,dw,sp=oracle(ctx,coef,g);err=abs(float(z['revenue'])-r);errors.append(err)
   check(err<2e-14,'independent decimal taxes');check(abs(float(z['dw'])-dw)<2e-14,'independent factor increment')
   check(abs(float(z['revenue'])-(A*g+B))<2e-14,'affine identity')
   p=dict(ctx['prepared'],g=np.asarray(g),dw=z['dw'],dn=g-z['dw'],ai=ctx['lambda_ai']*g*ctx['tau_ai']*max(0,1-ctx['erosion_ai']*ctx['tau_ai']))
   zz=tax.evaluate(p,alpha_pit_k=coef[0],k_w=coef[1],k_n=coef[2]);core_checks+=1
   check(abs(float(zz['revenue'])-r)<2e-14,'channel core consistent')
   check(bool(np.isnan(zz['M'])) if g==0 else abs(float(zz['M'])-r/g)<1e-4,'core average domain')
  g=ctx['prepared']['g'];step=1e-5
  deriv=float(new.capture(ctx,coef,g=g+step)['revenue']-new.capture(ctx,coef,g=g-step)['revenue'])/(2*step)
  check(abs(deriv-A)<1e-9,'finite difference derivative')
  path=new.capture(ctx,coef,years=np.arange(1,26));prior=old.capture(ctx,coef,years=np.arange(1,26))
  for name in ['g','dw','revenue','share_prime']:check(np.array_equal(path[name],prior[name]),'positive path unchanged '+name)
  positive+=25
  if B>=0:
   inv=new.invert_gain(ctx,coef,B);check(inv['g_required']==0 and float(z0['revenue'])>=B-2e-15,'zero root attained')
  frozen=dict(ctx,pressure_per_q=0.)
  no_distribution=new.capture(frozen,coef,g=g)
  rows.append(dict(zip(['country_id','scenario_id','regime_id'],key))|{'mode':mode,'g':g,'share':ctx['prepared']['ls'],'share_prime':float(z0['share_prime']),'gain_slope_A':A,'intercept_B':B,'M_average':float(new.capture(ctx,coef,g=g)['M_average']),'R':float(new.capture(ctx,coef,g=g)['revenue']),'R_no_distribution_shift':float(no_distribution['revenue']),'distribution_effect_at_g':float(new.capture(ctx,coef,g=g)['revenue']-no_distribution['revenue']),'right_limit_old_minus_R_at_zero':B})
pd.DataFrame(rows).to_csv(O/'CAPTURA_MEDIA_MARGINAL_Y_DISTRIBUCION.csv',index=False)
inv=pd.read_csv(T/'resultados/INVERSAS_RECALCULADAS.csv');recomputed=[];zero_changes=0
for r in inv.itertuples(index=False):
 ctx=ctxs[(r.country_id,r.scenario_id,r.regime_id)];coef=(r.alpha,r.k_w,r.k_n);z=new.invert_gain(ctx,coef,r.required_revenue)
 check(abs(z['g_required']-r.g_required)<2e-13,'existing inverse value')
 if r.g_required==0:zero_changes+=1
 else:check(z['gain_status']==r.gain_status,'existing positive inverse status')
 revenue=float(new.capture(ctx,coef,g=z['g_required'])['revenue'])
 check(revenue>=r.required_revenue-2e-13,'inverse satisfies requirement')
 recomputed.append({k:getattr(r,k) for k in ['country_id','scenario_id','regime_id','policy_variant_id','rule','cost_treatment','mode','required_revenue']}|z|{'old_gain_status':r.gain_status,'revenue_at_required':revenue})
pd.DataFrame(recomputed).to_csv(O/'INVERSAS_GANANCIA_REVISADAS.csv',index=False)
annual=pd.read_csv(T/'resultados/FRONTERAS_ANUALES_480.csv');af=[]
for r in annual.itertuples(index=False):
 ctx=ctxs[(r.country_id,r.scenario_id,r.regime_id)];z=new.capture(ctx,ctx['reference']);revenue=float(z['revenue'])
 check(abs(revenue-r.benefits-r.Fmax_B0_reference)<2e-13,'annual original identical')
 fmax=revenue-1.1*r.benefits-r.spb;check(abs(fmax-r.Fmax_B2_reference)<2e-13,'annual B2 identical')
 af.append({'country_id':r.country_id,'scenario_id':r.scenario_id,'regime_id':r.regime_id,'policy_variant_id':r.policy_variant_id,'revenue':revenue,'Fmax_B2':fmax,'B2':fmax>=r.F_recurring_author})
pd.DataFrame(af).to_csv(O/'ANUAL_480_RECONCILIADA.csv',index=False)
values=pd.read_parquet(R/'paso_07d/evidencia/insumos/values.parquet')
names=['LS_labor_share','lambda_LS','delta_s','zeta_s','RST','E_auto','psi_s','E_aug']
values[values.name.isin(names)].to_csv(O/'PARAMETROS_PARTICIPACION_LABORAL.csv',index=False)
manifest={'status':'PASS','checks':checks,'contexts':80,'context_coefficients':len(rows),'decimal_flow_checks':len(errors),'max_decimal_abs_error':max(errors),'core_channel_checks':core_checks,'positive_horizon_flows_identical':positive,'gain_inverses_checked':len(inv),'zero_inverse_status_changes':zero_changes,'annual_rows_identical':480,'new_datasets':False,'new_random_draws':False,'source_hashes':{str(p.relative_to(R)):sha(p) for p in [E/'CONTEXTOS_80.json',T/'resultados/INVERSAS_RECALCULADAS.csv',T/'resultados/FRONTERAS_ANUALES_480.csv',R/'paso_07d/evidencia/insumos/values.parquet']},'candidate_hashes':{p.name:sha(p) for p in (S/'candidato').glob('*.py')}}
(O/'VERIFICACION.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in manifest.items() if not k.endswith('hashes')}))
print(pd.DataFrame(rows).query("country_id=='CHL' and scenario_id=='mid' and regime_id=='r0' and mode=='reference'").to_string(index=False))
