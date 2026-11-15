from pathlib import Path
import os,sys,importlib.util
sys.dont_write_bytecode=True
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[name]='1'
N=Path(__file__).resolve().parents[1];S=N.parent;I=S/'evidencia/insumos';C=S/'candidato_iva_destino'
sys.path[:0]=[str(S.parent/'paso_07g/candidato'),str(C),str(C/'src')]
import numpy as np,pandas as pd
from scripts import run_official_monte_carlo as mc,run_official_tier_a as ta
from captura_conciliada import prepare,evaluate,envelope,response_index
x={p.stem:pd.read_parquet(p) for p in I.glob('*.parquet') if p.stem!='sorteos'}
x['values']=ta.normalize_keys(x['values']);value=ta.value_lookup(x['values'])
fiscal=x['fiscal_anchor'].query('year==2024').set_index('country_id')
class Central:
 size=1
 def array(self,name,*,country=None,scenario=None,policy=None,regime=None,force_draw=False):
  return np.array([value(name,country=country,scenario=scenario,policy=policy,regime=regime)])
def old_module():
 spec=importlib.util.spec_from_file_location('original_mc_fiscal02',I/'monte_carlo_original.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m
def build(sampler,country,scenario,regime,cs,rd,policy):
 old=mc.compute_cell_arrays(sampler,x,country,scenario,regime,policy,cs,rd)
 v=lambda name:value(name,country=country)
 a=lambda name:sampler.array(name,country=country)
 r=fiscal.loc[country]
 p=prepare(g=cs['g_ai_level'],delta_w=old['omega_l']*cs['g_ai_level'],ls=v('LS_labor_share'),pit=r.pit_gdp/100,cit=r.cit_gdp/100,ssc=r.social_contrib_gdp/100,vat_yield=v('tau_C_eff'),chi_k=a('chi_Kbase'),chi_dom=a('chi_dom'),psi=a('psi_shift'),chi_k0=v('chi_Kbase'),chi_dom0=v('chi_dom'),psi0=v('psi_shift'),base_broadening=rd['base_broadening_delta'],index_l=v('tau_L_eff'),index_k=v('tau_K_eff'),index_c=v('tau_C_eff'),delta_l=rd['tau_l_delta'],delta_k=rd['tau_k_delta'],delta_c=rd['tau_c_delta'],erosion_l=rd['epsilon_ero_l'],erosion_k=rd['epsilon_ero_k'],erosion_c=rd['epsilon_ero_c'],lambda_ai=cs['lambda_ai'],tau_ai=rd['tau_ai_eff'],erosion_ai=rd['epsilon_ero_ai'])
 ref=evaluate(p,alpha_pit_k=.15,k_w=v('mpc_W'),k_n=.5*v('mpc_W'))
 env=envelope(p);ext=envelope(p,1.)
 return p,ref,env,ext,old
def policies(country):return ta.policy_instances(country,x['policy_cost'],x['wpp'])
def annuity(country,policy):
 r=x['policy_admin_transition_cost'];r=r[r.country_id.eq(country)&r.policy_id.eq(policy)].iloc[0]
 return mc.annuitize_oneoff(float(r.transition_oneoff_gdp),float(r.transition_discount_rate),int(r.transition_horizon_years))
