"""Independent central-cell oracle and reaggregation of persisted simulation data."""
from pathlib import Path
from decimal import Decimal as D,getcontext
from itertools import product
import csv,math,json
import numpy as np,pandas as pd
getcontext().prec=40
N=Path(__file__).resolve().parents[1];S=N.parent;I=S/'evidencia/insumos';O=N/'resultados'
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
v=read(I/'valores_oficiales.csv')
def val(c,n):
 rows=[r for r in v if r['name']==n and r['country_id']==c]
 if not rows:rows=[r for r in v if r['name']==n and not r['country_id']]
 assert len(set(r['baseline_value'] for r in rows))==1,(c,n)
 return D(rows[0]['baseline_value'])
anc={r['country_id']:r for r in read(O/'ANCLAS_RECONCILIADAS_2024.csv') if r['alpha_PIT_K']=='0.15'}
source={tuple(r[k] for k in ['country_id','scenario_id','regime_id']):r for r in read(I/'distancias.csv')}
channels=read(O/'CANALES_CONCILIADOS_80.csv');count=0
for r in channels:
 c,sc,reg=r['country_id'],r['scenario_id'],r['regime_id'];g=D(source[c,sc,reg]['g_ai_level']);s=val(c,'LS_labor_share')
 qbar=1-val(c,'omega_I')*val(c,'I_adopt_informality')-val(c,'omega_G')*val(c,'Gap_excluded_indicators');ep=val(c,'epsilon_mu');q=min(max(val(c,'q_use_target'),ep),qbar-ep)
 pressure=(-(val(c,'delta_s')-val(c,'zeta_s')*val(c,'RST'))*val(c,'E_auto')+val(c,'psi_s')*val(c,'E_aug'))*q
 lsnew=1/(1+math.exp(-(math.log(float(s/(1-s)))+float(val(c,'lambda_LS')*pressure))))
 dw=D(str(lsnew))*(1+g)-s;dn=g-dw
 def response(ch):
  t=val(c,'tau_'+ch+'_eff');delta=val(c,'tau_'+ch+'_relative_delta_'+reg);e=val(c,'epsilon_ero_'+ch+'_'+reg)
  return (1+delta)*max(D(0),1-e*t*(1+delta))/(1-e*t)
 ul,uk,uc=[response(ch) for ch in ['L','K','C']]
 b=val(c,'base_broadening_delta_'+reg);psi=val(c,'psi_shift');rho=(1-psi*(1-b))/(1-psi)
 pit=D(anc[c]['PIT_gdp']);cit=D(anc[c]['CIT_gdp']);ssc=D(anc[c]['SSC_gdp']);yc=val(c,'tau_C_eff')
 lam=val(c,'lambda_AI_'+sc);tai=val(c,'tau_AI_eff_'+reg);eai=val(c,'epsilon_ero_AI_'+reg);AI=g*lam*tai*max(D(0),1-eai*tai)
 def model(a,w,n):
  L=(ssc+(1-a)*pit)/s*dw*ul;K=cit/(1-s)*dn*rho*uk;PK=a*pit/(1-s)*dn*uk;C=w*(dw-L)+n*(dn-K-PK-AI);VAT=yc*uc*C
  return (L+K+PK+AI+VAT)/g,(L,K,PK,AI,VAT)
 M,terms=model(D('.15'),val(c,'mpc_W'),val(c,'mpc_W')/2)
 assert abs(M-D(r['M_reference']))<D('3e-12'),(c,sc,reg,'M')
 for k,t in zip(['tax_l','tax_cit','tax_pit_k','tax_ai','tax_vat'],terms):assert abs(t-D(r[k]))<D('3e-13'),(c,sc,reg,k)
 for amax,suffix in [(D('.3'),''),(D('1'),'extreme_')]:
  ms=[model(a,w,n)[0] for a,w,n in product([D(0),amax],[D(0),D(1)],[D(0),D(1)])]
  assert abs(min(ms)-D(r['M_'+suffix+'low']))<D('3e-12')
  assert abs(max(ms)-D(r['M_'+suffix+'high']))<D('3e-12')
 count+=1
det=pd.read_csv(O/'DETERMINISTA_CONCILIADO_960.csv');ch=pd.read_csv(O/'CANALES_CONCILIADOS_80.csv');joined=det.merge(ch[['country_id','scenario_id','regime_id','M_reference','M_low','M_high']],on=['country_id','scenario_id','regime_id'],suffixes=('','_channel'),validate='many_to_one')
for mode in ['reference','low','high']:
 assert np.allclose(joined['M_'+mode],joined['M_'+mode+'_channel'],atol=1e-14)
 for rule,req in [('B0',joined.benefits),('B1',1.1*joined.benefits),('B2',1.1*joined.benefits+joined.spb)]:
  assert np.array_equal((joined.g*joined['M_'+mode]-joined.F>=req).to_numpy(),joined[rule+'_'+mode].to_numpy())
  assert np.allclose(joined['F_max_'+rule+'_'+mode],joined.g*joined['M_'+mode]-req,atol=1e-14)
draws=pd.read_parquet(O/'SORTEOS_CONCILIADOS_80x5000.parquet');summ=pd.read_csv(O/'MONTE_CARLO_5000_TODAS_CELDAS.csv');groups={key:z for key,z in draws.groupby(['country_id','scenario_id','regime_id'])}
lookup={(r.country_id,r.policy_variant_id,r.scenario_id,r.regime_id,r.timing):r for r in det.itertuples()}
mc_count=0
for r in summ.itertuples():
 z=groups[r.country_id,r.scenario_id,r.regime_id];p=lookup[r.country_id,r.policy_variant_id,r.scenario_id,r.regime_id,r.timing];pid=p.policy_id
 A=float(val(r.country_id,pid+'_admin_cost_new_gdp'));R=float(val(r.country_id,pid+'_transition_recurring_gdp'));J=float(val(r.country_id,pid+'_transition_oneoff_gdp'));i=float(val(r.country_id,pid+'_transition_discount_rate'));n=int(val(r.country_id,pid+'_transition_horizon_years'));leak=float(val(r.country_id,pid+'_leakage_fixed_gdp'))
 ann=J/n if i==0 else J*i/(1-(1+i)**(-n));F=A+R+leak*z.leakage_multiplier+(ann if r.timing=='annual_equivalent' else 0)
 M=z[{'iva_only':'M_iva_only','reference':'M_reference','uniform':'M_low','possible':'M_high'}[r.mode]];req=p.benefits if r.rule=='B0' else 1.1*p.benefits+p.spb
 k=int((z.valid&(z.g*M-F>=req)).sum());assert k==r.crossings,(r.country_id,r.scenario_id,r.regime_id,r.policy_variant_id,r.mode,r.rule,k,r.crossings);mc_count+=1
matched=pd.read_csv(O/'CHILE_EMPAREJADO_50000.csv');dd=pd.read_parquet(O/'SORTEOS_CHILE_50000.parquet');match_count=0
for r in matched.itertuples():
 p=lookup['CHL','GMI:GMI_ideal_aggregate','mid','r0',r.timing];M=dd[{'original':'M_original','iva_only':'M_iva_only','reference':'M_reference','uniform':'M_low','possible':'M_high'}[r.mode]];req=p.benefits if r.rule=='B0' else 1.1*p.benefits
 assert int((dd.g*M-p.F>=req).sum())==r.crossings;match_count+=1
for rule in ['B0','B1','B2']:assert (~det[rule+'_low']|det[rule+'_reference']).all() and (~det[rule+'_reference']|det[rule+'_high']).all()
result={'status':'PASS','independent_Decimal_channels':count,'deterministic_rows_reconciled':len(det),'full_MC_summary_rows_reaggregated':mc_count,'paired_MC_summary_rows_reaggregated':match_count,'notes':'No candidate fiscal functions imported. Independent central formula and persisted-draw recalc.'}
(N/'evidencia/VERIFICACION_INDEPENDIENTE.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False));print(det[det.scenario_id.ne('stress')&det.B2_reference][['country_id','policy_variant_id','scenario_id','regime_id','timing','V_reference']].to_string(index=False));print(pd.read_csv(O/'CHILE_DETERMINISTA_MODERADO_R0.csv')[['timing','M_reference','M_low','M_high','V_reference','F_max_B2_reference','F_max_B2_low','F_max_B2_high']].to_string(index=False))
