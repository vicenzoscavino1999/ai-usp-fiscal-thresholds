"""Conditional annual frontiers, endogenous capture and financing identities.

Ratios are to contemporaneous counterfactual no-AI GDP. Financing balances
are signed changes relative to the counterfactual, not gross sovereign debt.
"""
from itertools import product
import numpy as np
from scipy.optimize import brentq

VERTICES=list(product([0.,.3],[0.,1.],[0.,1.]))

def logistic(z):
    return 1/(1+np.exp(-np.asarray(z)))

def translation(ctx,q=None,exposure=None):
    q=ctx['q'] if q is None else np.asarray(q)
    e=ctx['exposure'] if exposure is None else np.asarray(exposure)
    eps=ctx['epsilon']
    score=(eps+(1-eps)*e)**ctx['beta']*(eps+(1-eps)*q)**ctx['gamma']
    return np.where((q>0)&(e>0),np.minimum(1,score/ctx['s_frontier']),0.)

def factor_coefficients(ctx,coef):
    a,w,n=coef;p=ctx['prepared'];v=p['vat_yield']*p['uc']
    tl=(p['ssc']+(1-a)*p['pit'])/p['ls']*p['ul']
    tn=(p['cit']*p['relative_base']+a*p['pit'])/(1-p['ls'])*p['uk']
    return float(tl*(1-v*w)+v*w),float(tn*(1-v*n)+v*n),float(v)

def capture(ctx,coef,*,years=10,q=None,exposure=None,g=None,tau=None):
    q=ctx['q'] if q is None else np.asarray(q)
    tau=ctx['tau_ai'] if tau is None else np.asarray(tau)
    tr=translation(ctx,q,exposure)
    gain=np.expm1(np.asarray(years)*np.log1p(ctx['phi']*tr)) if g is None else np.asarray(g)
    if np.any(~np.isfinite(gain)) or np.any(gain<0) or np.any(~np.isfinite(q)) or np.any(q<0):
        raise ValueError('Gain and adoption must be finite and nonnegative')
    s=ctx['prepared']['ls'];sp=logistic(np.log(s/(1-s))+ctx['pressure_per_q']*q)
    sp=np.where(q==0,s,sp)
    dw=sp*(1+gain)-s
    L,N,v=factor_coefficients(ctx,coef)
    ai=ctx['lambda_ai']*tau*np.maximum(0,1-ctx['erosion_ai']*tau)
    revenue=L*dw+N*(gain-dw)+(1-v*coef[2])*ai*gain
    # Zero aggregate gain at positive adoption can redistribute factor income.
    # The no-AI anchor is the joint corner q=0, g=0, where dw=R=0 exactly.
    # M=R/g is deliberately undefined at g=0; it is not the derivative dR/dg.
    conversion=np.divide(revenue,gain,out=np.full(np.shape(revenue),np.nan),where=gain>0)
    return {'g':gain,'dw':dw,'revenue':revenue,'share_prime':sp,'M_average':conversion}

def affine_capture(ctx,coef):
    L,N,v=factor_coefficients(ctx,coef);s=ctx['prepared']['ls']
    sp=float(logistic(np.log(s/(1-s))+ctx['pressure_per_q']*ctx['q']))
    ai=ctx['lambda_ai']*ctx['tau_ai']*max(0,1-ctx['erosion_ai']*ctx['tau_ai'])
    return L*sp+N*(1-sp)+(1-v*coef[2])*ai,(L-N)*(sp-s)

def invert_gain(ctx,coef,required):
    A,B=affine_capture(ctx,coef);gmax=np.expm1(10*np.log1p(ctx['phi']))
    out={'gain_slope':A,'gain_intercept':B,'g_max_T1':gmax,'g_required':np.nan,'T_required_frozen_distribution':np.nan}
    if A<=0:
        out['gain_status']='nonincreasing_requires_interval_analysis';return out
    g=(required-B)/A
    if g<=0:
        out.update(g_required=0.,gain_status='zero_gain_covers_with_redistribution_distribution_fixed')
        return out
    tr=np.expm1(np.log1p(g)/10)/ctx['phi']
    out.update(g_required=g,T_required_frozen_distribution=tr,gain_status='within_scenario_frontier' if g<=gmax+1e-12 else 'beyond_scenario_frontier')
    return out

def invert_ai(ctx,coef,required,cap=1.):
    base=float(capture(ctx,coef,tau=0)['revenue']);g=float(capture(ctx,coef)['g'])
    _,_,v=factor_coefficients(ctx,coef)
    scale=g*ctx['lambda_ai']*(1-v*coef[2]);e=ctx['erosion_ai']
    peak=min(cap,1/(2*e)) if e>0 else cap
    need=required-base
    out={'ai_net_scale':scale,'ai_peak_rate':peak,'tau_ai_required':np.nan}
    if need<=0:out.update(tau_ai_required=0.,ai_status='covered_without_additional_AI');return out
    if scale<=0 or need>scale*peak*max(0,1-e*peak)+1e-12:
        out['ai_status']='no_root_in_effective_rate_domain';return out
    ratio=need/scale
    root=ratio if e==0 else 2*ratio/(1+np.sqrt(max(0,1-4*e*ratio)))
    out.update(tau_ai_required=root,ai_status='feasible_net_effective_rate');return out

def derivative(ctx,coef,x,variable):
    q=np.asarray(x) if variable=='q' else ctx['q'];ep=np.asarray(x) if variable=='exposure' else ctx['exposure']
    eps=ctx['epsilon'];tr=translation(ctx,q,ep);phi=ctx['phi'];g=np.expm1(10*np.log1p(phi*tr))
    s=ctx['prepared']['ls'];sp=logistic(np.log(s/(1-s))+ctx['pressure_per_q']*q)
    L,N,v=factor_coefficients(ctx,coef);j=(1-v*coef[2])*ctx['lambda_ai']*ctx['tau_ai']*max(0,1-ctx['erosion_ai']*ctx['tau_ai'])
    A=L*sp+N*(1-sp)+j
    expo=ctx['gamma'] if variable=='q' else ctx['beta']
    dtr=np.where(tr<1,expo*tr*(1-eps)/(eps+(1-eps)*np.asarray(x)),0.)
    gp=10*phi*(1+phi*tr)**9*dtr
    return A*gp+((L-N)*ctx['pressure_per_q']*sp*(1-sp)*(1+g) if variable=='q' else 0.)

def monotonic_bound(ctx,coef,lo,hi,variable):
    """Conservative analytic lower bound for dR/dx on the whole interval.

    The productivity term is nonnegative when both endpoint coefficient
    mixtures are positive. A capped T allows its lower bound to be zero.
    This deliberately refuses a certificate when a redistribution effect
    could dominate; the caller then labels numerical search explicitly.
    """
    L,N,v=factor_coefficients(ctx,coef)
    j=(1-v*coef[2])*ctx['lambda_ai']*ctx['tau_ai']*max(0,1-ctx['erosion_ai']*ctx['tau_ai'])
    if min(L,N)+j<0:return -np.inf
    if variable=='exposure':return 0.
    tr0=float(translation(ctx,lo));tr1=float(translation(ctx,hi));eps=ctx['epsilon'];phi=ctx['phi']
    gp=0. if tr1>=1 else 10*phi*(1+phi*tr0)**9*ctx['gamma']*tr0*(1-eps)/(eps+(1-eps)*hi)
    negative=min(0.,(L-N)*ctx['pressure_per_q'])*.25*(1+phi*tr1)**10
    return (min(L,N)+j)*gp+negative

def invert_operational(ctx,coef,required,variable):
    """Minimum increase from the registered q/exposure, with full recapture.

    A global result is claimed only when the analytic derivative certificate
    holds. Otherwise report a bounded numerical first crossing, not proof of
    global impossibility/minimality.
    """
    lo=ctx['q'] if variable=='q' else ctx['exposure']
    hi=ctx['q_bar']-ctx['epsilon_mu'] if variable=='q' else 1.
    fun=lambda z:float(capture(ctx,coef,**{variable:z})['revenue'])-required
    bound=monotonic_bound(ctx,coef,lo,hi,variable);cert=bound>=-1e-14
    out={'required':np.nan,'derivative_lower_bound':bound,'monotonic_certified':cert}
    if fun(lo)>=0:out.update(required=lo,status='already_covered_at_registered_value');return out
    if cert:
        if fun(hi)<0:out['status']='not_reachable_within_declared_domain';return out
        root=brentq(fun,lo,hi,xtol=5e-15);out.update(required=root,status='minimum_increase_certified');return out
    # Full-interval monotonicity can fail when T saturates but labour shares
    # still move with q. Resolve the first crossing by interval subdivision,
    # certifying every skipped interval by an upper revenue bound.
    eps=ctx['epsilon'];L,N,v=factor_coefficients(ctx,coef);s=ctx['prepared']['ls'];phi=ctx['phi']
    J=(1-v*coef[2])*ctx['lambda_ai']*ctx['tau_ai']*max(0,1-ctx['erosion_ai']*ctx['tau_ai'])
    cap=(((ctx['s_frontier']/(eps+(1-eps)*ctx['exposure'])**ctx['beta'])**(1/ctx['gamma']))-eps)/(1-eps)
    def bounds(left,right):
        trl=float(translation(ctx,left));trh=float(translation(ctx,right))
        gl=(1+phi*trl)**10-1;gh=(1+phi*trh)**10-1
        sl=float(logistic(np.log(s/(1-s))+ctx['pressure_per_q']*left));sh=float(logistic(np.log(s/(1-s))+ctx['pressure_per_q']*right))
        ss=[min(sl,sh),max(sl,sh)];aa=[L*z+N*(1-z)+J for z in ss]
        maxrev=max((L*z+N*(1-z)+J)*g+(L-N)*(z-s) for z in ss for g in [gl,gh])
        fmin=min(z*(1-z) for z in ss);fmax=.25 if ss[0]<=.5<=ss[1] else max(z*(1-z) for z in ss)
        d=(L-N)*ctx['pressure_per_q'];dd=[d*f*(1+g) for f in [fmin,fmax] for g in [gl,gh]]
        if left>=cap:gpmin=gpmax=0.
        else:
            gpmin=10*phi*(1+phi*trl)**9*ctx['gamma']*trl*(1-eps)/(eps+(1-eps)*right)
            gpmax=10*phi*(1+phi*trh)**9*ctx['gamma']*trh*(1-eps)/(eps+(1-eps)*left)
            if right>cap:gpmin=0.
        pp=[a*gp for a in aa for gp in [gpmin,gpmax]]
        return maxrev,min(pp)+min(dd),max(pp)+max(dd)
    pieces=[lo]+([cap] if lo<cap<hi else [])+[hi]
    stack=[(pieces[i],pieces[i+1],0) for i in range(len(pieces)-2,-1,-1)]
    intervals=0
    while stack:
        left,right,depth=stack.pop();intervals+=1
        maximum,lower,upper=bounds(left,right)
        if maximum<required-2e-14:continue
        fl=fun(left);fr=fun(right)
        if fl>=0:
            out.update(required=left,status='minimum_increase_interval_certified',intervals=intervals);return out
        if upper<=0:continue
        if lower>=0:
            if fr<0:continue
            root=brentq(fun,left,right,xtol=5e-15)
            out.update(required=root,status='minimum_increase_interval_certified',intervals=intervals);return out
        if depth>=48 or right-left<=1e-13:
            # Keep a truthful fallback for nearly tangent or precision-limited
            # cases. Never call such a result a proof of non-existence.
            out.update(status='precision_limited_interval_unresolved',intervals=intervals);return out
        mid=(left+right)/2
        stack.append((mid,right,depth+1));stack.append((left,mid,depth+1))
    out.update(status='not_reachable_interval_certified',intervals=intervals)
    return out

def financing(revenue,cost,f,setup,interest,growth,replacements=None):
    """Signed incremental financing and exact constant-f frontiers.

    revenue and cost are one-dimensional paths at fixed unknown coefficients.
    Additional investment occurs at the end of each specified period.
    Initial external capital earns the same rate as liabilities cost.
    """
    revenue=np.asarray(revenue,dtype=float);cost=np.asarray(cost,dtype=float);H=len(revenue)
    rep=np.zeros(H) if replacements is None else np.asarray(replacements,dtype=float)
    if interest<=-1 or growth<=-1 or H!=len(cost) or H!=len(rep):raise ValueError('Invalid financing inputs')
    a=(1+interest)/(1+growth);years=np.arange(1,H+1);discount=a**(-years)
    net=cost+f+rep-revenue
    pv=setup+np.cumsum(net*discount)
    balances=a**years*pv
    fmax=(np.cumsum((revenue-cost-rep)*discount)-setup)/np.cumsum(discount)
    initial_need=np.maximum.accumulate(np.maximum(0,np.r_[setup,pv]))[1:]
    return dict(balance=balances,fmax=fmax,initial_capital=initial_need,net_primary=net,rep=rep,a=a)

def annuity_schedule(setup,interest,growth,term=3):
    payment=setup/term if abs(interest)<1e-14 else setup*interest/(-np.expm1(-term*np.log1p(interest)))
    stock=setup;rows=[]
    for t in range(1,term+1):
        charge=interest*stock;principal=payment-charge;end=stock-principal
        rows.append(dict(year=t,opening_nominal_gdp0=stock,interest_nominal_gdp0=charge,principal_nominal_gdp0=principal,payment_nominal_gdp0=payment,closing_nominal_gdp0=end,payment_ratio_year=payment/(1+growth)**t,closing_ratio_year=end/(1+growth)**t))
        stock=end
    return rows
