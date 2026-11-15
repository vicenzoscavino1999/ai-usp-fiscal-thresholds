from paso04_common import *
B=R.parent/'upstream'

x=load_inputs();m=x['macro_anchor'];f=x['fiscal_anchor'];pct=x['historical_capture_percentiles']
published=pd.read_parquet(B/'data/model_inputs/historical_capture_distribution.parquet')
allrows=[];variants=[];samples=[];summary=[]
def distribution(d,variant_id,concept,source,parent='structural',note='',winsor=True,empirical=False):
    z=d[d.delta_gdp_lcu.gt(0)&np.isfinite(d.mfc)].copy()
    raw=z.mfc.to_numpy()
    assert len(raw)>=5,(variant_id,len(raw))
    vals=np.clip(raw,*np.quantile(raw,[.01,.99])) if winsor else raw
    pos=vals[vals>=0];neg=vals[vals<0]
    assert len(pos)>0
    rec={'variant_id':variant_id,'concept':concept,'source':source,'parent_variant':parent,'note':note,'n_years':len(raw),
         'first_year':int(z.year.min()),'last_year':int(z.year.max()),'p_negative':float(np.mean(vals<0)),
         'winsor_01_99':winsor,'empirical_resampling':empirical,'positive_only':False,
         **{f'pos_p{q}':float(np.quantile(pos,q/100)) for q in [10,50,90]},
         **{f'neg_p{q}':float(np.quantile(neg,q/100)) if len(neg) else None for q in [10,50,90]}}
    variants.append(rec)
    for year,a,b in zip(z.year,raw,vals):samples.append({'variant_id':variant_id,'year':int(year),'raw_capture':float(a),'capture_for_draw':float(b)})
    return rec

for country in ['PER','CHL','COL','MEX']:
    base=m[m.country_id.eq(country)].merge(f[f.country_id.eq(country)],on=['country_id','year'],suffixes=('','_fiscal')).sort_values('year')
    for concept,column in [('tax','tax_revenue_gdp'),('total_revenue','total_revenue_gdp')]:
        d=base[['country_id','year','gdp_nominal_lcu','gdp_constant_lcu','gdp_deflator',column]].copy()
        d['revenue_nominal_lcu']=d[column]/100*d.gdp_nominal_lcu
        d['delta_gdp_lcu']=d.gdp_nominal_lcu.diff();d['delta_revenue_lcu']=d.revenue_nominal_lcu.diff()
        d['nominal_growth']=d.gdp_nominal_lcu.pct_change();d['mfc']=d.delta_revenue_lcu/d.delta_gdp_lcu
        d['revenue_real_lcu']=d.revenue_nominal_lcu/(d.gdp_deflator/100)
        d['capture_real_diagnostic']=d.revenue_real_lcu.diff()/d.gdp_constant_lcu.diff()
        d['revenue_concept']=concept
        d['excluded_nonpositive_denominator']=d.delta_gdp_lcu.le(0)
        d['near_zero_denominator_1pct']=d.nominal_growth.abs().lt(.01)
        d['near_zero_denominator_2pct']=d.nominal_growth.abs().lt(.02)
        d['negative_capture']=d.mfc.lt(0);d['capture_above_one']=d.mfc.gt(1)
        ref=published[published.country_id.eq(country)&published.revenue_concept.eq(concept)][['year','mfc_hist_gross']]
        merged=d.merge(ref,on='year',validate='one_to_one')
        assert np.allclose(merged.mfc,merged.mfc_hist_gross,atol=1e-12,equal_nan=True)
        eligible=d[d.delta_gdp_lcu.gt(0)&np.isfinite(d.mfc)]
        vals=np.clip(eligible.mfc,*np.quantile(eligible.mfc,[.01,.99]));pos=vals[vals>=0];neg=vals[vals<0]
        p=pct[pct.country_id.eq(country)&pct.revenue_concept.eq(concept)&pct.percentile_sample.eq('2000plus')].iloc[0]
        for q in [10,50,90]:assert abs(np.quantile(pos,q/100)-p[f'p{q}_mfc_hist_positive'])<1e-12
        assert abs(np.mean(vals<0)-p.p_negative_capture)<1e-12
        summary.append({'country_id':country,'concept':concept,'source_rows':len(d),'included_years':len(eligible),
                        'nonpositive_denominators':int(d.delta_gdp_lcu.le(0).sum()),'near_zero_1pct':int(d.near_zero_denominator_1pct.sum()),
                        'near_zero_2pct':int(d.near_zero_denominator_2pct.sum()),'negative_capture_included':int((eligible.mfc<0).sum()),
                        'raw_min':float(eligible.mfc.min()),'raw_max':float(eligible.mfc.max()),'winsor_low':float(vals.min()),'winsor_high':float(vals.max()),
                        'min_positive_nominal_growth':float(eligible.nominal_growth.min()),'all_baseline_percentiles_reproduced':True})
        allrows.append(d)
        if country!='CHL':continue
        root='hist_'+concept+'_mixture'
        canon=distribution(d,root,concept,'OECD' if concept=='tax' else 'IMF',note='Published 2000+ capture, 1-99 winsor, PERT support p10/p50/p90; negative mixture retained')
        variants.append({**canon,'variant_id':'hist_'+concept+'_positive','parent_variant':root,'positive_only':True,'note':'Same positive PERT component; negative mass conditioned away'})
        for label,select in [('2010plus',d.year.ge(2010)),('2015plus',d.year.ge(2015)),('no2020_21',~d.year.isin([2020,2021])),('no2008_09',~d.year.isin([2008,2009])),('min_g_1pct',d.nominal_growth.ge(.01)),('min_g_2pct',d.nominal_growth.ge(.02))]:
            distribution(d[select],root+'_'+label,concept,canon['source'],root,'One filter only: '+label)
        distribution(d,root+'_no_winsor',concept,canon['source'],root,'No clipping of historical values before PERT percentiles',winsor=False)
        distribution(d,root+'_empirical',concept,canon['source'],root,'Uniform resampling of untrimmed eligible historical years; alternative empirical support',winsor=False,empirical=True)

aud=pd.concat(allrows,ignore_index=True);aud.to_csv(S/'AUDITORIA_HISTORICA_ANUAL.csv',index=False)
pd.DataFrame(summary).to_csv(S/'RESUMEN_AUDITORIA_HISTORICA.csv',index=False)

# Source replacement: select actual GDP-ratio rows, not both LCU and GDP sheets.
# Retain government coverage, SC definition, common GDP and identical adjacent years.
raw=pd.read_parquet(B/'data/raw_snapshots/v1.0.1-official-4c/grd/grd_revenue.parquet')
grd=raw[raw.country_id.eq('CHL')&raw.government_level.eq('general_government')&raw.unit.eq('gdp_ratio')].copy()
assert not grd.duplicated('year').any()
base=m[m.country_id.eq('CHL')][['year','gdp_nominal_lcu']].merge(f[f.country_id.eq('CHL')][['year','tax_revenue_gdp','total_revenue_gdp']],on='year').merge(grd,on='year').sort_values('year')
source_rows=[]
for concept,col,nrcol,rescol in [('tax','tax_revenue_including_sc','non_resource_tax_revenue_including_sc','resource_tax_revenue'),('total_revenue','total_revenue_including_grants_inc_sc','total_non_resource_revenue_inc_sc','total_resource_revenue')]:
    for nonresource in [False,True]:
        # The source comparison keeps grants included, as in total IMF revenue.
        # The nonresource comparison uses GRD's explicitly ex-grants series on both sides.
        grosscol='total_revenue_excluding_grants_inc_sc' if nonresource and concept=='total_revenue' else col
        altcol=nrcol if nonresource else col
        if nonresource:
            good=base[[grosscol,nrcol,rescol]].dropna()
            assert np.allclose(good[grosscol]-good[rescol],good[nrcol],atol=1e-9),concept
        a=base[['year','gdp_nominal_lcu',grosscol,altcol] if altcol!=grosscol else ['year','gdp_nominal_lcu',grosscol]].copy()
        a['delta_gdp_lcu']=a.gdp_nominal_lcu.diff()
        a['mfc']=(a[altcol]*a.gdp_nominal_lcu).diff()/a.delta_gdp_lcu
        current_valid=np.isfinite(a.mfc)&a.delta_gdp_lcu.gt(0)
        # The parent GRD gross and OECD/IMF comparisons use this exact year set.
        if not nonresource:
            o=base[['year','gdp_nominal_lcu',concept+'_gdp' if concept=='tax_revenue' else ('tax_revenue_gdp' if concept=='tax' else 'total_revenue_gdp')]].copy()
            origcol='tax_revenue_gdp' if concept=='tax' else 'total_revenue_gdp'
            o['delta_gdp_lcu']=o.gdp_nominal_lcu.diff();o['mfc']=(o[origcol]/100*o.gdp_nominal_lcu).diff()/o.delta_gdp_lcu
            parent='hist_'+concept+'_common_grd_years'
            distribution(o[current_valid],parent,concept,'OECD' if concept=='tax' else 'IMF','hist_'+concept+'_mixture','Original source limited to same adjacent-year sample as GRD')
            distribution(a[current_valid],'grd_'+concept+'_mixture',concept,'GRD general government GDP-ratio, social contributions included',parent,'Only revenue/GDP source changed; common WDI GDP, sample, distribution and costs')
        else:
            gross=a.copy();gross['mfc']=(base[grosscol]*base.gdp_nominal_lcu).diff()/a.delta_gdp_lcu
            parent='grd_'+concept+'_gross_common_nonresource'
            distribution(gross[current_valid],parent,concept,'GRD','grd_'+concept+'_mixture','GRD gross on nonresource available years; for total revenue, grants excluded in both gross and nonresource. Difference from source-comparison parent combines window and grants definition, not a pure effect.')
            distribution(a[current_valid],'grd_'+concept+'_nonresource',concept,'GRD',parent,'Only removal of registered resource revenue; does not isolate tax-policy or all commodity effects')
        for _,r in a[current_valid].iterrows():source_rows.append({'year':r.year,'concept':concept,'nonresource':nonresource,'mfc':r.mfc})

pd.DataFrame(source_rows).to_csv(E/'COMPARACION_FUENTE_GRD_ANUAL.csv',index=False)
pd.DataFrame(variants).to_csv(S/'DISTRIBUCIONES_CAPTURA_REGISTRADAS.csv',index=False)
pd.DataFrame(samples).to_parquet(E/'MUESTRAS_HISTORICAS_PARA_SORTEO.parquet',index=False)
savejson('AUDITORIA_HISTORICA.json',{'status':'PASS','rederived_annual_rows':len(aud),'baseline_percentile_sets_verified':8,'matched_capture_distributions':len(variants),
 'selection':'GRD GDP-ratio rows only, general government, including social contributions; identical common years for one-at-a-time source replacements',
 'new_evidence_before_runs':'Frozen GRD has Chile nonresource series, so the conditional commodity audit is now feasible without a new database. Use gross/nonresource common-year pairs.',
 'legacy_diagnostic_limit':'Existing LOSO multiplies net V by a source ratio; it is a proxy rather than a rebuild preserving fixed costs. New matched comparisons replace capture and preserve fixed costs.',
 'commodity_flag_limit':'V1 commodity_shock_flag is hardcoded False, not evidence that commodity shocks are absent. Tax-policy reforms are not causally identified in the frozen panel.',
 'nominal_real_limit':'Canonical historical measure uses nominal revenue and nominal GDP; real diagnostic is computed separately and not pooled with the nominal estimand.'})
print(pd.DataFrame(summary).to_string(index=False));print('Distributions',len(variants))
