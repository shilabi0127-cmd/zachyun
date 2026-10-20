"""Interval-capacity MILP selection followed by feasible interval coloring."""
import heapq
import math
import time
from statistics import NormalDist

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csc_array
from .risk import tolerance, marginal_quantile


def protected_windows(reservations, risk_budget=.1, buffered=False, distribution='normal', fixed_buffer=None):
    result = []
    for r in reservations:
        if fixed_buffer is not None:
            early = late = fixed_buffer
        elif buffered:
            alpha = tolerance(r,risk_budget)
            early = max(0., -marginal_quantile(r.arrival_mean,r.arrival_std,alpha/2,distribution))
            late = max(0., marginal_quantile(r.departure_mean,r.departure_std,1-alpha/2,distribution))
        else:
            early = late = 0.
        result.append((r.start - early, r.end + late))
    return result


def color_intervals(selected, windows, slots):
    """Assign selected intervals to identical bays; half-open endpoint semantics."""
    free = list(range(1, slots + 1))
    heapq.heapify(free)
    occupied = []
    assignments = {}
    for i in sorted(selected, key=lambda i: (windows[i][0], windows[i][1], i)):
        start, end = windows[i]
        while occupied and occupied[0][0] <= start + 1e-8:
            _, bay = heapq.heappop(occupied)
            heapq.heappush(free, bay)
        if not free:
            raise RuntimeError("求解结果违反泊位容量约束")
        bay = heapq.heappop(free)
        assignments[i] = bay
        heapq.heappush(occupied, (end, bay))
    return assignments


def greedy(reservations, slots):
    started = time.perf_counter()
    windows = protected_windows(reservations)
    assignments = {}
    # Missing booking_order uses CSV row order. Do not confuse booking with arrival order.
    for i in sorted(range(len(reservations)),key=lambda i:(
            reservations[i].booking_order if reservations[i].booking_order is not None else i,i)):
        start,end=windows[i]
        for bay in range(1,slots+1):
            if all(assignments[j]!=bay or end<=windows[j][0] or windows[j][1]<=start for j in assignments):
                assignments[i]=bay
                break
    return {"selected": sorted(assignments), "assignments": assignments,
            "windows": windows, "status": "heuristic", "optimal": False,
            "gap": None, "runtime_ms": (time.perf_counter()-started)*1000}


def optimize(reservations, config, buffered=False, fixed_buffer=None):
    started = time.perf_counter()
    n = len(reservations)
    windows = protected_windows(reservations, config.risk_budget, buffered,
                                config.deviation_distribution,fixed_buffer)
    starts, ends = np.asarray(windows, dtype=float).T
    times = np.unique(starts)
    # Every maximum occupancy occurs at a start event. Ends are excluded.
    occupancy = (starts[None, :] <= times[:, None]) & (ends[None, :] > times[:, None])
    values = np.asarray([r.priority if config.objective == "weighted_admission" else r.fee
                         for r in reservations], dtype=float)
    result = milp(c=-values, integrality=np.ones(n), bounds=Bounds(np.zeros(n), np.ones(n)),
                  constraints=LinearConstraint(csc_array(occupancy.astype(float)),
                                               np.full(len(times), -np.inf),
                                               np.full(len(times), config.slots)),
                  options={"time_limit": config.time_limit, "mip_rel_gap": 0.})
    if result.x is None:
        raise RuntimeError("求解器未返回可行解 " + str(result.message))
    selected = np.flatnonzero(result.x > .5).tolist()
    assignments = color_intervals(selected, windows, config.slots)
    gap = getattr(result, "mip_gap", None)
    return {"selected": selected, "assignments": assignments, "windows": windows,
            "status": "optimal" if result.status == 0 else "feasible_time_limit",
            "optimal": result.status == 0,
            "gap": None if gap is None or not math.isfinite(gap) else float(gap),
            "runtime_ms": (time.perf_counter()-started)*1000}
