"""Independent-endpoint overlap probabilities and conservative repair allowance.

Units are minutes. Uniform and normal inputs share the same mean/std parameters.
The raw-overlap events use disjoint endpoint variables, so their probabilities
multiply. Repaired intervals add a union-bound allowance for invalid raw durations.
"""
import math
from statistics import NormalDist

import numpy as np
from scipy.optimize import brentq
from scipy.special import ndtr

MIN_DURATION = .001


def tolerance(reservation, default):
    if reservation.failure_tolerance is not None:
        return reservation.failure_tolerance
    return default / math.sqrt(reservation.priority)


def difference_positive(mean_a, std_a, mean_b, std_b, distribution='normal'):
    """P(A > B), including deterministic endpoints and strict touching semantics."""
    delta = mean_a - mean_b
    if std_a == 0 and std_b == 0:
        return float(delta > 0)
    if distribution == 'normal':
        return float(ndtr(delta / math.hypot(std_a, std_b)))
    if distribution != 'uniform':
        raise ValueError('Unsupported deviation distribution')
    # Centered uniform widths are sqrt(12)*std. Sum of two uniforms is trapezoidal.
    a, b = sorted([math.sqrt(12)*std_a, math.sqrt(12)*std_b], reverse=True)
    x = delta + (a+b)/2
    if x <= 0:
        return 0.
    if x >= a+b:
        return 1.
    if b == 0:
        return x/a
    if x < b:
        return x*x/(2*a*b)
    if x <= a:
        return (x-b/2)/a
    return 1-(a+b-x)**2/(2*a*b)


def marginal_quantile(mean, std, probability, distribution='normal'):
    if distribution == 'normal':
        return mean + std*NormalDist().inv_cdf(probability)
    if distribution == 'uniform':
        return mean + math.sqrt(3)*std*(2*probability-1)
    raise ValueError('Unsupported deviation distribution')


def risk_matrix(reservations, distribution='normal'):
    n = len(reservations)
    raw = np.zeros((n,n))
    repair = np.array([difference_positive(
        r.start+r.arrival_mean+MIN_DURATION, r.arrival_std,
        r.end+r.departure_mean, r.departure_std, distribution) for r in reservations])
    for i, a in enumerate(reservations):
        for j in range(i+1,n):
            b = reservations[j]
            forward = difference_positive(a.end+a.departure_mean,a.departure_std,
                                          b.start+b.arrival_mean,b.arrival_std,distribution)
            reverse = difference_positive(b.end+b.departure_mean,b.departure_std,
                                          a.start+a.arrival_mean,a.arrival_std,distribution)
            raw[i,j] = raw[j,i] = forward*reverse
    bound = np.minimum(1, raw+repair[:,None]+repair[None,:])
    np.fill_diagonal(bound,0)
    return {'raw':raw,'upper':bound,'repair_probability':repair}


def assigned_risk_bounds(assignments, matrix, n):
    values = np.zeros(n)
    ids = list(assignments)
    for pos,i in enumerate(ids):
        for j in ids[pos+1:]:
            if assignments[i] == assignments[j]:
                values[i] += matrix[i,j]
                values[j] += matrix[i,j]
    return np.minimum(1,values)


def recommended_gap(previous, following, alpha, distribution='normal'):
    """Gap covering a directional late-departure/early-arrival event, not a bay-wide guarantee."""
    mean = previous.departure_mean-following.arrival_mean
    a,b = previous.departure_std,following.arrival_std
    if a == 0 and b == 0:
        return max(0.,mean)
    if distribution == 'normal':
        return max(0.,mean+NormalDist().inv_cdf(1-alpha)*math.hypot(a,b))
    width = math.sqrt(3)*(a+b)
    root = brentq(lambda gap: difference_positive(mean,a,gap,b,'uniform')-alpha,
                  mean-width,mean+width)
    return max(0.,float(root))
