"""Interval-capacity MILP selection followed by feasible interval coloring."""
import heapq
import math
import time
from statistics import NormalDist

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csc_array


def protected_windows(reservations, risk_budget=.1, buffered=False):
    result = []
    for r in reservations:
        if buffered:
            alpha = risk_budget / math.sqrt(r.priority)
            z = NormalDist().inv_cdf(1 - alpha / 2)
            early = max(0., z * r.arrival_std - r.arrival_mean)
            late = max(0., r.departure_mean + z * r.departure_std)
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
    occupied, selected = [], []
    for i in sorted(range(len(reservations)), key=lambda i: (windows[i][0], i)):
        while occupied and occupied[0] <= windows[i][0]:
            heapq.heappop(occupied)
        if len(occupied) < slots:
            selected.append(i)
            heapq.heappush(occupied, windows[i][1])
    return {"selected": selected, "assignments": color_intervals(selected, windows, slots),
            "windows": windows, "status": "heuristic", "optimal": False,
            "gap": None, "runtime_ms": (time.perf_counter()-started)*1000}


def optimize(reservations, config, buffered=False):
    started = time.perf_counter()
    n = len(reservations)
    windows = protected_windows(reservations, config.risk_budget, buffered)
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
