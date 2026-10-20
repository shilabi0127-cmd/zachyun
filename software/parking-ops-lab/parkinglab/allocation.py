"""Bay-assignment MILP with per-request union bounds on occupancy conflicts.

The guarantee is conditional on the supplied independent endpoint distributions.
It is neither a joint system guarantee nor a claim about field traffic.
"""
import time

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from .risk import assigned_risk_bounds, risk_matrix, tolerance


def feasible_greedy(reservations, config, matrix, reserve=None):
    values = [r.priority if config.objective=='weighted_admission' else r.fee for r in reservations]
    limits = np.array([tolerance(r,config.risk_budget) for r in reservations])
    if reserve is not None:
        limits = np.maximum(0,limits-reserve)
    assignments = {}
    used = np.zeros(len(reservations))
    for i in sorted(range(len(reservations)),key=lambda i:(-values[i],reservations[i].start,i)):
        candidates=[]
        for bay in range(1,config.slots+1):
            peers=[j for j in assignments if assignments[j]==bay]
            added=float(sum(matrix[i,j] for j in peers))
            if added<=limits[i] and all(used[j]+matrix[i,j]<=limits[j] for j in peers):
                candidates.append((added,bay,peers))
        if candidates:
            added,bay,peers=min(candidates)
            assignments[i]=bay;used[i]=added
            for j in peers:used[j]+=matrix[i,j]
    return assignments


def optimize_risk(reservations, config, risks=None):
    started=time.perf_counter()
    n,k=len(reservations),config.slots
    risks=risks if risks is not None else risk_matrix(reservations,config.deviation_distribution)
    matrix=risks['upper']
    limits=np.array([tolerance(r,config.risk_budget) for r in reservations])
    values=np.array([r.priority if config.objective=='weighted_admission' else r.fee for r in reservations])
    # Very small coefficients are omitted, but their full per-row mass is reserved.
    cutoff=1e-8
    omitted=np.sum(np.where(matrix<=cutoff,matrix,0.),axis=1)
    incumbent=feasible_greedy(reservations,config,matrix,reserve=omitted)
    low=[];high=[]
    for i in range(n):
        for j in range(i+1,n):
            p=matrix[i,j]
            if p<=cutoff:continue
            (high if p>min(limits[i],limits[j]) else low).append((i,j,p))
    variable_count=n*k+len(low)
    rr=[];cc=[];vv=[];upper=[]
    def add(columns, coefficients, bound):
        row=len(upper);upper.append(bound)
        rr.extend([row]*len(columns));cc.extend(columns);vv.extend(coefficients)
    for i in range(n):add([i*k+b for b in range(k)],[1.]*k,1.)
    for i,j,_ in high:
        for b in range(k):add([i*k+b,j*k+b],[1.,1.],1.)
    risk_columns=[[] for _ in range(n)];risk_values=[[] for _ in range(n)]
    for pos,(i,j,p) in enumerate(low):
        z=n*k+pos
        for b in range(k):add([i*k+b,j*k+b,z],[1.,1.,-1.],1.)
        for item in (i,j):risk_columns[item].append(z);risk_values[item].append(p)
    for i in range(n):add(risk_columns[i],risk_values[i],max(0.,limits[i]-omitted[i]))
    # Break identical-bay occupancy symmetry without ruling out any allocation.
    for b in range(k-1):
        add([i*k+b+1 for i in range(n)]+[i*k+b for i in range(n)], [1.]*n+[-1.]*n,0.)
    A=coo_matrix((vv,(rr,cc)),shape=(len(upper),variable_count)).tocsc()
    c=np.concatenate([-np.repeat(values,k),np.zeros(len(low))])
    result=milp(c,integrality=np.r_[np.ones(n*k),np.zeros(len(low))],
        bounds=Bounds(np.zeros(variable_count),np.ones(variable_count)),
        constraints=LinearConstraint(A,np.full(len(upper),-np.inf),upper),
        options={'time_limit':config.time_limit,'mip_rel_gap':0.})
    if result.status not in (0,1):
        raise RuntimeError('Risk allocation solver failed: '+str(result.message))
    source='verified_greedy_fallback'
    if result.x is not None:
        chosen=np.argwhere(result.x[:n*k].reshape(n,k)>.5)
        candidate={int(i):int(b)+1 for i,b in chosen}
        risk=assigned_risk_bounds(candidate,matrix,n)
        valid=len(candidate)==len(chosen) and all(risk[i]<=limits[i]+1e-7 for i in candidate)
        if valid and sum(values[i] for i in candidate)>=sum(values[i] for i in incumbent):
            incumbent=candidate;source='milp'
    checked=assigned_risk_bounds(incumbent,matrix,n)
    if any(checked[i]>limits[i]+1e-7 for i in incumbent):
        raise RuntimeError('Allocation failed the independent risk-budget check')
    value=float(sum(values[i] for i in incumbent))
    bound=getattr(result,'mip_dual_bound',None)
    upper_bound=max(value,-float(bound)) if bound is not None and np.isfinite(bound) else None
    proven=result.status==0 and source=='milp'
    gap=max(0.,(upper_bound-value)/max(abs(value),1e-10)) if upper_bound is not None else None
    return {'selected':sorted(incumbent),'assignments':incumbent,
        'windows':[(r.start,r.end) for r in reservations],
        'status':'optimal' if proven else 'feasible_time_limit', 'optimal':proven,'gap':gap,
        'runtime_ms':(time.perf_counter()-started)*1000,'objective_value':value,
        'objective_upper_bound':upper_bound,'solution_source':source,
        'risk_constraint_verified':True,'variables':variable_count,'constraints':len(upper),
        'omitted_pair_mass_max':float(omitted.max()),'solver_message':str(result.message)}
