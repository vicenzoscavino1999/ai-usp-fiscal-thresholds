from pathlib import Path
import pandas as pd,json
N=Path(__file__).resolve().parents[1];S=N.parent;I=S/'evidencia/insumos';O=N/'resultados'
f=pd.read_csv(N/'fuentes/BFJZ_globalETR.csv');a=pd.read_stata(N/'fuentes/BFJZ_pit_alpha.dta');a['year']=a.year.dt.year
countries=['PER','CHL','COL','MEX'];f=f[f.country.isin(countries)];a=a[a.country.isin(countries)]
f.to_csv(O/'BFJZ_4PAISES_HISTORICO.csv',index=False);a.to_csv(O/'BFJZ_PIT_AUXILIAR_4PAISES.csv',index=False)
out=[]
for c in countries:
 z=f[f.country.eq(c)].sort_values('year');q=a[a.country.eq(c)&a.alpha_pit.notna()].sort_values('year');last=z.iloc[-1];p=q.iloc[-1]
 out.append({'country_id':c,'ETR_first_year':int(z.year.min()),'ETR_last_year':int(z.year.max()),'ETR_L_last':float(last.ETR_L),'ETR_K_last':float(last.ETR_K),'PIT_aux_last_year':int(p.year),'PIT_aux_K_share':float(p.alpha_pit),'PIT_threshold_imputed':float(p.pit_thr_imputed),'use':'Historical methodological comparison only; ETR uses factor-price NDP; no direct replacement of 2024 GDP anchors.'})
pd.DataFrame(out).to_csv(O/'ALCANCE_BFJZ.csv',index=False)
fiscal=pd.read_parquet(I/'fiscal_anchor.parquet');v=pd.read_parquet(I/'values.parquet')
rows=[]
for c in countries:
 def val(n):return float(v[v.country_id.eq(c)&v.name.eq(n)].baseline_value.iloc[0])
 r=fiscal[fiscal.country_id.eq(c)&fiscal.year.eq(2024)].iloc[0];s=val('LS_labor_share');P=r.pit_gdp/100;T=r.cit_gdp/100;SC=r.social_contrib_gdp/100;V=r.vat_gdp/100
 for alpha in [0,.15,.3,1]:
  tl=(SC+(1-alpha)*P)/s;tk=(T+alpha*P)/(1-s)
  rows.append({'country_id':c,'year':2024,'alpha_PIT_K':alpha,'labor_share':s,'PIT_gdp':P,'CIT_gdp':T,'SSC_gdp':SC,'VAT_gdp':V,'tau_l_aggregate':tl,'tau_k_aggregate':tk,'revenue_original_LK':P+T+SC,'revenue_reconstructed_LK':tl*s+tk*(1-s),'error':tl*s+tk*(1-s)-P-T-SC,'role':'literature-based assumption cases' if alpha!=1 else 'extreme identification case, not reference'})
pd.DataFrame(rows).to_csv(O/'ANCLAS_RECONCILIADAS_2024.csv',index=False)
assert max(abs(r['error']) for r in rows)<1e-14
print(pd.DataFrame(out).to_string(index=False));print(pd.DataFrame(rows).query('alpha_PIT_K == .15')[['country_id','tau_l_aggregate','tau_k_aggregate']].to_string(index=False))
