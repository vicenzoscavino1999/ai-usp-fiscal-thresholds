"""Capture with reconciled aggregate bases and explicitly unidentified routing.
All amounts are shares of baseline GDP. Tax-response indices are conditional,
not statutory rates. No calibrated point is silently assigned to unknown PIT
allocation or domestic consumption routing.
"""
from itertools import product
import numpy as np

def response_index(t0, relative_delta, erosion):
    t0,d,e=np.broadcast_arrays(t0,relative_delta,erosion)
    den=1-e*t0
    if np.any(den<=0) or np.any(d < -1):
        raise ValueError('Invalid normalized response support')
    return (1+d)*np.maximum(0.,1-e*t0*(1+d))/den

def prepare(*,g,delta_w,ls,pit,cit,ssc,vat_yield,
            chi_k,chi_dom,psi,chi_k0,chi_dom0,psi0,base_broadening,
            index_l,index_k,index_c,delta_l,delta_k,delta_c,
            erosion_l,erosion_k,erosion_c,lambda_ai,tau_ai,erosion_ai):
    """Prepare flows independent of the unknown allocation/consumption terms."""
    g=np.asarray(g,dtype=float);dw=np.asarray(delta_w,dtype=float);dn=g-dw
    if np.any(~np.isfinite(g)) or np.any(g<0) or not 0<ls<1 or not 0<=psi0<1:
        raise ValueError('Invalid growth or anchor')
    b0=chi_k0*chi_dom0*(1-psi0)
    if b0<=0:raise ValueError('Zero baseline corporate-exposure index')
    psi_r=np.maximum(0.,np.asarray(psi)*(1-np.clip(base_broadening,0,1)))
    relative_base=np.asarray(chi_k)*np.asarray(chi_dom)*(1-psi_r)/b0
    ul=response_index(index_l,delta_l,erosion_l)
    uk=response_index(index_k,delta_k,erosion_k)
    uc=response_index(index_c,delta_c,erosion_c)
    ai=g*np.asarray(lambda_ai)*np.asarray(tau_ai)*np.maximum(0.,1-np.asarray(erosion_ai)*np.asarray(tau_ai))
    return dict(g=g,dw=dw,dn=dn,ls=ls,pit=pit,cit=cit,ssc=ssc,vat_yield=vat_yield,
                relative_base=relative_base,ul=ul,uk=uk,uc=uc,ai=ai)

def evaluate(p,*,alpha_pit_k,k_w,k_n):
    """Return selected taxes and disposable flows; preserve signed increments."""
    if not 0<=alpha_pit_k<=1 or np.any(np.asarray(k_w)<0) or np.any(np.asarray(k_w)>1) or np.any(np.asarray(k_n)<0) or np.any(np.asarray(k_n)>1):
        raise ValueError('Allocation/consumption coefficient outside [0,1]')
    a=alpha_pit_k
    tax_l=(p['ssc']+(1-a)*p['pit'])/p['ls']*p['dw']*p['ul']
    tax_cit=p['cit']/(1-p['ls'])*p['dn']*p['relative_base']*p['uk']
    tax_pit_k=a*p['pit']/(1-p['ls'])*p['dn']*p['uk']
    disposable_w=p['dw']-tax_l
    disposable_n=p['dn']-tax_cit-tax_pit_k-p['ai']
    consumption=k_w*disposable_w+k_n*disposable_n
    tax_vat=p['vat_yield']*p['uc']*consumption
    revenue=tax_l+tax_cit+tax_pit_k+p['ai']+tax_vat
    conversion=np.divide(revenue,p['g'],out=np.full(np.shape(revenue),np.nan),where=p['g']>0)
    return dict(M=conversion,revenue=revenue,tax_l=tax_l,tax_cit=tax_cit,
                tax_pit_k=tax_pit_k,tax_ai=p['ai'],tax_vat=tax_vat,
                disposable_w=disposable_w,disposable_n=disposable_n,consumption=consumption)

def envelope(p,alpha_max=.3):
    """Exact extrema on a rectangular domain by multi-affinity, not sampling."""
    vertices=list(product([0.,alpha_max],[0.,1.],[0.,1.]))
    values=np.stack([evaluate(p,alpha_pit_k=a,k_w=w,k_n=n)['M'] for a,w,n in vertices])
    return dict(M_low=values.min(axis=0),M_high=values.max(axis=0),
                argmin=values.argmin(axis=0),argmax=values.argmax(axis=0),vertices=vertices)
