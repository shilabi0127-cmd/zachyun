# junction-agents

Constrained multi-agent signal control on a small queue network. Includes independent Q-learning, a joint rollout controller, pressure-based and fixed-time baselines, and a no-Q ablation.

Python 3.12 + NumPy. No simulator server or GPU is needed.

```bash
python -m pip install -r requirements.txt
python -m junction_agents train --episodes 600
python -m junction_agents evaluate --episodes 25
```

The trained Q table, training trace and full episode-level evaluation are committed in `examples/`. Re-running a command replaces its output file. Default training without `--episodes` uses 800 episodes; the committed run uses 600.

An optional [CEM sequence planner](docs/cem.md) adds vectorized candidate rollouts and warm-started sampling. Its fresh-seed comparison records control outcomes and per-decision latency separately from the original experiment.

```bash
python -m junction_agents.planner_benchmark --episodes 10
```

## Control problem

Four junctions form a 2×2 grid. Each junction has north/east/south/west approach queues and two signal phases, NS and EW. Vehicles continue straight, move to the downstream approach after service, and leave at the network boundary.

Boundary demand is Poisson with a mid-episode change in directional load. The arrival stream is sampled once per scenario. All controllers see the same stream for a given seed. Policies read current queues and phase state; they do not access future arrivals.

Constraints enforced by the environment and controller masks

- Minimum green of 2 steps, maximum green of 12 steps.
- One all-red step when a phase changes.
- Finite approach capacity and downstream storage checks before transfer.
- Only feasible actions enter greedy Q selection, TD bootstrap or joint search.

The maximum green bounds phase duration, not individual vehicle waiting time. Overflow means external arrivals refused at a full approach; it is reported alongside queue size and exits so that dropping demand is not mistaken for successful control.

## Controllers

| Policy | Decision |
| --- | --- |
| `fixed_time` | Change after six green steps, subject to the same masks |
| `max_pressure` | Switch when opposite-phase pressure improves by more than two, or when forced by maximum green |
| `independent_q` | Four separate tabular Q functions, neighborhood pressure observations and a shared network reward |
| `joint_q_coordinator` | Enumerate up to 16 feasible first actions, score three-step rollouts and add a learned Q-regret term |
| `joint_without_q` | Same rollout and constraints with the Q term removed |

The pressure baseline is a practical variant with hysteresis and clearance loss; no max-pressure stability theorem is claimed for this implementation. The learned policy is tabular IQL, not a deep-RL model.

For IQL, each junction observes binned NS/EW pressure, its current phase and switch eligibility. Pressure uses current local and adjacent queues. Training receives the shared scalar reward

```text
reward = -(total_queue + 5 * overflow + 0.25 * phase_changes) / 16
```

The rollout controller optimizes only its first joint action. Subsequent simulated actions hold the chosen phase unless maximum green forces a change. The model assumes zero new arrivals over the short rollout. It minimizes discounted quadratic queue potential, blocking and switching costs, with a throughput credit and a Q-regret penalty. See [`docs/design.md`](docs/design.md) for the exact objective and the initial failure case.

This is an experimental controller composition. It is not a new algorithm with a convergence or optimality proof.

## Recorded evaluation

Training uses environment seeds 0–599 and 96-step episodes. Development scenarios 50000–50024 exposed the myopic rollout issue. Final evaluation uses fresh seeds **60000–60024**, 120 steps and two demand levels. The Q table is frozen during evaluation.

Mean episode metrics, rounded here; smaller queues and overflow are preferable, more exits are preferable

| Demand | Controller | Avg queued vehicles | Exits | Overflow |
| --- | --- | ---: | ---: | ---: |
| Regular | Fixed time | 60.35 | 596.44 | 10.92 |
| Regular | Pressure | 61.63 | 607.72 | 0.52 |
| Regular | Independent Q | 73.14 | 537.64 | 26.80 |
| Regular | Joint rollout + Q | 40.90 | 639.16 | 0.00 |
| Regular | Joint rollout without Q | 40.84 | 638.68 | 0.00 |
| Higher | Fixed time | 125.45 | 739.84 | 283.00 |
| Higher | Pressure | 164.59 | 679.96 | 273.04 |
| Higher | Independent Q | 176.20 | 642.76 | 281.68 |
| Higher | Joint rollout + Q | 144.66 | 808.44 | 165.68 |
| Higher | Joint rollout without Q | 143.73 | 809.40 | 167.52 |

The model-based joint rollout helps in these scenarios. **The ablation does not establish an additional queue-reduction benefit from the learned Q term.** At higher demand, fixed time has a smaller mean queue than the joint controller but admits less traffic through the network and loses more arrivals. No single queue metric settles that trade-off.

[`examples/evaluation.json`](examples/evaluation.json) includes each seed, paired queue differences against pressure control and their standard errors. These summarize variation across this small synthetic set, not a city deployment or general traffic-control benchmark. Training/evaluation lengths also differ; the evaluation runs longer than training episodes.

## Checks

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests cover vehicle conservation, capacity bounds, all-red timing, minimum/maximum green, downstream blocking, action masks in learning targets, non-mutating lookahead, no access to future arrivals, seed reproducibility and train/test separation.

## Limits

This is a mesoscopic queue toy model with straight-through vehicles, deterministic saturation service and no lane changes, turn movements, pedestrians or calibrated travel times. A step has no asserted real-world duration. Queue area is measured in vehicle-steps, not observed travel delay. Downstream space is checked before simultaneous discharge, a conservative simplification.

Four agents with binary actions permit exhaustive first-action search. That search scales exponentially with the number of agents; this implementation does not solve large networks. Discretized local observations are partially observed and nonstationary during independent learning, so ordinary single-agent Q-learning guarantees do not apply.

Before using the idea in traffic engineering, replace the model with a calibrated simulator and validate demand, phase conflicts, safety constraints and performance on independent scenarios.
