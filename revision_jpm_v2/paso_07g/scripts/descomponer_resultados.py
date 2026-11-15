from pathlib import Path
import sys,json,hashlib,math
sys.dont_write_bytecode=True
S=Path(__file__).resolve().parents[1];R=S.parent;D=R/'paso_07d';N=D/'conciliacion_fiscal_02';O=S/'bloque_2_descomposicion'
sys.path.insert(0,str(N/'scripts'));import comun as cf
import numpy as np,pandas as pd
from scipy.stats import beta
names=['IVA_destino','base_CIT_relativa','renta_IA_ordinaria','asignacion_PIT','respuesta_normalizada','consumo_disponible','instalacion_separada']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def setup(sampler,c,sc,reg,cs,rd,pol):
 original=cf.old_module().compute_cell_arrays(sampler,cf.x,c,sc,reg,pol,cs,rd)
 p,z,env,ext,iv=cf.build(sampler,c,sc,reg,cs,rd,pol)
 val=lambda k:cf.value(k,country=c);arr=lambda k:sampler.array(k,country=c)
 g=cs['g_ai_level'];dw=original['omega_l']*g;dn=g-dw
 chi=arr('chi_Kbase');dom=arr('chi_dom');psi=np.maximum(0,arr('psi_shift')*(1-np.clip(rd['base_broadening_delta'],0,1)))
 absbase=chi*dom*(1-psi);relative=absbase/(val('chi_Kbase')*val('chi_dom')*(1-val('psi_shift')))
 factors={}
 for ch,k in [('l','tau_L_eff'),('k','tau_K_eff'),('c','tau_C_eff')]:
  t=original['tau_'+ch];ero=rd['epsilon_ero_'+ch];t0=val(k)
  factors[ch]=(t/t0*(np.maximum(0,1-ero*t) if reg!='r0' else 1),cf.response_index(t0,rd['tau_'+ch+'_delta'],ero))
 ai=cs['lambda_ai']*g*original['tau_ai']*(np.maximum(0,1-rd['epsilon_ero_ai']*original['tau_ai']) if reg!='r0' else 1)
 oldcons=(arr('mpc_W')*(1-arr('tau_L_disp'))*dw+arr('mpc_Pi')*(1-arr('tau_K_disp'))*absbase*dn+arr('mpc_R')*arr('theta_R_dom')*(1-arr('tau_R_disp'))*np.maximum(0,dn-chi*dn))
 exempt=np.maximum(0,arr('exempt_C')*(1-np.clip(rd['base_broadening_delta'],0,1)))
 def revenue(mask):
  dest,corp,rent,pit,norm,cons=[bool(mask&(1<<j)) for j in range(6)]
  alpha=.15 if pit else 0.;ul,uk,uc=[factors[ch][int(norm)] for ch in ['l','k','c']]
  tl=(p['ssc']+(1-alpha)*p['pit'])/p['ls']*dw*ul
  tc=p['cit']/(1-p['ls'])*dn*(relative if corp else absbase)*uk
  tk=alpha*p['pit']/(1-p['ls'])*dn*uk
  if not rent:tc=tc-cs['lambda_ai_kbase']*g*val('tau_K_eff')*uk
  consumption=val('mpc_W')*(dw-tl)+.5*val('mpc_W')*(dn-tc-tk-ai) if cons else (1-exempt)*np.maximum(0,oldcons)
  if not dest:consumption=consumption*(1-arr('m_M'))
  tv=val('tau_C_eff')*uc*consumption
  return tl+tc+tk+ai+tv
 # Endpoints must recover the two actual models, with all primitives matched.
 assert np.allclose(revenue(0),g*original['mfc_gross'],atol=2e-15,rtol=1e-12),(c,sc,reg,'old')
 assert np.allclose(revenue(63),z['revenue'],atol=2e-15,rtol=1e-12),(c,sc,reg,'new')
 assert np.allclose(revenue(1),g*iv['mfc_gross'],atol=2e-15,rtol=1e-12),(c,sc,reg,'IVA')
 return revenue,original,z

central=cf.Central();front=central.array('E_prod_frontier');rows=[];channels=[]
for c in cf.ta.COUNTRIES:
 for sc in cf.ta.SCENARIOS:
  cs=cf.mc.build_country_scenario_draws(central,cf.x,c,sc,front)
  for reg in cf.ta.REGIMES:
   rd=cf.mc.build_regime_draws(central,reg);pols=cf.policies(c);fun,base,z=setup(central,c,sc,reg,cs,rd,pols[0]);g=float(cs['g_ai_level'][0]);rev=[float(fun(mask)[0]) for mask in range(64)]
   channels.extend({'country_id':c,'scenario_id':sc,'regime_id':reg,'mask':mask,'g':g,'revenue':rv,'M':rv/g} for mask,rv in enumerate(rev))
   for pol in pols:
    f=float(cf.mc.fixed_cost_arrays(cf.x['policy_admin_transition_cost'],c,pol['policy_id'],rd['leakage_multiplier'])['f_fix'][0]);ann=cf.annuity(c,pol['policy_id']);cost=pol['cost_gross_gdp'];spb=cf.value('sPB_plus_gdp_ratio',country=c)
    for mask in range(128):
     F=f-ann if mask&64 else f;gap=rev[mask&63]-F-1.1*cost-spb
     rows.append({'country_id':c,'scenario_id':sc,'regime_id':reg,'policy_variant_id':pol['policy_variant_id'],'mask':mask,'R':rev[mask&63],'F':F,'benefits':cost,'spb':spb,'B2_balance':gap,'B2':gap>=0})
df=pd.DataFrame(rows);df.to_csv(O/'PUENTE_DETERMINISTA_61440.csv',index=False);pd.DataFrame(channels).to_csv(O/'CANALES_PUENTE_5120.csv',index=False)
summary=df.assign(domain=np.where(df.scenario_id.eq('stress'),'stress','nonstress')).groupby(['mask','domain']).agg(cells=('B2','size'),B2_crossings=('B2','sum')).reset_index();summary.to_csv(O/'RESUMEN_PUENTE_DETERMINISTA.csv',index=False)
last=pd.read_csv(D/'costos_transicion_03/resultados/FRONTERAS_ANUALES_480.csv');keys=['country_id','scenario_id','regime_id','policy_variant_id'];merged=df[df['mask'].eq(127)].merge(last,on=keys,validate='one_to_one')
assert np.allclose(merged.B2_balance,merged.Fmax_B2_reference-merged.F_recurring_author,atol=2e-14)
assert np.array_equal(merged.B2,merged.covers_recurring_B2_reference)
# Rebuild the retained primitive draws in the original order and verify equality.
sampler=cf.mc.ValueSampler(cf.x['values'],50000,20261114,record_parameters=False);front=sampler.array('E_prod_frontier');cs=cf.mc.build_country_scenario_draws(sampler,cf.x,'CHL','mid',front);rd=cf.mc.build_regime_draws(sampler,'r0');pol=next(p for p in cf.policies('CHL') if p['policy_variant_id']=='GMI:GMI_ideal_aggregate')
fun,base,z=setup(sampler,'CHL','mid','r0',cs,rd,pol);saved=pd.read_parquet(D/'evidencia/insumos/sorteos.parquet');current=pd.read_parquet(N/'resultados/SORTEOS_CHILE_50000.parquet')
assert np.array_equal(cs['g_ai_level'],saved.g_ai_level) and np.array_equal(base['mfc_gross'],saved.mfc__structural)
assert np.array_equal(cs['g_ai_level'],current.g)
assert np.allclose(z['M'],current.M_reference,atol=2e-15,rtol=1e-13)
f=base['fixed']['f_fix'];ann=cf.annuity('CHL','GMI');cost=pol['cost_gross_gdp'];results=[];drawmasks={}
for mask in range(128):
 revenue=fun(mask&63);F=f-ann if mask&64 else f;balance=revenue-F-1.1*cost;hit=balance>=0;n=len(hit);k=int(hit.sum())
 results.append({'mask':mask,'n':n,'crossings':k,'B2_frequency_percent':100*k/n,'R_mean_percent_GDP':100*float(revenue.mean()),'R_p50_percent_GDP':100*float(np.median(revenue)),'balance_mean_pp_GDP':100*float(balance.mean()),'F_mean_percent_GDP':100*float(F.mean()),'M_mean':float(np.mean(revenue/cs['g_ai_level']))})
 if mask in [0,1,3,7,15,31,63,127]:drawmasks[mask]=revenue
mc=pd.DataFrame(results);mc.to_csv(O/'PUENTE_CHILE_50000_128.csv',index=False)
# Compare the bridge endpoints with the independently computed model arrays.
# Numeric r8 frequencies remain in the external reference, not in generation.
iva=cf.mc.compute_cell_arrays(sampler,cf.x,'CHL','mid','r0',pol,cs,rd)
endpoint_receipts={0:saved.g_ai_level.to_numpy()*saved.mfc__structural.to_numpy(),1:cs['g_ai_level']*iva['mfc_gross'],63:current.g.to_numpy()*current.M_reference.to_numpy(),127:current.g.to_numpy()*current.M_reference.to_numpy()}
matched_crossings=[]
for mask,receipts in endpoint_receipts.items():
 expected_count=int((receipts-(f-ann if mask&64 else f)>=1.1*cost).sum())
 assert int(mc.loc[mc['mask'].eq(mask),'crossings'].iloc[0])==expected_count,(mask,expected_count)
 matched_crossings.append(expected_count)
seq=mc[mc['mask'].isin([0,1,3,7,15,31,63,127])].copy();seq['step']=['anterior']+names;seq['change_frequency_pp']=seq.B2_frequency_percent.diff();seq.to_csv(O/'SECUENCIA_CHILE.csv',index=False)
# Exact permutation-average allocation of all interactions over the chosen groups.
def shapley(vals,metric,case):
 vals=dict(vals);out=[]
 for j,name in enumerate(names):
  contrib=0.;margins=[]
  for mask in range(128):
   if mask&(1<<j):continue
   k=mask.bit_count();weight=math.factorial(k)*math.factorial(6-k)/math.factorial(7)
   marginal=vals[mask|(1<<j)]-vals[mask];contrib+=weight*marginal;margins.append(marginal)
  out.append({'case':case,'metric':metric,'change':name,'allocation':contrib,'min_order_marginal':min(margins),'max_order_marginal':max(margins),'initial':vals[0],'final':vals[127]})
 assert abs(sum(r['allocation'] for r in out)-(vals[127]-vals[0]))<1e-10
 return out
sh=[]
for metric in ['B2_frequency_percent','R_mean_percent_GDP','balance_mean_pp_GDP']:sh+=shapley(zip(mc['mask'],mc[metric]),metric,'CHL_mid_r0_50000')
for domain in ['nonstress','stress']:
 z=summary[summary.domain.eq(domain)];sh+=shapley(zip(z['mask'],z.B2_crossings),'B2_crossings',domain+'_central_grid')
centralch=pd.DataFrame(channels).query("country_id=='CHL' and scenario_id=='mid' and regime_id=='r0'").set_index('mask')
sh+=shapley([(mask,centralch.loc[mask&63,'M']) for mask in range(128)],'M_average','CHL_mid_r0_central')
pd.DataFrame(sh).to_csv(O/'ATRIBUCION_SOBRE_TODOS_LOS_ORDENES.csv',index=False)
# Preserve matched primitive arrays needed by an independent, no-import verifier.
primitive={'g':cs['g_ai_level'],'dw':base['omega_l']*cs['g_ai_level'],'dn':cs['g_ai_level']-base['omega_l']*cs['g_ai_level'],'F_equivalent':f,'original_M':base['mfc_gross'],'current_M':current.M_reference.to_numpy()}
for name in ['chi_Kbase','chi_dom','psi_shift','tau_L_disp','tau_K_disp','tau_R_disp','mpc_W','mpc_Pi','mpc_R','m_M','theta_R_dom','exempt_C']:primitive[name]=sampler.array(name,country='CHL')
for name in ['lambda_ai','lambda_ai_kbase']:primitive[name]=cs[name]
pd.DataFrame(primitive).to_parquet(O/'PRIMITIVAS_EMPAREJADAS_CHILE.parquet',index=False)
fr=cf.fiscal.loc['CHL'];constants={'ls':cf.value('LS_labor_share',country='CHL'),'pit':fr.pit_gdp/100,'cit':fr.cit_gdp/100,'ssc':fr.social_contrib_gdp/100,'vat':cf.value('tau_C_eff',country='CHL'),'kw_reference':cf.value('mpc_W',country='CHL'),'base_central':cf.value('chi_Kbase',country='CHL')*cf.value('chi_dom',country='CHL')*(1-cf.value('psi_shift',country='CHL')),'benefits':cost,'annuity':ann,'regime':'r0','alpha_reference':.15}
(O/'CONSTANTES_CHILE.json').write_text(json.dumps(constants,indent=2)+'\n',encoding='utf-8')
manifest={'status':'BUILT_AND_ENDPOINTS_MATCHED','central_cells':480,'coalitions':128,'deterministic_rows':len(df),'draws':50000,'new_primitive_draws':False,'reconstructed_original_draws_exact':True,'current_endpoint_rows_match':len(merged),'matched_crossings':matched_crossings,'attribution_groups':names,'distribution_equation_changed':False,'operating_cost_calibration_changed':False,'method':'Exact Shapley allocation over all subsets of seven stated switches; arithmetic, not causal','design_sha256':sha(S/'DISENO_Y_ADENDA_07G.md')}
(O/'EJECUCION.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(seq.to_string(index=False));print(pd.DataFrame(sh).query("case=='CHL_mid_r0_50000' and metric=='B2_frequency_percent'")[['change','allocation','min_order_marginal','max_order_marginal']].to_string(index=False));print(json.dumps(manifest))
