"""Common-random-number comparisons with trial-level concentration bounds."""
import hashlib
import json
import math
import time
import platform

import numpy as np
import scipy

from .optimizer import greedy, optimize
from .allocation import optimize_risk
from .risk import MIN_DURATION, assigned_risk_bounds, recommended_gap, risk_matrix, tolerance

POLICY_LABELS = {'fcfs':'先到先得', 'nominal_milp':'名义时段分配',
                 'fixed_buffer_milp':'固定缓冲分配', 'buffered_milp':'分位数缓冲分配',
                 'risk_milp':'逐用户风险约束分配'}


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


def evaluate(reservations, config, solution, actual_starts, actual_ends, risks=None):
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
    result = {
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
        'objective_value': solution.get('objective_value'),
        'objective_upper_bound': solution.get('objective_upper_bound'),
        'solution_source': solution.get('solution_source','interval_selection'),
        'risk_constraint_verified':solution.get('risk_constraint_verified',False),
        'model_variables':solution.get('variables'), 'model_constraints':solution.get('constraints'),
        'expected_conflict_free_booking_fees':float(np.mean(np.sum(
            (~conflicts[:,ids])*np.array([reservations[i].fee for i in ids])[None,:],axis=1))) if ids else 0.,
        "schedule": [{**r.model_dump(), "accepted": i in solution["assignments"],
                      "bay": solution["assignments"].get(i),
                      "protected_start": round(solution["windows"][i][0], 3),
                      "protected_end": round(solution["windows"][i][1], 3),
                      'early_buffer_minutes':round(max(0,r.start-solution['windows'][i][0]),3),
                      'late_buffer_minutes':round(max(0,solution['windows'][i][1]-r.end),3),
                      'failure_tolerance':tolerance(r,config.risk_budget),
                      'observed_conflict_rate':float(conflicts[:,i].mean()) if i in solution['assignments'] else None,
                      'decision':'accepted' if i in solution['assignments'] else 'not_selected_by_policy'} for i,r in enumerate(reservations)]}
    if risks is not None:
        bounds=assigned_risk_bounds(solution['assignments'],risks['upper'],n)
        for i,row in enumerate(result['schedule']):
            row['conflict_probability_upper_bound']=float(bounds[i]) if row['accepted'] else None
        pairs=[];buffers=[]
        for bay in range(1,config.slots+1):
            peers=sorted([i for i in ids if solution['assignments'][i]==bay],key=lambda i:(reservations[i].start,i))
            for pos,i in enumerate(peers):
                for j in peers[pos+1:]:
                    pairs.append({'first':reservations[i].id,'second':reservations[j].id,'bay':bay,
                        'raw_overlap_probability':float(risks['raw'][i,j]),
                        'overlap_probability_upper_bound':float(risks['upper'][i,j])})
            for i,j in zip(peers,peers[1:]):
                a,b=reservations[i],reservations[j]
                alpha=min(tolerance(a,config.risk_budget),tolerance(b,config.risk_budget))
                gap=recommended_gap(a,b,alpha,config.deviation_distribution)
                actual=b.start-a.end
                buffers.append({'bay':bay,'previous':a.id,'following':b.id,
                    'scheduled_gap_minutes':actual,'suggested_directional_gap_minutes':gap,
                    'additional_gap_minutes':max(0.,gap-actual),'directional_failure_tolerance':alpha})
        pairs.sort(key=lambda r:-r['overlap_probability_upper_bound'])
        result['risk_pairs']=pairs[:50];result['same_bay_pair_count']=len(pairs)
        result['buffer_recommendations']=buffers
        result['max_request_risk_upper_bound']=float(max((bounds[i] for i in ids),default=0.)) if ids else None
        result['requests_over_risk_budget']=int(sum(bounds[i]>tolerance(reservations[i],config.risk_budget)+1e-7 for i in ids))
    return result


def run_experiment(request):
    started = time.perf_counter()
    reservations, config = request.reservations, request.config
    rng = np.random.default_rng(config.seed)
    shape = (config.trials, len(reservations))
    def deviations(mean,std):
        if config.deviation_distribution=='normal':
            return rng.normal(mean,std,size=shape)
        return np.asarray(mean)+rng.uniform(-math.sqrt(3),math.sqrt(3),size=shape)*np.asarray(std)
    starts = np.array([r.start for r in reservations])[None,:] + deviations(
        [r.arrival_mean for r in reservations], [r.arrival_std for r in reservations])
    raw_ends = np.array([r.end for r in reservations])[None,:] + deviations(
        [r.departure_mean for r in reservations], [r.departure_std for r in reservations])
    clamp_count = int(np.sum(raw_ends < starts+MIN_DURATION))
    ends = np.maximum(raw_ends, starts + MIN_DURATION)
    risks=risk_matrix(reservations,config.deviation_distribution)
    solutions = {"fcfs": greedy(reservations, config.slots),
                 "nominal_milp": optimize(reservations, config, False),
                 'fixed_buffer_milp':optimize(reservations,config,fixed_buffer=config.fixed_buffer_minutes),
                 "buffered_milp": optimize(reservations, config, True),
                 'risk_milp':optimize_risk(reservations,config,risks)}
    policies = {key: evaluate(reservations, config, sol, starts, ends,risks) for key,sol in solutions.items()}
    canonical = json.dumps(request.model_dump(), sort_keys=True, separators=(",", ":"))
    return {"scenario_hash": hashlib.sha256(canonical.encode()).hexdigest(),
            "scope": "User-defined or synthetic inputs; not a thesis replication or production deployment",
            "config": config.model_dump(), "request_count": len(reservations),
            'input_reservations':[r.model_dump() for r in reservations],
            'risk_model':{'endpoint_independence':True,'distribution':config.deviation_distribution,
                'maximum_interval_repair_probability':float(risks['repair_probability'].max()),
                'guarantee':'Per-request union bound under supplied distributions; not a system-wide or field guarantee'},
            "clamped_realizations": clamp_count,
            "versions": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
            "policies": policies, "total_runtime_ms": round((time.perf_counter()-started)*1000, 2)}


def deterministic_report(result):
    labels = POLICY_LABELS
    lines = ["# 预约泊位策略实验报告", "", f"场景标识 `{result['scenario_hash']}`", "",
             f"输入 {result['request_count']} 条预约、{result['config']['slots']} 个同质泊位。",
             f"随机种子 {result['config']['seed']}，共同随机数仿真 {result['config']['trials']} 轮。", "",
             "| 策略 | 接纳 | 加权接纳 | 预约收入 | 冲突涉及率 |", "| --- | --- | --- | --- | --- |"]
    for key,r in result['policies'].items():
        rate = "无接纳请求" if r['conflict_rate'] is None else f"{r['conflict_rate']:.2%}"
        lines.append(f"| {labels[key]} | {r['accepted']}/{r['total']} | {r['accepted_weight']:.2f} | {r['revenue']:.2f} | {rate} |")
    lines += ["", "冲突涉及率统计同一泊位发生实际占用重叠的请求，每轮每个请求最多计一次。",
              "必须同时比较接纳、加权接纳、收入与冲突，不能仅凭较低冲突率认定策略全面更优。",
              "分位数缓冲控制边际窗口；风险约束分配限制每位用户与同泊位全部其他预约的冲突概率上界之和。",
              "风险上界以输入的独立到离场分布为前提，不是系统整体无冲突保证，也不覆盖分布估计错误。",
              "固定缓冲对每条订单前后各预留配置的分钟数；相邻订单之间的总间隔可能为其两倍。",
              "逐对间隔建议仅针对相邻两单的晚离与早到事件，不能替代完整的逐用户风险约束。",
              "预约收入是已接纳订单费用，不是净利润。无冲突费用期望也未建模退款、补偿或冲突后的服务恢复。",
              "模型使用同质泊位、固定预约区间，没有模拟冲突后的排队、重新分配或实际服务损失。",
              "95%界限基于独立仿真轮次的Hoeffding界限，仅表示蒙特卡洛抽样误差。",
              f"实际离场早于到达时执行最小时长修正，本次共 {result['clamped_realizations']} 次。",
              "所有软件实验结果与博士论文结果分别呈现。"]
    return "\n".join(lines)
