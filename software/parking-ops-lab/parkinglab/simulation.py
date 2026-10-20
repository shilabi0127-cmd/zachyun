"""Common-random-number comparisons with trial-level concentration bounds."""
import hashlib
import json
import math
import time
import platform

import numpy as np
import scipy

from .optimizer import greedy, optimize


def conflict_mask(starts, ends):
    """Per-request conflicts for many trials in one bay, O(T*n*log(n))."""
    order = np.argsort(starts, axis=1, kind="stable")
    ss = np.take_along_axis(starts, order, axis=1)
    ee = np.take_along_axis(ends, order, axis=1)
    bad = np.zeros_like(ss, dtype=bool)
    if ss.shape[1] > 1:
        previous_max = np.maximum.accumulate(ee, axis=1)
        bad[:, 1:] |= ss[:, 1:] < previous_max[:, :-1]
        bad[:, :-1] |= ss[:, 1:] < ee[:, :-1]
    # Invert the sorting permutation so columns match the input request order.
    original = np.empty_like(bad)
    np.put_along_axis(original, order, bad, axis=1)
    return original


def evaluate(reservations, config, solution, actual_starts, actual_ends):
    n = len(reservations)
    ids = solution["selected"]
    conflicts = np.zeros((config.trials, n), dtype=bool)
    for bay in range(1, config.slots+1):
        indices = [i for i in ids if solution["assignments"][i] == bay]
        if indices:
            conflicts[:, indices] = conflict_mask(actual_starts[:, indices], actual_ends[:, indices])
    accepted = len(ids)
    per_trial = conflicts.sum(axis=1) / accepted if accepted else None
    rate = None if per_trial is None else float(np.mean(per_trial))
    # Trials are independent, requests within each trial may be dependent.
    epsilon = math.sqrt(math.log(40) / (2 * config.trials))
    bound = None if rate is None else [max(0., rate-epsilon), min(1., rate+epsilon)]
    priority_ids = [i for i,r in enumerate(reservations) if r.priority >= 3]
    priority_admitted = sum(i in ids for i in priority_ids)
    horizon = max(r.end for r in reservations)-min(r.start for r in reservations)
    return {
        "accepted": accepted, "total": n, "acceptance_rate": accepted/n,
        "accepted_weight": sum(reservations[i].priority for i in ids),
        "revenue": round(sum(reservations[i].fee for i in ids), 2),
        "priority_accepted": priority_admitted, "priority_total": len(priority_ids),
        "priority_acceptance_rate": priority_admitted/len(priority_ids) if priority_ids else None,
        "conflict_rate": rate, "mc_95_bound": bound,
        "any_conflict_trial_rate": float(np.mean(conflicts.any(axis=1))),
        "nominal_utilization": sum(reservations[i].end-reservations[i].start for i in ids)/(config.slots*horizon),
        "solver_status": solution["status"], "optimal": solution["optimal"],
        "mip_gap": solution["gap"], "solver_runtime_ms": round(solution["runtime_ms"], 3),
        "schedule": [{**r.model_dump(), "accepted": i in solution["assignments"],
                      "bay": solution["assignments"].get(i),
                      "protected_start": round(solution["windows"][i][0], 3),
                      "protected_end": round(solution["windows"][i][1], 3)} for i,r in enumerate(reservations)]}


def run_experiment(request):
    started = time.perf_counter()
    reservations, config = request.reservations, request.config
    rng = np.random.default_rng(config.seed)
    shape = (config.trials, len(reservations))
    starts = np.array([r.start for r in reservations])[None,:] + rng.normal(
        [r.arrival_mean for r in reservations], [r.arrival_std for r in reservations], size=shape)
    raw_ends = np.array([r.end for r in reservations])[None,:] + rng.normal(
        [r.departure_mean for r in reservations], [r.departure_std for r in reservations], size=shape)
    clamp_count = int(np.sum(raw_ends <= starts))
    ends = np.maximum(raw_ends, starts + .001)
    solutions = {"fcfs": greedy(reservations, config.slots),
                 "nominal_milp": optimize(reservations, config, False),
                 "buffered_milp": optimize(reservations, config, True)}
    policies = {key: evaluate(reservations, config, sol, starts, ends) for key,sol in solutions.items()}
    canonical = json.dumps(request.model_dump(), sort_keys=True, separators=(",", ":"))
    return {"scenario_hash": hashlib.sha256(canonical.encode()).hexdigest(),
            "scope": "User-defined or synthetic inputs; not a thesis replication or production deployment",
            "config": config.model_dump(), "request_count": len(reservations),
            "clamped_realizations": clamp_count,
            "versions": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
            "policies": policies, "total_runtime_ms": round((time.perf_counter()-started)*1000, 2)}


def deterministic_report(result):
    labels = {"fcfs":"先到先接纳", "nominal_milp":"名义时段整数规划", "buffered_milp":"风险缓冲整数规划"}
    lines = ["# 预约泊位策略实验报告", "", f"场景标识 `{result['scenario_hash']}`", "",
             f"输入 {result['request_count']} 条预约、{result['config']['slots']} 个同质泊位。",
             f"随机种子 {result['config']['seed']}，共同随机数仿真 {result['config']['trials']} 轮。", "",
             "| 策略 | 接纳 | 加权接纳 | 预约收入 | 冲突涉及率 |", "| --- | --- | --- | --- | --- |"]
    for key,r in result['policies'].items():
        rate = "无接纳请求" if r['conflict_rate'] is None else f"{r['conflict_rate']:.2%}"
        lines.append(f"| {labels[key]} | {r['accepted']}/{r['total']} | {r['accepted_weight']:.2f} | {r['revenue']:.2f} | {rate} |")
    lines += ["", "冲突涉及率统计同一泊位发生实际占用重叠的请求，每轮每个请求最多计一次。",
              "必须同时比较接纳、加权接纳、收入与冲突，不能仅凭较低冲突率认定策略全面更优。",
              "缓冲来自输入的正态时间偏差与分位数，是保守规划启发式，不是系统联合机会约束保证。",
              "模型使用同质泊位、固定预约区间，没有模拟冲突后的排队、重新分配或实际服务损失。",
              "95%界限基于独立仿真轮次的Hoeffding界限，仅表示蒙特卡洛抽样误差。",
              f"实际离场早于到达时执行最小时长修正，本次共 {result['clamped_realizations']} 次。",
              "所有软件实验结果与博士论文结果分别呈现。"]
    return "\n".join(lines)
