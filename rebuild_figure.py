from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
B=Path(__file__).resolve().parent;T=B/'revision_jpm_v2/paso_07d/costos_transicion_03';I=B/'publication';I.mkdir(exist_ok=True)
paths=pd.read_parquet(T/'resultados/SENDAS_FINANCIACION.parquet');paths=paths[(paths.country_id=='CHL')&(paths.scenario_id=='mid')&(paths.policy_variant_id=='GMI:GMI_ideal_aggregate')&(paths['mode']=='reference')&(paths.budget=='B2_reserved')]
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(2,1,figsize=(7,5.4),sharex=True);colors={'r0':'#1d587b','r4':'#a84524'}
for reg,color in colors.items():
 z=paths[(paths.regime_id==reg)&(paths.replacement=='none')].sort_values('H');f=float(z.F_recurring_author.iloc[0]);front=z.revenue-z.commitments_before_f
 axes[0].plot(z.H,front,color=color,label=f'{reg} annual frontier');axes[0].axhline(f,color=color,ls=':',lw=1.2,label=f'{reg} recurring cost')
 axes[1].plot(z.H,z.balance_ratio_noAI,color=color,label=f'{reg} no replacement')
z=paths[(paths.regime_id=='r4')&(paths.replacement=='every3_author_sensitivity')].sort_values('H');axes[1].plot(z.H,z.balance_ratio_noAI,color=colors['r4'],ls='--',label='r4 three-year replacement')
for ax in axes:
 ax.axhline(0,color='#555555',lw=.7);ax.yaxis.set_major_formatter(PercentFormatter(1,decimals=2 if ax is axes[0] else 1));ax.grid(axis='y',alpha=.15);ax.legend(fontsize=8.5,frameon=False,loc='best')
axes[0].set_ylabel('Recurring cost / no-AI GDP');axes[1].set_ylabel('Financing balance / no-AI GDP');axes[1].set_xlabel('Scenario horizon in years from 2024');axes[1].set_xticks([1,5,9,14,18,25]);axes[1].set_xlim(1,25)
fig.tight_layout(h_pad=1.2);fig.savefig(I/'figure_transition.png',dpi=240);plt.close(fig)
print('Figure 1 regenerated from the reconstructed financing paths.')
