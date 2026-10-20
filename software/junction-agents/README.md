# junction-agents

Multi-agent signal control with a small queue model and an actual SUMO/TraCI backend. Controllers share a constrained action interface; the simulator comparison tests whether queue-model behavior survives microscopic vehicle dynamics.

## Run SUMO

Python 3.12. The pinned SUMO wheel includes the simulator and network converter; no external server or GPU is required.

```bash
python -m pip install -r requirements-sumo.txt
python -m junction_agents.sumo_benchmark
```

This runs the frozen 90-episode protocol and writes `report.json`, `summary.csv` and per-run logs under `.sumo/validation/`. For an installation check, `--episodes 1` runs 18 episodes using the first seed; it is a subset, not a replacement for the full evaluation.

## Recorded SUMO comparison

Mean total halted vehicles on the 16 incoming approach lanes over a fixed 900-second horizon. Lower is better. Each cell averages five paired seeds.

| Controller | Tidal regular | Tidal heavy | Long asymmetric |
| --- | ---: | ---: | ---: |
| Fixed time | 13.51 | 31.75 | 21.65 |
| SUMO actuated | 6.18 | 15.76 | 5.84 |
| Pressure heuristic | 8.59 | 22.16 | 10.10 |
| Joint rollout, no Q | 10.19 | 24.66 | 10.12 |
| CEM sequence planner | 10.35 | 25.86 | 9.82 |
| Queue-trained IQL, zero-shot | 14.16 | 37.23 | 16.07 |

All scheduled vehicles completed in these 90 runs. The recorded checks found no signal-timing violations, collision vehicle reports or teleport starts. These checks concern the specified straight-through synthetic scenarios; they are not a safety certification.

**Native SUMO actuated control is strongest here.** Joint rollout and CEM improve over fixed time, but do not beat this stronger baseline. Queue-trained IQL transfers poorly. The queue surrogate observes halted vehicles, omits approaching moving vehicles and uses an uncalibrated discharge approximation; more planning does not remove that mismatch.

[Full method and limitations](docs/sumo.md) · [Per-seed report](examples/sumo-validation.json) · [CSV summary](examples/sumo-summary.csv) · [Example decisions and observed signal audit](examples/sumo-sample)

## Implementation

- [`sumo_scenarios.py`](junction_agents/sumo_scenarios.py) builds 250 m and 380 m grids and seeded boundary demand. Policies receive identical route schedules.
- [`sumo_backend.py`](junction_agents/sumo_backend.py) reads actual lane states and executes five-second control intervals through TraCI.
- [`sumo_signals.py`](junction_agents/sumo_signals.py) checks observed signal transitions, including the simulator-native baseline. Green durations are 10–60 seconds, with 3 seconds yellow and 2 seconds all-red.
- [`sumo_benchmark.py`](junction_agents/sumo_benchmark.py) records input hashes, complete vehicle accounting, paired differences and planning latency.
- [`policies.py`](junction_agents/policies.py) and [`cem.py`](junction_agents/cem.py) implement constrained joint search, tabular independent Q-learning and CEM. No deep-RL claim is made.

The [queue experiment](docs/queue-model.md) remains a separate, fast environment for training and ablation. Its queue-area gains are not SUMO travel-delay gains. See [controller design](docs/design.md) and [CEM experiments](docs/cem.md).

## Tests

```bash
python -m pip install -r requirements-dev.txt -r requirements-sumo.txt
python -m pytest -q
```

Pure tests run by default. Enable the five actual-SUMO integration cases with `RUN_SUMO_TESTS=1` in your environment. In PowerShell use `$env:RUN_SUMO_TESTS='1'`; on Linux/macOS use `RUN_SUMO_TESTS=1 python -m pytest -q`. The dedicated [CI workflow](../../.github/workflows/sumo-integration.yml) installs and launches SUMO on Linux.
