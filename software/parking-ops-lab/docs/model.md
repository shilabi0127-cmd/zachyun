# Risk and assignment model

## Endpoint distributions

For request i, the random arrival is A_i = s_i + X_i and raw departure is D_i = e_i + Y_i. X_i and Y_i have supplied mean/std and are mutually independent across all requests and endpoints. Normal or bounded uniform deviations are supported. Uniform bounds are mean ± √3 × std.

For two independent endpoints U and V, P(U > V) is computed from the normal difference distribution or the exact trapezoidal distribution of the difference of two uniforms. Zero-variance endpoints use a strict comparison, so deterministic touching intervals do not conflict.

## Pair overlap and invalid-duration repair

Raw interval overlap is the event A_i < D_j and A_j < D_i. These two comparisons involve disjoint endpoint variables under the independence assumption, giving

```text
p_raw(i,j) = P(D_i > A_j) * P(D_j > A_i)
```

Normal distributions are unbounded and can generate a departure before arrival. Simulation repairs departure to E_i = max(D_i, A_i + ε), with ε = 0.001 minute. Ignoring this repair in the risk calculation would understate risk for short or highly uncertain bookings. Let c_i = P(A_i + ε > D_i). Outside either repair event, the raw and repaired intervals coincide, so

```text
p_overlap(i,j) <= p_upper(i,j)
p_upper(i,j) = min(1, p_raw(i,j) + c_i + c_j)
```

This is a conservative union bound, not an assertion that the repaired-interval probability equals the raw formula. A high repair probability is a warning that the endpoint model is poorly suited to the booking duration; no attempt is made to hide it. The report records the maximum repair probability and the actual number of sampled repairs.

## Per-request service budget

For request i sharing a bay with a set of admitted requests B_i, union bounding gives

```text
P(request i overlaps any other admitted request on its bay)
    <= min(1, sum[p_upper(i,j) for j in B_i])
```

The risk allocator keeps that sum at or below alpha_i. A CSV-supplied `failure_tolerance` is used directly. Otherwise alpha_i = config.risk_budget / sqrt(priority_i). This default mapping is an explicit policy assumption, not an empirically estimated customer preference.

The guarantee is conditional on independent, correctly specified endpoint distributions. It is not a guarantee for the system-wide probability of any conflict, and does not account for distribution estimation errors or correlated late departures. Baseline policies are evaluated against the same budgets but do not enforce them.

## MILP

Let x_ib be binary, indicating admission of request i on bay b. Each request has sum_b x_ib <= 1. Its weight v_i is priority or booked fee, depending on the selected objective.

For a pair with p_upper(i,j) greater than min(alpha_i,alpha_j), coassignment is impossible, so x_ib + x_jb <= 1 on every bay. Other non-negligible pairs get one continuous variable z_ij in [0,1], with

```text
x_ib + x_jb - z_ij <= 1       for every bay b
sum_j p_upper(i,j) * z_ij <= alpha_i - reserve_i
maximize sum_i sum_b v_i * x_ib
```

Whenever two integer assignments share a bay, their z must be one. All z have nonnegative coefficients in risk constraints and no objective reward, so z can be zero for non-coassigned pairs. Making these auxiliary variables continuous therefore does not weaken feasibility for integer assignments.

Coefficients at most 1e-8 are omitted from pair constraints to avoid ineffective numerical coefficients. Their entire per-request mass, even for rejected or differently assigned requests, is reserved on the risk RHS. This is conservative. The returned assignment is independently checked against the full, unpruned pair matrix with 1e-7 numerical tolerance.

Identical-bay symmetry is reduced by requiring bay occupancy counts to be nonincreasing. This preserves at least one relabeling of each feasible allocation. Sparse constraint matrices avoid an all-dense bay/pair tensor.

## Solver limits and verified fallback

SciPy calls HiGHS with a configurable solver time limit. The timer reported by this project also includes Python model construction and post-solve checks. A time-limited incumbent is labeled feasible, not optimal.

A deterministic greedy allocation is constructed before the solve. It checks each new request's budget and all already assigned peers' updated budgets, reserving the omitted mass as well. If the solver returns no incumbent or a worse verified solution, this allocation is retained and labeled `verified_greedy_fallback`. It is not called a MILP optimum. Solver errors other than a normal limit are surfaced rather than disguised as a successful solve.

The reported `objective_upper_bound` converts the solver's minimization dual bound to a maximization upper bound for this conservative formulation. `mip_gap` is recalculated against the actually returned allocation. When no valid dual bound exists, it is null. The upper bound does not establish the optimum of a less conservative true joint chance-constrained problem. Different baseline models have different feasible sets, so their objective values are not interchangeable optimality bounds.

## Buffers and advice

Fixed buffers expand both ends by a configured number of minutes. Marginal quantile windows use alpha_i/2 on each endpoint; they are not the new all-pairs risk budget.

The risk MILP directly chooses bay combinations without expanding a protected interval. For explanation, consecutive nominal orders on each selected bay also receive a directional gap recommendation. It solves P(Y_i - X_j > gap) <= min(alpha_i,alpha_j). Normal differences use their inverse CDF; uniform differences use a scalar root on the exact CDF. This diagnostic concerns one late-departure/early-arrival event only. It does not modify start times, allocate both-sided buffers, or certify a full bay schedule.

## Independent simulation

All policies use the same sampled endpoint deviations for a given instance. The planning risk matrix is analytic; simulation outcomes are sampled separately and are never fed into optimization. A booking is counted once per trial if it overlaps any other accepted booking on the same bay. The denominator is accepted bookings. Each policy retains its admission count, booked fees and priority acceptance, so refusing more orders cannot be hidden behind a lower conflict rate.

Observed per-order Monte Carlo frequencies can exceed an analytic bound by sampling noise. A 95% Hoeffding interval is reported for the trial-level average involvement rate; it covers sampling error only. No individual-order confidence claim or causal claim is made. Actual conflict resolution, waiting, reallocation, refunds and net profit are outside the model.
