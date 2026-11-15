from pathlib import Path
import sys,json,hashlib,itertools,zipfile,xml.etree.ElementTree as ET
from collections import defaultdict
sys.dont_write_bytecode=True
import numpy as np,pandas as pd
from scipy.stats import beta
S=Path(__file__).resolve().parents[1];R=S.parent;O=S/'resultados';G=R/'paso_07g/bloque_2_descomposicion'
checks=defaultdict(int);errors=defaultdict(float);hashes={};cells=[]
def source(p):hashes[p.relative_to(R).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest();return p
def eq(name,a,b,tol=2e-11):
 a=np.asarray(a);b=np.asarray(b);err=float(np.max(np.abs(a-b)));checks[name]+=a.size;errors[name]=max(errors[name],err);assert np.isfinite(err) and err<tol,(name,err,tol)
def yes(name,x):a=np.asarray(x);checks[name]+=a.size;assert np.all(a),name
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
def tables(name):
 with zipfile.ZipFile(source(S/'evidencia'/name)) as z:root=ET.fromstring(z.read('word/document.xml'))
 return [[[''.join(x.text or '' for x in c.findall('.//w:t',ns)) for c in row.findall('w:tc',ns)] for row in tb.findall('w:tr',ns)] for tb in root.findall('w:body/w:tbl',ns)]
main=tables('MANUSCRITO_JPM_V2.docx');supp=tables('SUPLEMENTO_TECNICO_JPM_V2.docx')
def cell(table,row,col,actual,expected):
 yes('celdas_documentales',actual==expected);cells.append(dict(table=table,row=row,column=col,actual=actual,expected=expected))
annual=pd.read_csv(source(R/'paso_07d/costos_transicion_03/resultados/FRONTERAS_ANUALES_480.csv'));nuc=pd.read_csv(source(O/'NUCLEO_720_RECONSTRUIDO.csv'));ctxs=json.loads(source(R/'paso_07g/evidencia/CONTEXTOS_80.json').read_text());ctxs={(x['country_id'],x['scenario_id'],x['regime_id']):x['context'] for x in ctxs}
values=pd.read_parquet(source(R/'paso_07d/evidencia/insumos/values.parquet'))
def value(name,c,field='baseline_value'):
 x=values[values.name.eq(name)&values.country_id.eq(c)];assert len(x)==1;return float(x.iloc[0][field])
for col,country in enumerate(['CHL','COL','MEX','PER'],1):
 c=ctxs[country,'mid','r0'];p=c['prepared'];r=nuc.query('country_id==@country and scenario_id=="mid" and regime_id=="r0" and mode=="reference"').iloc[0]
 tr=np.expm1(np.log1p(r.g)/10)/c['phi']
 for row,expected in [(1,f'{p["ls"]:.3f}'),(2,f'{tr:.3f}'),(3,f'{r.M:.3f}'),(4,f'{100*value("sPB_plus_gdp_ratio",country):.3f}')]:cell('1',row,col,main[0][row][col],expected)
 variants=['PEN','MUT','GMI:GMI_ideal_aggregate','GMI:GMI_loaded_aggregate','PBI','UBI']
 for row,variant in enumerate(variants,1):
  z=annual.query('country_id==@country and scenario_id=="mid" and regime_id=="r0" and policy_variant_id==@variant');assert len(z)==1
  cell('2',row,col,main[1][row][col],f'{100*z.iloc[0].benefits:.2f}')
 ideal=annual.query('country_id==@country and scenario_id=="mid" and regime_id=="r0" and policy_variant_id=="GMI:GMI_ideal_aggregate"').iloc[0].benefits
 loaded=annual.query('country_id==@country and scenario_id=="mid" and regime_id=="r0" and policy_variant_id=="GMI:GMI_loaded_aggregate"').iloc[0].benefits
 eq('GMI_loaded',loaded,1.5*ideal)
cases=pd.read_csv(source(R/'paso_07e/resultados/CASOS_PUBLICABLES.csv'))
for i,r in enumerate(cases.itertuples(index=False),1):
 z=nuc.query('country_id==@r.country_id and scenario_id==@r.scenario_id and regime_id==@r.regime_id and mode=="reference"').iloc[0]
 for col,expected in [(1,f'{100*z.revenue:.3f}'),(2,f'{100*r.F_recurring_author:.3f}'),(3,f'{100*r.Fmax_B2_reference:.3f}'),(4,f'[{100*r.Fmax_B2_uniform:.3f}, {100*r.Fmax_B2_possible:.3f}]')]:cell('3',i,col,main[2][i][col],expected)
for sc,select,expected in [('nonstress',annual.scenario_id.ne('stress'),[5,4,0,18]),('stress',annual.scenario_id.eq('stress'),[24,10,10,12])]:
 a=annual[select];actual=[int(a.covers_recurring_B0_reference.sum()),int(a.covers_recurring_B2_reference.sum()),int(a.covers_recurring_B2_uniform.sum()),int(a.covers_recurring_B2_possible.sum())];eq('recuentos_'+sc,actual,expected)
eq('B1_estres',int(annual[annual.scenario_id.eq('stress')].covers_recurring_B1_reference.sum()),23)

# Reconstruct the matched comparison from stored primitive draws, not previous
# reported frequencies. No sampling is done in this audit.
p=pd.read_parquet(source(G/'PRIMITIVAS_EMPAREJADAS_CHILE.parquet'));c=json.loads(source(G/'CONSTANTES_CHILE.json').read_text());s=c['ls'];g=p.g.to_numpy();dw=p.dw.to_numpy();dn=g-dw
absbase=p.chi_Kbase*p.chi_dom*(1-p.psi_shift);rel=absbase/c['base_central'];ai=np.zeros(len(p)) # r0 has zero additional rent rate
oldcons=p.mpc_W*(1-p.tau_L_disp)*dw+p.mpc_Pi*(1-p.tau_K_disp)*absbase*dn+p.mpc_R*p.theta_R_dom*(1-p.tau_R_disp)*np.maximum(0,dn-p.chi_Kbase*dn)
records=[];revnew=None
for mask in range(128):
 dest,corp,rent,allocate,normalise,cons,sep=[bool(mask&(1<<k)) for k in range(7)]
 alpha=c['alpha_reference'] if allocate else 0.;labor=(c['ssc']+(1-alpha)*c['pit'])/s*dw;corporate=c['cit']/(1-s)*dn*(rel if corp else absbase)
 if not rent:corporate-=p.lambda_ai_kbase*g*c['cit']/(1-s)
 capital=alpha*c['pit']/(1-s)*dn
 consume=c['kw_reference']*(dw-labor)+.5*c['kw_reference']*(dn-corporate-capital-ai) if cons else (1-p.exempt_C)*np.maximum(0,oldcons)
 if not dest:consume=consume*(1-p.m_M)
 rev=np.asarray(labor+corporate+capital+ai+c['vat']*consume)
 F=np.asarray(p.F_equivalent)-(c['annuity'] if sep else 0.);hits=rev-F>=1.1*c['benefits'];freq=100*hits.mean()
 records.append(dict(mask=mask,crossings=int(hits.sum()),B2_frequency_percent=float(freq)))
 if mask==0:eq('extremo_modelo_original',rev/g,p.original_M)
 if mask==127:eq('extremo_modelo_actual',rev/g,p.current_M);revnew=rev
new=pd.DataFrame(records).set_index('mask');previous=pd.read_csv(source(G/'PUENTE_CHILE_50000_128.csv')).set_index('mask')
eq('128_recuentos_emparejados',new.crossings,previous.crossings);eq('128_frecuencias_emparejadas',new.B2_frequency_percent,previous.B2_frequency_percent)
sequence=[0,1,3,7,15,31,63,127]
for row,mask in enumerate(sequence,1):
 cell('S3',row,1,supp[2][row][1],f'{new.loc[mask,"B2_frequency_percent"]:.3f}')
 if row>1:cell('S3',row,2,supp[2][row][2],f'{new.loc[mask,"B2_frequency_percent"]-new.loc[sequence[row-2],"B2_frequency_percent"]:+.3f}')
names=['IVA_destino','base_CIT_relativa','renta_IA_ordinaria','asignacion_PIT','respuesta_normalizada','consumo_disponible','instalacion_separada'];contrib=[]
for order in itertools.permutations(range(7)):
 mask=0;row=np.zeros(7)
 for j in order:
  updated=mask|(1<<j);row[j]=new.loc[updated,'B2_frequency_percent']-new.loc[mask,'B2_frequency_percent'];mask=updated
 contrib.append(row)
contrib=np.asarray(contrib);avg=contrib.mean(axis=0);eq('eficiencia_descomposicion',avg.sum(),new.loc[127,'B2_frequency_percent']-new.loc[0,'B2_frequency_percent'])
previous_attr=pd.read_csv(source(G/'ATRIBUCION_SOBRE_TODOS_LOS_ORDENES.csv')).query('case=="CHL_mid_r0_50000" and metric=="B2_frequency_percent"').set_index('change')
for row,name in enumerate(names,1):
 eq('atribucion_5040_ordenes',avg[row-1],previous_attr.loc[name,'allocation'])
 cell('S4',row,1,supp[3][row][1],f'{avg[row-1]:+.4f}')
 cell('S4',row,2,supp[3][row][2],f'{contrib[:,row-1].min():+.3f} to {contrib[:,row-1].max():+.3f}')
raw=pd.read_parquet(source(R/'paso_07d/evidencia/insumos/sorteos.parquet'));eq('sorteos_mismos',raw.g_ai_level,g)
F0=.00295;benefit=c['benefits']
for row,rev in enumerate([revnew,g*raw.mfc__hist_tax_mixture,g*raw.mfc__hist_total_revenue_mixture],1):
 hit0=np.asarray(rev)-F0>=benefit;hit2=np.asarray(rev)-F0>=1.1*benefit;k=int(hit2.sum());nn=len(hit2)
 lo=0 if k==0 else beta.ppf(.025,k,nn-k+1);hi=1 if k==nn else beta.ppf(.975,k+1,nn-k)
 cell('5',row,1,main[4][row][1],f'{100*hit0.mean():.3f}');cell('5',row,2,main[4][row][2],f'{100*hit2.mean():.3f}');cell('5',row,3,main[4][row][3],f'{100*lo:.3f}–{100*hi:.3f}')
print('Tablas y reconciliacion: 128 combinaciones x 50.000 sorteos retenidos y 5.040 ordenes comprobados.',flush=True)

# New calibration diagnostics are evaluated from their saved contexts, with direct
# channel accounting and separately calculated coefficient slopes.
configs=json.loads(source(R/'paso_07h/evidencia/CONFIGURACIONES_FLUJOS.json').read_text());flow=pd.read_csv(source(R/'paso_07h/resultados/FLUJOS_DIAGNOSTICOS.csv')).set_index('flow_id');newflows=[]
for item in configs:
 c=item['context'];p=c['prepared'];a,w,n=item['coefficients'];s=p['ls'];tr=min(1,(c['epsilon']+(1-c['epsilon'])*c['exposure'])**c['beta']*(c['epsilon']+(1-c['epsilon'])*c['q'])**c['gamma']/c['s_frontier']);gain=np.expm1(10*np.log1p(c['phi']*tr));sp=1/(1+(1-s)/s*np.exp(-c['pressure_per_q']*c['q']));dw=(sp-s)+sp*gain;dn=gain-dw
 labor=(p['ssc']+(1-a)*p['pit'])/s*p['ul']*dw;capital=(p['cit']*p['relative_base']+a*p['pit'])/(1-s)*p['uk']*dn;ta=c['lambda_ai']*c['tau_ai']*max(0,1-c['erosion_ai']*c['tau_ai'])*gain;v=p['vat_yield']*p['uc'];direct=labor+capital+ta;cw=v*(dw-labor);cn=v*(dn-capital-ta);rev=direct+w*cw+n*cn
 saved=flow.loc[item['flow_id']];eq('diagnosticos_calibracion',rev,saved.revenue);eq('pendientes_gasto',[cw,cn],[saved.vat_w_slope,saved.vat_n_slope]);newflows.append([item['flow_id'],rev,direct,cw,cn])
newflow=pd.DataFrame(newflows,columns=['flow_id','R','direct','cw','cn']).set_index('flow_id');front=pd.read_csv(source(R/'paso_07h/resultados/FRONTERAS_DIAGNOSTICAS.csv'));r=newflow.loc[front.flow_id,'R'].to_numpy();ceiling=r-1.1*front.benefits.to_numpy()-front.spb.to_numpy();eq('fronteras_calibraciones',ceiling,front.Fmax);yes('clasificacion_calibraciones',(ceiling-front.F_recurring_author.to_numpy()>=-1e-12)==front.B2.to_numpy())
th=pd.read_csv(source(R/'paso_07h/resultados/UMBRALES_CASOS_7.csv'));ch=th.query('country_id=="CHL" and scenario_id=="mid" and regime_id=="r4"').iloc[0];p=newflow.loc[ch.flow_id];required=1.1*ch.benefits+ch.F_recurring_author+ch.spb;kw=(required-p.direct)/(p.cw+.5*p.cn);margin=(p.R-1.1*ch.benefits-ch.spb)/ch.F_recurring_author
eq('umbral_consumo',kw,ch.k_required_kn_half_kw);eq('umbral_consumo_texto',kw,.4824,5.00001e-5);eq('margen_costo_texto',(margin-1)*100,25.91,.005001)
calibration={'k_required_half_rule':float(kw),'cost_margin_percent':float((margin-1)*100)}
# Pressure is multiaffine in the seven supports; evaluate the registered vertices.
paramnames=['lambda_LS','delta_s','zeta_s','RST','E_auto','psi_s','E_aug'];bounds=[]
for country in ['CHL','PER','COL','MEX']:
 ps=[]
 for vals in itertools.product(*[(value(n,country,'low_value'),value(n,country,'high_value')) for n in paramnames]):
  lam,ds,zs,rst,ea,ss,aug=vals;ps.append(lam*(-(ds-zs*rst)*ea+ss*aug))
 bounds.append(dict(country_id=country,min=min(ps),max=max(ps)))
eq('presion_extremos_min',min(x['min'] for x in bounds),-.03);eq('presion_extremos_max',max(x['max'] for x in bounds),.1775)
pd.DataFrame(cells).to_csv(O/'CELDAS_RESULTADOS_VERIFICADAS.csv',index=False)
(O/'TITULARES_CALIBRACION.json').write_text(json.dumps(calibration,indent=2)+'\n',encoding='utf-8')
result={'status':'PASS','matched_draws':50000,'coalitions':128,'draw_coalition_evaluations':6400000,'permutations':5040,'calibration_flows':len(configs),'calibration_frontiers':len(front),'document_cells':len(cells),'checks_by_group':dict(checks),'max_absolute_errors':dict(errors),'source_hashes':hashes,'scope':'Reconstruccion de operaciones y cifras desde insumos retenidos; no estimacion causal ni nuevo muestreo.'}
(O/'VERIFICACION_RESULTADOS.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','document_cells':len(cells),'calibration_flows':len(configs),'calibration_frontiers':len(front)}))
