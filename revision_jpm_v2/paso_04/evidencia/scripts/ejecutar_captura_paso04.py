from paso04_common import *
from scipy.stats import beta
import time
t0=time.perf_counter();x=load_inputs();n=50000;seed=20261114
sampler=mc.ValueSampler(x['values'],n,seed,record_parameters=False)
frontier=sampler.array('E_prod_frontier');cs=mc.build_country_scenario_draws(sampler,x,'CHL','mid',frontier)
rd=mc.build_regime_draws(sampler,'r0')
policy=next(p for p in ta.policy_instances('CHL',x['policy_cost'],x['wpp']) if p['policy_variant_id']=='GMI:GMI_ideal_aggregate')
base=mc.compute_cell_arrays(sampler,x,'CHL','mid','r0',policy,cs,rd)
cost=policy['cost_gross_gdp'];spb=ta.value_lookup(x['values'])('sPB_plus_gdp_ratio',country='CHL');assert spb==0
fixed=base['fixed']['f_fix'];g=cs['g_ai_level']
common_hash={key:hashlib.sha256(np.asarray(cs[key]).tobytes()).hexdigest() for key in ['g_ai_level','translation_factor','phi_y_nominal']}
rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed,741])))
u=np.clip(rng.random(n),1e-12,1-1e-12);uneg=rng.random(n);uyear=rng.random(n)
spec=pd.read_csv(S/'DISTRIBUCIONES_CAPTURA_REGISTRADAS.csv')
samples=pd.read_parquet(E/'MUESTRAS_HISTORICAS_PARA_SORTEO.parquet')
def pert(lo,mode,hi):
    if abs(hi-lo)<1e-14:return np.full(n,mode)
    a=1+4*(mode-lo)/(hi-lo);b=1+4*(hi-mode)/(hi-lo)
    return lo+(hi-lo)*beta.ppf(u,a,b)
captures={'structural':base['mfc_gross']};parents={'structural':None};types={'structural':'model_channels'}
for _,v in spec.iterrows():
    if bool(v.empirical_resampling):
        vals=samples[samples.variant_id.eq(v.variant_id)].sort_values('year').capture_for_draw.to_numpy()
        capture=vals[np.minimum((uyear*len(vals)).astype(int),len(vals)-1)]
    else:
        positive=pert(v.pos_p10,v.pos_p50,v.pos_p90)
        if v.positive_only or v.p_negative==0:capture=positive
        else:
            negative=pert(v.neg_p10,v.neg_p50,v.neg_p90)
            capture=np.where(uneg<v.p_negative,negative,positive)
    captures[v.variant_id]=capture;parents[v.variant_id]=v.parent_variant;types[v.variant_id]='external_plausibility_not_ai_causal'

rows=[];outcomes={};supportcommon=cs['support_ok']&(cs['q_prod']<=cs['q_bar']+1e-14)&(cs['translation_factor']>=-1e-14)&(cs['translation_factor']<=1+1e-14)
draws=pd.DataFrame({'draw_id':np.arange(n),'g_ai_level':g,'translation_factor':cs['translation_factor'],'phi_y_nominal':cs['phi_y_nominal'],'fixed_cost_gdp':fixed,
 'cost_gross_gdp':cost,'spb':spb,'primitives_support_valid':supportcommon,'mfc_required_100':(cost+fixed)/g,'mfc_required_110':(1.1*cost+fixed+spb)/g})
convergence=[]
for mode,capture in captures.items():
    fs=g*capture-fixed;v=fs/cost
    # The independent expression must agree with the established compute function.
    calc=base if mode=='structural' else mc.compute_cell_arrays(sampler,x,'CHL','mid','r0',policy,cs,rd,historical_mfc=capture)
    assert np.allclose(fs,calc['fs_eff'],atol=1e-14)
    assert np.allclose(v,calc['v_gross'],atol=1e-12)
    basic=np.isfinite(v)&np.isfinite(capture)&np.isfinite(g)&(g>0)&(capture>0)
    assert np.array_equal(basic,calc['basic_valid'])
    draws['mfc__'+mode]=capture
    for basis,mask in [('all_draw',np.ones(n,dtype=bool)),('support_valid',supportcommon&basic)]:
        denom=int(mask.sum())
        for threshold in [1.,1.1]:
            success=basic&(fs>=threshold*cost+spb)
            k=int(np.sum(success&mask));freq=k/denom if denom else 0
            lo=0 if k==0 else float(beta.ppf(.025,k,denom-k+1));hi=1 if k==denom else float(beta.ppf(.975,k+1,denom-k))
            rows.append({'revision_id':REV,'mode':mode,'country_id':'CHL','policy_variant_id':policy['policy_variant_id'],'scenario_id':'mid','regime_id':'r0',
             'basis':basis,'threshold':threshold,'n_total':n,'denominator':denom,'crossings':k,'frequency':freq,'mc_binomial95_lower':lo,'mc_binomial95_upper':hi,
             'cost_gdp':cost,'spb':spb,'fixed_cost_gdp':float(fixed[0]),'capture_p10':float(np.quantile(capture,.1)),'capture_p50':float(np.median(capture)),
             'capture_p90':float(np.quantile(capture,.9)),'required_capture_p50':float(np.median((threshold*cost+fixed+spb)/g)),
             'V_p50':float(np.median(v)),'evidence_role':types[mode]})
            if basis=='all_draw':outcomes[(mode,threshold)]=success
    if mode in ['structural','hist_tax_positive','hist_tax_mixture','hist_total_revenue_positive','hist_total_revenue_mixture']:
        for count in [5000,10000,25000,50000]:
            for threshold in [1.,1.1]:convergence.append({'mode':mode,'n':count,'threshold':threshold,'count':int(outcomes[(mode,threshold)][:count].sum()),'frequency':float(outcomes[(mode,threshold)][:count].mean())})

comparisons=[]
pairs=[(mode,parent,('sample_and_definition_alignment' if '_gross_common_nonresource' in mode else ('sample_alignment' if '_common_grd_years' in mode else 'one_at_a_time_registered'))) for mode,parent in parents.items() if parent is not None]
pairs += [('hist_tax_positive','structural','capture_specification'),('hist_tax_mixture','structural','capture_specification'),('hist_total_revenue_positive','structural','capture_specification'),('hist_total_revenue_mixture','structural','capture_specification'),('hist_total_revenue_mixture','hist_tax_mixture','revenue_concept_changes_multiple_components')]
for mode,parent,role in pairs:
    for threshold in [1.,1.1]:
        a=outcomes[(mode,threshold)].astype(float);b=outcomes[(parent,threshold)].astype(float);delta=a-b
        se=float(np.std(delta,ddof=1)/np.sqrt(n));mean=float(np.mean(delta))
        comparisons.append({'variant':mode,'reference':parent,'comparison_role':role,'threshold':threshold,'n':n,'difference':mean,'paired_mc_se':se,
                            'paired_mc_normal95_lower':mean-1.96*se,'paired_mc_normal95_upper':mean+1.96*se,'only_variant_crosses':int(((a==1)&(b==0)).sum()),'only_reference_crosses':int(((a==0)&(b==1)).sum())})

pd.DataFrame(rows).to_csv(S/'CAPTURA_EMPAREJADA_50000.csv',index=False)
pd.DataFrame(comparisons).to_csv(S/'DESCOMPOSICION_CAPTURA_EMPAREJADA.csv',index=False)
pd.DataFrame(convergence).to_csv(E/'CONVERGENCIA_EMPAREJADA.csv',index=False)
draws.to_parquet(E/'SORTEOS_EMPAREJADOS.parquet',index=False)
for key,digest in common_hash.items():assert hashlib.sha256(np.asarray(cs[key]).tobytes()).hexdigest()==digest
result=pd.DataFrame(rows)
savejson('EJECUCION_CAPTURA.json',{'status':'PASS','revision_id':REV,'n':n,'seed':seed,'draw_modes':len(captures),'result_rows':len(rows),'paired_comparisons':len(comparisons),
 'elapsed_seconds':time.perf_counter()-t0,'common_draw_hashes':common_hash,'all_fixed_costs_identical':bool(np.all(fixed==fixed[0])),
 'shared_uniforms':'One common beta quantile vector, one sign vector, one empirical-year vector, independent of shared model primitives. Monte Carlo uncertainty conditional on calibration.',
 'draw_file_sha256':sha(E/'SORTEOS_EMPAREJADOS.parquet'),'baseline_5_modes':result[(result.basis=='all_draw')&result['mode'].isin(['structural','hist_tax_positive','hist_tax_mixture','hist_total_revenue_positive','hist_total_revenue_mixture'])].to_dict('records')})
print(result[(result.basis=='all_draw')&result.threshold.eq(1.)][['mode','crossings','frequency','capture_p50','required_capture_p50']].to_string(index=False))
print('Seconds',time.perf_counter()-t0)
