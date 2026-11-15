from pathlib import Path
import json
import numpy as np,pandas as pd
S=Path(__file__).resolve().parents[1];O=S/'bloque_3_transicion'
m=pd.read_csv(O/'TRAYECTORIAS_CONFIGURACION.csv');z=np.load(O/'TRAYECTORIAS_COMPLETAS.npz');h=pd.read_csv(O/'SENSIBILIDAD_H10_H25.csv');inputs=json.loads((O/'INSUMOS_CASOS.json').read_text());N=len(m);years=np.arange(1,26);errors={}
def check(name,actual,expected,tol=3e-11):
 err=float(np.max(np.abs(np.asarray(actual)-np.asarray(expected))));errors[name]=max(err,errors.get(name,0));assert err<tol,(name,err)
# Direct revenue identity reconstructed without importing candidate modules.
for inp in inputs:
 ids=np.flatnonzero(m.case_id.to_numpy()==inp['case_id']);mm=m.iloc[ids];c=inp['context'];p=c['prepared'];a=mm.alpha.to_numpy()[:,None];kw=mm.k_w.to_numpy()[:,None];kn=mm.k_n.to_numpy()[:,None]
 tr=min(1,((c['epsilon']+(1-c['epsilon'])*c['exposure'])**c['beta']*(c['epsilon']+(1-c['epsilon'])*c['q'])**c['gamma'])/c['s_frontier'])
 gain=(1+c['phi']*tr)**years-1;sp=1/(1+np.exp(-(np.log(p['ls']/(1-p['ls']))+c['pressure_per_q']*c['q'])));dw=sp*(1+gain)-p['ls'];dn=gain-dw
 labor=(p['ssc']+(1-a)*p['pit'])/p['ls']*p['ul']*dw;nonlabor=(p['cit']*p['relative_base']+a*p['pit'])/(1-p['ls'])*p['uk']*dn;ai=c['lambda_ai']*c['tau_ai']*max(0,1-c['erosion_ai']*c['tau_ai'])*gain
 vat=p['vat_yield']*p['uc']*(kw*(dw-labor)+kn*(dn-nonlabor-ai));rev=labor+nonlabor+ai+vat
 check('independent_revenue',rev,z['revenue'][ids]);check('benefits',np.broadcast_to(inp['benefits'],(len(ids),25)),z['benefits'][ids])
 expectedcost=np.where(mm.budget.eq('cash').to_numpy()[:,None],z['benefits'][ids],1.1*z['benefits'][ids]+mm.spb.to_numpy()[:,None]);check('budget',expectedcost,z['cost'][ids])
 check('F',mm.F,inp['F_reference']*mm.F_factor);check('I',mm.I,inp['I_reference']*mm.I_factor)
i=m.interest.to_numpy();n=m.growth.to_numpy();F=m.F.to_numpy();I=m.I.to_numpy();period=m.replacement_period.to_numpy()
s=np.maximum(0,(i-n)/(1+n)*m.target_debt-m.primary_balance);check('spb',s,m.spb)
rep=np.zeros((N,25))
for t in range(1,26):rep[:,t-1]=np.where((period>0)&(t%np.where(period>0,period,1)==0),I,0)
check('replacements',rep,z['replacement'])
ledger=I.copy();noF=I.copy();unit=np.zeros(N);gdp=np.ones(N);accrual=np.ones(N);capital=np.maximum(0,I.copy());balances=[];frontiers=[];caps=[]
for t in range(25):
 gdp*=1+n;accrual*=1+i;ledger=(1+i)*ledger+(z['cost'][:,t]+F+rep[:,t]-z['revenue'][:,t])*gdp
 noF=(1+i)*noF+(z['cost'][:,t]+rep[:,t]-z['revenue'][:,t])*gdp;unit=(1+i)*unit+gdp
 balance=ledger/gdp;frontier=-noF/unit;capital=np.maximum(capital,ledger/accrual)
 check('nominal_ledger',balance,z['balance'][:,t]);check('zero_terminal_frontier',frontier,z['frontier'][:,t]);check('minimal_initial_capital',capital,z['capital'][:,t]);check('F_derivative_identity',noF+F*unit,ledger,2e-8)
 balances.append(balance);frontiers.append(frontier);caps.append(capital.copy())
B=np.array(balances).T;C=np.array(caps).T
# Starting with the reported minimum capital prevents a positive financing balance
# through the stated horizon; one binding constraint proves minimality.
for H in [10,25]:
 funded=B[:,:H]-C[:,H-1,None]*((1+i[:,None])/(1+n[:,None]))**years[:H]
 assert funded.max()<3e-11
 residual=np.maximum(np.max(funded,axis=1),I-C[:,H-1]);assert np.max(np.abs(residual))<3e-11
 sub=h[h.H.eq(H)].sort_values('path_id');assert np.array_equal(sub.path_id,np.arange(N))
 check('summary_balance',sub.balance_H,B[:,H-1]);check('summary_capital',sub.initial_capital_gdp0_H,C[:,H-1]);check('summary_peak',sub.peak_balance_ratio_H,np.maximum(I,np.max(B[:,:H],axis=1)))
 annual=z['revenue']-z['cost']-F[:,None]>=0;returned=B<=0;persistent=np.logical_and.accumulate(returned[:,::-1],axis=1)[:,::-1]
 def first(mask):return np.where(mask.any(axis=1),np.argmax(mask,axis=1)+1,np.nan)
 for col,expected in [('first_return_by_H',first(returned[:,:H])),('first_annual_coverage_by_H',first(annual[:,:H])),('persistent_return_to_25',first(persistent))]:assert np.allclose(sub[col],expected,equal_nan=True)
 assert np.array_equal(sub.annual_coverage_H,annual[:,H-1]);assert np.array_equal(sub.no_return_by_H,~returned[:,:H].any(axis=1))
v={'status':'PASS','paths':N,'nominal_path_years':N*25,'horizon_rows':len(h),'independent_channel_reconstruction':True,'independent_nominal_ledger':True,'frontier_and_minimal_capital_proofs':True,'summary_and_censoring_checks':True,'max_absolute_errors':errors}
(O/'VERIFICACION_INDEPENDIENTE.json').write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8');print(json.dumps(v))
q=pd.read_csv(O/'COMBINACIONES_ILUSTRATIVAS.csv');q=q[(q.case_id==1)&(q.budget=='B2_reserved')];print(q[['macro_id','F_factor','I_factor','replacement_period','H','first_annual_coverage_by_H','balance_H','initial_capital_gdp0_H','first_return_by_H','persistent_return_to_25']].to_string(index=False))
