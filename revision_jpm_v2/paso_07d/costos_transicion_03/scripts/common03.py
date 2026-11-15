from pathlib import Path
import sys
sys.dont_write_bytecode=True
T=Path(__file__).resolve().parents[1];S=T.parent;N=S/'conciliacion_fiscal_02';R=S.parent;P=R.parent
sys.path[:0]=[str(R/'paso_07g/candidato'),str(N/'scripts')]
import comun as cf
from frontera_transicion import *
import pandas as pd
O=T/'resultados';E=T/'evidencia'
cn=cf.Central()
scalar=lambda z:float(np.asarray(z).ravel()[0])
def context(country,scenario,regime):
    cs=cf.mc.build_country_scenario_draws(cn,cf.x,country,scenario,cn.array('E_prod_frontier'));rd=cf.mc.build_regime_draws(cn,regime)
    p,ref,env,ext,old=cf.build(cn,country,scenario,regime,cs,rd,cf.policies(country)[0])
    p={k:scalar(v) for k,v in p.items()}
    val=lambda k:cf.value(k,country=country)
    ctx=dict(prepared=p,q=scalar(cs['q_prod']),exposure=scalar(cs['eprod']),epsilon=scalar(cs['epsilon']),beta=scalar(cs['beta']),gamma=scalar(cs['gamma']),s_frontier=scalar(cs['s_frontier']),phi=scalar(cs['phi_y_nominal']),lambda_ai=scalar(cs['lambda_ai']),tau_ai=scalar(rd['tau_ai_eff']),erosion_ai=scalar(rd['epsilon_ero_ai']),q_bar=scalar(cs['q_bar']),epsilon_mu=val('epsilon_mu'),lambda_q=scalar(cs['lambda_q']),leak_multiplier=scalar(rd['leakage_multiplier']))
    ctx['pressure_per_q']=val('lambda_LS')*(-(val('delta_s')-val('zeta_s')*val('RST'))*val('E_auto')+val('psi_s')*val('E_aug'))
    ctx['reference']=(.15,val('mpc_W'),.5*val('mpc_W'))
    return ctx

def cost_path(country,pol,wpp,*,harmonized=False):
    policy=pol['policy_id'];base=cf.ta.eligible_metric(wpp,country,2024,policy)
    pop=wpp[wpp.ISO3_code.eq(country)].groupby('Time').PopTotal.sum()
    ratios=[]
    for t in range(1,26):
        ratio=cf.ta.eligible_metric(wpp,country,2024+t,policy)/base
        if harmonized and policy=='PEN' and country=='COL':ratio/=float(pop.loc[2024+t]/pop.loc[2024])
        ratios.append(ratio)
    return np.array(ratios)*pol['cost_2024_gdp']

def costs(country,policy,ctx):
    r=cf.x['policy_admin_transition_cost'].query('country_id==@country and policy_id==@policy').iloc[0]
    f=float(r.admin_cost_new_gdp-r.admin_savings_existing_gdp+r.transition_recurring_gdp+r.leakage_fixed_gdp*ctx['leak_multiplier'])
    return f,float(r.transition_oneoff_gdp),cf.annuity(country,policy)
