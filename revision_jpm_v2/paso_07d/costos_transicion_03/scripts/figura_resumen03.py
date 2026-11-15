from common03 import *
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
an=pd.read_csv(O/'FRONTERAS_ANUALES_480.csv');ch=pd.read_csv(O/'CANALES_HORIZONTES_2000.csv');fi=pd.read_parquet(O/'SENDAS_FINANCIACION.parquet');hh=pd.read_csv(O/'HORIZONTES_RECALCULADOS.csv');ff=pd.read_csv(O/'FRONTERAS_TRANSICION.csv');iv=pd.read_csv(O/'INVERSAS_RECALCULADAS.csv')
mask=lambda z:(z.country_id=='CHL')&(z.scenario_id=='mid')&(z.policy_variant_id=='GMI:GMI_ideal_aggregate')
z=fi[mask(fi)&(fi['mode']=='reference')&(fi.budget=='B2_reserved')]
plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(2,1,figsize=(10.5,8.7),sharex=True)
colors={'r0':'#27628d','r4':'#b25525'}
for reg,color in colors.items():
 a=an[mask(an)&an.regime_id.eq(reg)].iloc[0];c=ch[(ch.country_id=='CHL')&(ch.scenario_id=='mid')&(ch.regime_id==reg)].sort_values('H')
 ax=axes[0];ax.plot(c.H,c.revenue_reference-1.1*a.benefits-a.spb,color=color,label=f'{reg}: frontera anual de gasto recurrente')
 ax.axhline(a.F_recurring_author,color=color,linestyle=':',alpha=.85,label=f'{reg}: gasto recurrente del escenario')
 zz=z[(z.regime_id==reg)&(z.replacement=='none')].sort_values('H')
 axes[1].plot(zz.H,zz.balance_ratio_noAI,color=color,label=f'{reg}: sin reposición')
 if reg=='r4':
  zr=z[(z.regime_id==reg)&(z.replacement=='every3_author_sensitivity')].sort_values('H')
  axes[1].plot(zr.H,zr.balance_ratio_noAI,color=color,linestyle='--',label='r4: reposición cada tres años (sensibilidad)')
for ax in axes:
 ax.axhline(0,color='#555555',linewidth=.8);ax.yaxis.set_major_formatter(PercentFormatter(1,decimals=1));ax.grid(axis='y',alpha=.15);ax.legend(loc='best',fontsize=9,frameon=False)
axes[0].set_title('La cobertura anual no cancela la financiación acumulada',loc='left',fontweight='bold',pad=30)
axes[0].text(0,1.04,'Chile · GMI ideal · escenario moderado · captura de referencia ilustrativa',transform=axes[0].transAxes,fontsize=11,color='#555555')
axes[0].set_ylabel('Fracción del PIB sin IA de cada año')
axes[1].set_ylabel('Saldo incremental / PIB sin IA')
axes[1].set_xlabel('Horizonte desde 2024 (años del escenario)');axes[1].set_xticks([1,5,9,10,14,18,20,25]);axes[1].set_xlim(1,25)
axes[1].text(.01,.03,'Saldo positivo: recursos todavía por financiar. Saldo negativo: ahorro relativo al contrafactual.',transform=axes[1].transAxes,fontsize=9,color='#555555')
fig.text(.1,.02,'Cuenta inferior con margen de 10% y reserva del ajuste primario (B2). Incluye instalación e intereses.\nSupuestos constantes, sin pronóstico de adopción ni garantía de acceso a crédito. Fuentes: insumos preservados y cálculo propio.',fontsize=9,color='#555555')
fig.tight_layout(rect=(0,.085,1,1),h_pad=2.0);fig.savefig(O/'COBERTURA_Y_TRANSICION_CHILE.png',dpi=170);plt.close(fig)

# Small review tables, including a controlled comparison isolating M(H).
costpath=fi[(fi['mode']=='reference')&(fi.budget=='cash')&(fi.replacement=='none')]
compare=[]
for key,d in costpath.groupby(['country_id','scenario_id','regime_id','policy_variant_id'],sort=False):
 d=d.sort_values('H');r=an[(an.country_id==key[0])&(an.scenario_id==key[1])&(an.regime_id==key[2])&(an.policy_variant_id==key[3])].iloc[0]
 actual=hh[(hh.country_id==key[0])&(hh.scenario_id==key[1])&(hh.regime_id==key[2])&(hh.policy_variant_id==key[3])&(hh['mode']=='reference')&(hh.rule=='B2')].iloc[0]
 M10=float(d.loc[d.H.eq(10),'revenue'].iloc[0]/d.loc[d.H.eq(10),'g'].iloc[0]);hit=M10*d.g.to_numpy()>=1.1*d.benefits.to_numpy()+r.F_recurring_author+r.spb
 old=int(d.H.to_numpy()[np.flatnonzero(hit)[0]]) if hit.any() else np.nan
 compare.append({'country_id':key[0],'scenario_id':key[1],'regime_id':key[2],'policy_variant_id':key[3],'H_frozen_M10_same_recurring_cost':old,'H_recomputed_capture':actual.H_star_recurring,'changed':not np.isclose(old,actual.H_star_recurring,equal_nan=True)})
pd.DataFrame(compare).to_csv(O/'EFECTO_RECALCULAR_M_EN_H.csv',index=False)
sample=an[mask(an)&an.regime_id.isin(['r0','r4'])][['regime_id','F_recurring_author','Fmax_B2_reference','Fmax_B2_uniform','Fmax_B2_possible']]
sample=sample.merge(hh[mask(hh)&(hh.rule=='B2')&(hh['mode']=='reference')][['regime_id','H_star_recurring']],on='regime_id')
sample=sample.merge(ff[mask(ff)&(ff.budget=='B2_reserved')&(ff.replacement=='none')&(ff.H==10)][['regime_id','Fmax_path_reference','Fmax_path_uniform','Fmax_path_possible','balance_reference_noAI','initial_capital_reference_gdp0']],on='regime_id')
sample=sample.merge(ff[mask(ff)&(ff.budget=='B2_reserved')&(ff.replacement=='none')&(ff.H==25)][['regime_id','H_return_reference']],on='regime_id')
sample.to_csv(O/'CASOS_CHILE_MODERADO.csv',index=False)
print(sample.to_string(index=False));print('Changed H from endogenous capture:',sum(r['changed'] for r in compare));print('q inversion statuses:',iv.q_status.value_counts().to_dict())
