from comun import *
import json
checks=[]
def ck(name,condition):
 checks.append({'check':name,'pass':bool(condition)});assert condition,name
def near(a,b):return np.allclose(a,b,atol=2e-13,rtol=1e-12)
for t in [0,.05,.2,.9]:
 for e in [0,.5,1]:ck(f'neutral response {t} {e}',near(response_index(t,0,e),1))
for c in ta.COUNTRIES:
 s=value('LS_labor_share',country=c);r=fiscal.loc[c];g=np.array([.01,.05])
 kw=dict(g=g,delta_w=s*g,ls=s,pit=r.pit_gdp/100,cit=r.cit_gdp/100,ssc=r.social_contrib_gdp/100,vat_yield=value('tau_C_eff',country=c),chi_k=.7,chi_dom=.95,psi=.15,chi_k0=.7,chi_dom0=.95,psi0=.15,base_broadening=0,index_l=value('tau_L_eff',country=c),index_k=value('tau_K_eff',country=c),index_c=value('tau_C_eff',country=c),delta_l=0,delta_k=0,delta_c=0,erosion_l=.5,erosion_k=.5,erosion_c=.5,lambda_ai=.1,tau_ai=0,erosion_ai=.5)
 p=prepare(**kw)
 for a in [0,.15,.3,1]:
  z=evaluate(p,alpha_pit_k=a,k_w=.8,k_n=.4)
  ck(f'income tax anchor constant composition {c} {a}',near(z['tax_l']+z['tax_cit']+z['tax_pit_k'],g*(r.pit_gdp+r.cit_gdp+r.social_contrib_gdp)/100))
  ck(f'income flow conservation {c} {a}',near(z['disposable_w']+z['disposable_n']+z['tax_l']+z['tax_cit']+z['tax_pit_k']+z['tax_ai'],g))
  z0=evaluate(prepare(**(kw|{'lambda_ai':0})),alpha_pit_k=a,k_w=.8,k_n=.4)
  ck(f'no ordinary rent exemption with AI tax zero {c} {a}',near(z['M'],z0['M']))
  za=evaluate(prepare(**(kw|{'tau_ai':.1})),alpha_pit_k=a,k_w=.8,k_n=.4)
  ck(f'AI net contribution including induced VAT {c} {a}',near(za['M']-z['M'],za['tax_ai']/g*(1-.4*kw['vat_yield'])))
 ck('negative consumption preserved '+c,bool((evaluate(prepare(**(kw|{'delta_w':-g})),alpha_pit_k=.15,k_w=1,k_n=0)['tax_vat']<0).all()))
 ck('relative composition identity '+c,near(p['relative_base'],1))
 # Independent evaluation of multiaffine interpolation at interior points.
 q=prepare(**(kw|{'delta_w':.7*g,'base_broadening':.2,'tau_ai':.08,'delta_l':.1,'delta_k':.08,'delta_c':.05}))
 env=envelope(q)
 for a,w,n in [(.1,.2,.8),(.22,.7,.1),(.15,.5,.5)]:
  z=evaluate(q,alpha_pit_k=a,k_w=w,k_n=n)['M'];inter=np.zeros_like(g)
  for av,wv,nv in env['vertices']:
   weight=(a/.3 if av else 1-a/.3)*(w if wv else 1-w)*(n if nv else 1-n)
   inter+=weight*evaluate(q,alpha_pit_k=av,k_w=wv,k_n=nv)['M']
  ck(f'interpolation identifies exact box {c} {a}',near(z,inter) and bool(((z>=env['M_low']-1e-14)&(z<=env['M_high']+1e-14)).all()))
result={'status':'PASS','n_checks':len(checks),'checks':checks,'scope':'Accounting and domain verification, not causal validation.'}
(N/'evidencia/PRUEBAS_MODELO.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('PASS',len(checks),'model checks')
