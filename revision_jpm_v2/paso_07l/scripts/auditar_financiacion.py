from pathlib import Path
import sys,json,hashlib,importlib.util,zipfile,xml.etree.ElementTree as ET
from collections import defaultdict
sys.dont_write_bytecode=True
import numpy as np,pandas as pd
S=Path(__file__).resolve().parents[1];R=S.parent;O=S/'resultados';G=R/'paso_07g/bloque_3_transicion'
hashes={};checks=defaultdict(int);errors=defaultdict(float)
def source(p):hashes[p.relative_to(R).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest();return p
def eq(name,a,b,tol=3e-11):
 a=np.asarray(a);b=np.asarray(b);err=float(np.max(np.abs(a-b)));errors[name]=max(errors[name],err);checks[name]+=a.size
 assert np.isfinite(err) and err<tol,(name,err,tol)
def yes(name,x):a=np.asarray(x);checks[name]+=a.size;assert np.all(a),name
m=pd.read_csv(source(G/'TRAYECTORIAS_CONFIGURACION.csv'));saved=np.load(source(G/'TRAYECTORIAS_COMPLETAS.npz'));h=pd.read_csv(source(G/'SENSIBILIDAD_H10_H25.csv'));inputs=json.loads(source(G/'INSUMOS_CASOS.json').read_text());N=len(m);years=np.arange(1,26)
newR=np.zeros((N,25));benefits=np.zeros((N,25))
for inp in inputs:
 ids=np.flatnonzero(m.case_id.to_numpy()==inp['case_id']);d=m.iloc[ids];c=inp['context'];p=c['prepared'];a=d.alpha.to_numpy()[:,None];w=d.k_w.to_numpy()[:,None];n=d.k_n.to_numpy()[:,None];s=p['ls']
 tr=min(1,((c['epsilon']+(1-c['epsilon'])*c['q'])**c['gamma']*(c['epsilon']+(1-c['epsilon'])*c['exposure'])**c['beta'])/c['s_frontier'])
 g=(1+c['phi']*tr)**years-1;sp=1/(1+(1-s)/s*np.exp(-c['pressure_per_q']*c['q']));dw=(sp-s)+sp*g;dn=(s-sp)+(1-sp)*g
 tl=(p['ssc']+(1-a)*p['pit'])/s*p['ul']*dw;tn=(p['cit']*p['relative_base']+a*p['pit'])/(1-s)*p['uk']*dn;ta=c['lambda_ai']*c['tau_ai']*max(0,1-c['erosion_ai']*c['tau_ai'])*g
 newR[ids]=tl+tn+ta+p['vat_yield']*p['uc']*(w*(dw-tl)+n*(dn-tn-ta));benefits[ids]=inp['benefits']
 eq('costo_operativo',d.F,inp['F_reference']*d.F_factor);eq('instalacion',d.I,inp['I_reference']*d.I_factor)
eq('ingresos_reconstruidos',newR,saved['revenue']);eq('beneficios',benefits,saved['benefits'])
i=m.interest.to_numpy();n=m.growth.to_numpy();F=m.F.to_numpy();I=m.I.to_numpy();period=m.replacement_period.to_numpy();a=(1+i)/(1+n)
yes('dominio_interes_crecimiento',(i>-1)&(n>-1));spb=np.maximum(0,(i-n)/(1+n)*m.target_debt-m.primary_balance);eq('reserva_primaria',spb,m.spb)
cost=np.where(m.budget.eq('cash').to_numpy()[:,None],benefits,1.1*benefits+np.asarray(spb)[:,None]);eq('compromiso_caja_B2',cost,saved['cost'])
rep=np.zeros((N,25))
for t in years:rep[:,t-1]=np.where((period>0)&(t%np.maximum(period,1)==0),I,0.)
eq('reposicion_incluido_endpoint',rep,saved['replacement'])
# Build nominal balances at Y0=1. Keep the F-free and unit-F accounts separate.
D=I.copy();D_noF=I.copy();D_unit=np.zeros(N);GDP=np.ones(N);capital=np.maximum(I,0);acc=np.ones(N)
B=np.zeros((N,25));C=np.zeros((N,25));U=np.zeros((N,25))
for t in range(25):
 GDP*=1+n;acc*=1+i
 D=(1+i)*D+(cost[:,t]+F+rep[:,t]-newR[:,t])*GDP
 D_noF=(1+i)*D_noF+(cost[:,t]+rep[:,t]-newR[:,t])*GDP;D_unit=(1+i)*D_unit+GDP
 capital=np.maximum(capital,D/acc);B[:,t]=D/GDP;C[:,t]=capital;U[:,t]=-D_noF/D_unit
eq('saldo_nominal_sobre_PIB',B,saved['balance']);eq('frontera_temporal',U,saved['frontier']);eq('capital_minimo',C,saved['capital'])
annual=newR-cost-F[:,None]>=0;returned=B<=0;persistent=np.logical_and.accumulate(returned[:,::-1],axis=1)[:,::-1]
def first(mask):return np.where(mask.any(axis=1),np.argmax(mask,axis=1)+1,np.nan)
for H in [10,25]:
 sub=h[h.H.eq(H)].sort_values('path_id');yes('orden_trayectorias',sub.path_id.to_numpy()==np.arange(N))
 eq('resumen_saldo',sub.balance_H,B[:,H-1]);eq('resumen_capital',sub.initial_capital_gdp0_H,C[:,H-1]);eq('resumen_frontera',sub.Fmax_H,U[:,H-1]);eq('resumen_pico',sub.peak_balance_ratio_H,np.maximum(I,np.max(B[:,:H],axis=1)))
 for col,expected in [('first_return_by_H',first(returned[:,:H])),('first_annual_coverage_by_H',first(annual[:,:H])),('persistent_return_to_25',first(persistent))]:yes('anos_y_censura',np.isclose(sub[col],expected,equal_nan=True))
 yes('ausencia_recuperacion',sub.no_return_by_H.to_numpy()==~returned[:,:H].any(axis=1))
 # Every time constraint is satisfied by K and at least one is binding, including t=0.
 funded=B[:,:H]-C[:,H-1,None]*a[:,None]**years[:H]
 yes('suficiencia_capital',funded.max(axis=1)<=3e-11)
 eq('minimalidad_capital',np.maximum(funded.max(axis=1),I-C[:,H-1]),np.zeros(N))
 # The sign of the terminal balance agrees with the terminal recurring ceiling.
 yes('desigualdad_frontera_temporal',(B[:,H-1]<=1e-11)==(F<=U[:,H-1]+1e-11))
print('Financiacion: 49.896 trayectorias y 99.792 horizontes reconstruidos.',flush=True)

# Compare rendered scientific tables by their actual DOCX cell text.
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
def tables(name):
 with zipfile.ZipFile(source(S/'evidencia'/name)) as z:root=ET.fromstring(z.read('word/document.xml'))
 return [[[''.join(c.itertext()) if False else ''.join(x.text or '' for x in c.findall('.//w:t',ns)) for c in row.findall('w:tc',ns)] for row in tb.findall('w:tr',ns)] for tb in root.findall('w:body/w:tbl',ns)]
main=tables('MANUSCRITO_JPM_V2.docx');supp=tables('SUPLEMENTO_TECNICO_JPM_V2.docx');cellrecords=[]
def cell(table,row,col,expected,actual,label):
 yes('celdas_documentos',actual==expected);cellrecords.append(dict(table=table,row=row,column=col,expected=expected,actual=actual,label=label))
def selection(case,adverse=False,period=0):
 select=m.case_id.eq(case)&m['mode'].eq('reference')&m.budget.eq('B2_reserved')&m.replacement_period.eq(period)
 select&=m.macro_id.eq('diagnostic_i_plus2_n_minus2' if adverse else 'historical_2024')&m.F_factor.eq(1.25 if adverse else 1)&m.I_factor.eq(1.5 if adverse else 1)
 ids=np.flatnonzero(select);assert len(ids)==1;return ids[0]
for case in range(7):
 base=selection(case);adverse=selection(case,True,3)
 fy=lambda idx:str(int(first(returned[idx:idx+1])[0])) if returned[idx].any() else '>25'
 cell('S6',case+1,1,fy(base)+' / '+fy(adverse),supp[5][case+1][1],'recuperacion')
 cell('S6',case+1,2,f'{100*C[base,24]:.4f} / {100*C[adverse,24]:.4f}',supp[5][case+1][2],'capital')
 ids=np.flatnonzero(m.case_id.eq(case)&m.budget.eq('B2_reserved'));no=int((~returned[ids].any(axis=1)).sum())
 cell('S7',case+1,1,f'{100*C[ids,24].min():.2f}–{100*C[ids,24].max():.2f}',supp[6][case+1][1],'rango_capital')
 cell('S7',case+1,2,f'{no} / {len(ids)}',supp[6][case+1][2],'no_recuperacion')
for col,case in [(1,1),(2,4)]:
 idx=selection(case);inp=inputs[case];c=inp['context'];p=c['prepared'];s=p['ls'];aa,w,nn=c['reference'];v=p['vat_yield']*p['uc'];tl=(p['ssc']+(1-aa)*p['pit'])/s*p['ul'];tn=(p['cit']*p['relative_base']+aa*p['pit'])/(1-s)*p['uk'];sp=1/(1+(1-s)/s*np.exp(-c['pressure_per_q']*c['q']));L=tl+v*w*(1-tl);NN=tn+v*nn*(1-tn);J=(1-v*nn)*c['lambda_ai']*c['tau_ai']*max(0,1-c['erosion_ai']*c['tau_ai']);A=L*sp+NN*(1-sp)+J;intercept=(L-NN)*(sp-s)
 rev=newR[idx,9];ben=benefits[idx,9];req=1.1*ben+F[idx]+spb.iloc[idx];gain=(rev-intercept)/A;greq=max(0,(req-intercept)/A)
 cell('4',1,col,f'{100*(rev-ben-F[idx]):+.4f}',main[3][1][col],'B0')
 cell('4',2,col,f'{100*(rev-req):+.4f}',main[3][2][col],'B2')
 cell('4',3,col,str(int(first(annual[idx:idx+1])[0])),main[3][3][col],'primera_cobertura')
 cell('4',4,col,str(int(first(returned[idx:idx+1])[0])),main[3][4][col],'primera_recuperacion')
 cell('4',5,col,f'{100*gain:.4f} / {100*greq:.4f}',main[3][5][col],'ganancia_y_umbral')
 yes('cobertura_persistente_tabla4',np.all(annual[idx,int(first(annual[idx:idx+1])[0])-1:]))
ch=selection(1);adv=selection(1,True);adv3=selection(1,True,3)
headline={'year_B2':int(first(annual[ch:ch+1])[0]),'year_recovery':int(first(returned[ch:ch+1])[0]),'balance10_pct':float(100*B[ch,9]),'Fmax_path10_pct':float(100*U[ch,9]),'capital10_pct':float(100*C[ch,9]),'adverse_annual_year':int(first(annual[adv:adv+1])[0]),'adverse_balance25_pct':float(100*B[adv,24]),'adverse_capital25_pct':float(100*C[adv,24]),'adverse_replacement_balance25_pct':float(100*B[adv3,24]),'adverse_replacement_capital25_pct':float(100*C[adv3,24])}
expected={'year_B2':9,'year_recovery':15,'balance10_pct':1.0300,'Fmax_path10_pct':.1437,'capital10_pct':2.3883,'adverse_annual_year':20,'adverse_balance25_pct':4.1357,'adverse_capital25_pct':12.9509,'adverse_replacement_balance25_pct':5.7445,'adverse_replacement_capital25_pct':16.1092}
for k,v in expected.items():eq('cifras_texto_'+k,headline[k],v,5.00001e-5)
for case,year in [(1,16),(0,20)]:idx=selection(case,period=3);eq('recuperacion_reposicion',first(returned[idx:idx+1])[0],year)

# Boundary tests independently exercise the production financing function.
spec=importlib.util.spec_from_file_location('fin_candidate',source(R/'paso_07g/candidato/frontera_transicion.py'));f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
synthetic=[]
for i0,n0,I0 in [(0.,0.,.2),(.03,.03,.2),(-.02,.01,.2),(.12,-.05,0.)]:
 rev=np.array([.1,.2,.8,.01,.7]);cost0=np.array([.2,.1,.05,.3,.05]);repl=np.array([0,0,0,0,.15]);f0=.04
 z=f.financing(rev,cost0,f0,I0,i0,n0,repl);dd=I0;gdp=1.;acc0=1.;K=max(0,I0)
 for t in range(5):
  gdp*=1+n0;acc0*=1+i0;dd=dd*(1+i0)+(cost0[t]+f0+repl[t]-rev[t])*gdp;K=max(K,dd/acc0)
  eq('borde_saldo',z['balance'][t],dd/gdp);eq('borde_capital',z['initial_capital'][t],K)
  terminal=f.financing(rev[:t+1],cost0[:t+1],z['fmax'][t],I0,i0,n0,repl[:t+1])['balance'][-1];eq('borde_frontera',terminal,0.)
 synthetic.append(dict(interest=i0,growth=n0,setup=I0,terminal_balance=float(z['balance'][-1])))
zero=f.financing(np.zeros(3),np.zeros(3),0.,0.,0.,0.);eq('borde_cero_financiero',zero['initial_capital'],np.zeros(3))
for i0 in [0.,.03]:
 sched=f.annuity_schedule(.002,i0,.04);eq('anualidad_amortizacion',sum(r['principal_nominal_gdp0'] for r in sched),.002);eq('anualidad_saldo_final',sched[-1]['closing_nominal_gdp0'],0.)

pd.DataFrame(cellrecords).to_csv(O/'CELDAS_FINANCIACION_VERIFICADAS.csv',index=False)
(O/'TITULARES_FINANCIACION.json').write_text(json.dumps(headline,indent=2)+'\n',encoding='utf-8')
result={'status':'PASS','paths':N,'path_years':N*25,'horizon_rows':len(h),'checks_by_group':dict(checks),'max_absolute_errors':dict(errors),'scientific_cells_verified':len(cellrecords),'synthetic_boundaries':synthetic,'source_hashes':hashes,'scope':'Reconstruccion desde entradas retenidas, sin importar funciones candidatas en el calculo de trayectorias. No nueva ingesta ni reproduccion en entorno limpio.'}
(O/'VERIFICACION_FINANCIACION.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','paths':N,'document_cells':len(cellrecords),'balance_max_error':errors['saldo_nominal_sobre_PIB']}))
