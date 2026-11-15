from pathlib import Path
import json, shutil
import pandas as pd
ROOT=Path(__file__).resolve().parents[3];R=ROOT/'revision_jpm_v2';T=ROOT/'extensions/stress';O=T/'resultados'
d=pd.read_csv(O/'SIETE_CASOS_TRES_DEPENDENCIAS.csv')
key=['country_id','scenario_id','regime_id','policy_variant_id']
g=d.query("mode=='reference'").groupby(key+['dependency']).recurring_author_frequency.agg(['min','max','mean']).reset_index()
g.to_csv(O/'RESUMEN_SIETE_CASOS.csv',index=False)
tail=pd.read_csv(O/'DECILES_FACTOR_SIETE_CASOS.csv').groupby(key+['stratum']).frequency.agg(['min','max']).reset_index()
tail.to_csv(O/'RESUMEN_DECILES_FACTOR.csv',index=False)
KEY=key+['rule','mode'];PF=['recurring_author_frequency','registered_leakage_frequency','nonnegative_frontier_frequency'];QF=['Fmax_p05','Fmax_p50','Fmax_p95']
delta=[]
for seed in [20261114,20261215,20261316]:
 a=pd.read_csv(O/f'MC_ESTRES_{seed}.csv').query('n==50000').set_index(KEY).sort_index()
 for dep in ['independent','rank_factor_nominal']:
  b=pd.read_csv(ROOT/f'extensions/convergence/resultados/MC_{seed}_{dep}.csv').query('n==50000').set_index(KEY).sort_index()
  assert a.index.equals(b.index)
  x=(a[PF+QF]-b[PF+QF]).reset_index();x['seed']=seed;x['comparison']=dep;delta.append(x)
full=pd.concat(delta,ignore_index=True);full.to_csv(O/'DIFERENCIAS_CELDA_ENTRE_DEPENDENCIAS.csv',index=False)
registered=pd.read_csv(O/'SENSIBILIDAD_ENTRE_DEPENDENCIAS.csv')
for r in registered.itertuples():
 z=full.query('seed==@r.seed and comparison==@r.comparison')[r.metric]
 assert abs(z.abs().max()-r.max_abs_difference)<1e-14
c=pd.read_csv(O/'CORRELACIONES_REALIZADAS.csv');valid=c.realized_spearman.dropna().abs()
drivers=pd.read_csv(O/'DRIVERS_ENTRE_DEPENDENCIAS.csv')
conv=pd.read_csv(O/'CONVERGENCIA_ESCALERA.csv');disp=pd.read_csv(O/'DISPERSION_ENTRE_SEMILLAS.csv')
summary={
 'comparison_rows':len(full),
 'max_differences':{dep:{m:float(z[m].abs().max()) for m in PF+QF} for dep,z in full.groupby('comparison')},
 'spearman_abs_min':float(valid.min()),'spearman_abs_max':float(valid.max()),'spearman_defined':len(valid),'spearman_total':len(c),
 'constant_vectors':int(pd.read_csv(O/'PRESERVACION_MARGINALES.csv').constant.sum()),
 'driver_overlap_by_comparison':{dep:{str(k):int(v) for k,v in z.top3_overlap.value_counts().items()} for dep,z in drivers.groupby('comparison')},
 'quantile_within_25k_50k':{m:float(conv.query('n_from==25000 and metric==@m').max_abs_difference.max()) for m in QF},
 'quantile_between_seed':dict(zip(disp.query('metric in @QF').metric,disp.query('metric in @QF').max_between_seed_range)),
 'first_step_max_frequency_drift':float(conv.query('n_from==5000 and metric in @PF').max_abs_difference.max()),
 'interpretation':'Conditional model frequencies; contrasts include dependence choice and finite Monte Carlo variation, not causal effects or empirical probabilities'
}
(O/'RESUMEN_INTERPRETACION.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
print(g.to_string(index=False))
print(tail.to_string(index=False))
