# Sampling joint action sequences

`cem.py` adds a discrete cross-entropy planner. It searches sequences of four-agent binary decisions rather than only a first joint action. It uses the same queue model, clearance loss, storage constraints and stage cost as the existing rollout controller.

## Procedure

The default budget is a horizon of 5, a population of 32, 6 elites and 3 iterations.

1. Seed the search with the existing no-Q joint controller's first decision and future holds.
2. Sample Bernoulli action sequences from a time-by-agent probability table.
3. Advance all candidates in a vectorized model. Repair each candidate's requested action using that candidate's evolving minimum/maximum-green mask.
4. Rank feasible executed sequences by discounted queue, blocking, switching and exit cost.
5. Update the Bernoulli table toward elite executed actions, with smoothing and a probability floor.
6. Retain the best evaluated plan, execute its first action and shift the distribution for the next decision.

The incumbent is retained across iterations. The selected plan therefore has no greater **predicted cost under this model** than the seed plan. It does not guarantee better real episode outcomes: new arrivals occur after planning, and the planner currently forecasts zero arrivals.

Warm starts are per planner instance. The benchmark constructs a new planner for each scenario. Reusing a planner across unrelated episodes also reuses its warm-start state; construct a new instance to reset it.

## Implementation checks

The batched rollout is checked against repeated calls to the scalar environment on randomized states and plans. Tests compare executed actions, predicted queues and cost, in addition to feasibility, state preservation, fixed-seed repeatability and independence from future arrivals.

`last_diagnostics` reports the seed/selected costs, repaired sample actions, planning time and transition-evaluation count. The count includes the seed controller's search; vectorizing many transitions does not make their computational cost zero.

## Separate evaluation

```bash
python -m junction_agents.planner_benchmark --episodes 10
```

The committed run uses fresh scenario seeds 70000–70009. Four policies share the same arrival stream for each scenario, under regular and higher demand. These are separate from the earlier 60000–60024 result table. CEM sampling uses a scenario-derived seed, separately from the arrival generator.

Mean episode outcomes and decision-time p95 from one Windows/Python run

| Demand | Policy | Avg queued | Exits | Overflow | Decision p95 ms |
| --- | --- | ---: | ---: | ---: | ---: |
| Regular | Joint rollout | 42.47 | 646.6 | 0.0 | 2.77 |
| Regular | CEM | 43.15 | 647.5 | 0.0 | 6.33 |
| Higher | Joint rollout | 142.97 | 808.1 | 173.7 | 2.38 |
| Higher | CEM | 142.57 | 810.9 | 175.7 | 5.35 |

The small differences do not establish a stable control benefit over the simpler joint controller. Higher-demand CEM slightly increases exits and also loses slightly more arrivals. It uses more computation. The default experiment therefore stays with the existing joint controller; CEM is an optional research backend.

Full results, paired episode differences and per-decision latency samples are in `examples/cem-evaluation.json`. Timing is a single-machine observation, not a deployment deadline guarantee. The comparison changes the horizon and search budget together, so it cannot isolate the effect of sampling alone.

## Relation to prior work

CEM is an established planning method. [Pinneri et al., Sample-efficient Cross-Entropy Method for Real-time Planning](https://arxiv.org/abs/2008.06389) discusses sampling efficiency, temporal structure and memory in planning. This implementation uses discrete Bernoulli sequences with deterministic feasibility repair. It does not reproduce that paper's iCEM algorithm or claim its performance improvements.
