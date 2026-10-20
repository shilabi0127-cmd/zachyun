# parking-ops-lab

Batch reservation allocation with uncertain arrival/departure times. Import orders, choose a service-risk budget, assign bays and inspect the admission/risk/fee trade-off in a browser.

The core extension is a bay-assignment MILP that limits each admitted request's union bound on overlap with all other bookings sharing its bay. It compares that allocation with FCFS, nominal intervals, fixed buffers and marginal quantile buffers.

## Run

Python 3.12.

```bash
python -m pip install -r requirements.txt
python -m uvicorn parkinglab.api:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Windows users can run `start.bat`. The browser can generate sample orders, import CSV, set bay count, distribution, fixed-buffer length, service tolerance, objective and solve limit. The distribution panel can overwrite all loaded orders' deviation parameters explicitly; importing heterogeneous CSV does not silently overwrite them.

The result contains an admission decision for every order, its bay, planned buffers, allowed failure probability, model risk upper bound and simulated conflict frequency. Separate tables rank high-risk pairs and diagnose missing inter-booking gaps. Exports include schedule CSV, pair-risk CSV, gap recommendations, a full JSON record and Markdown report.

![Browser result](docs/dashboard.png)

## Input

```csv
id,start,end,fee,priority,arrival_mean,arrival_std,departure_mean,departure_std,failure_tolerance,booking_order
R001,08:00,09:00,10,4,-2,4,4,5,0.05,1
R002,09:20,10:00,8,1,-2,4,4,5,0.10,2
```

Only `id,start,end` are required. Times are minutes or `HH:MM` within one day. Endpoint deviations are in minutes; negative arrival mean means early arrival. Normal and uniform distributions share mean/std parameters; uniform support is mean ± √3 × std. All endpoints are assumed independent.

Priority is a supplied weight, not an inferred user value or a loyalty classifier. A request-specific `failure_tolerance` overrides the default `risk_budget / sqrt(priority)`. `booking_order` supplies FCFS submission order; missing values use input row index, so provide it consistently or leave it blank for all rows. Equal values retain row order. Limits are 300 orders, 20 identical bays, 3000 Monte Carlo trials and 20 solver seconds.

## Five policies

| Method | Allocation rule |
| --- | --- |
| FCFS | Process booking order, keep the first bay that can fit the nominal interval; no recoloring or displacement of prior assignments |
| Nominal MILP | Maximize priority-weighted admission or booked fees using scheduled intervals |
| Fixed-buffer MILP | Reserve the configured minutes before and after every interval |
| Quantile-buffer MILP | Expand individual intervals using their marginal arrival/departure quantiles |
| Risk-budget MILP | Assign requests directly to bays, with an all-pairs union-bound budget for each admitted request |

Fixed buffer is **per endpoint**: a five-minute early buffer and a five-minute late buffer require ten minutes between consecutive nominal intervals. Quantile buffers are a marginal-window heuristic. Risk budgets concern individual requests, not the probability that the entire parking lot is conflict-free. [Model equations, probability derivation and solver limits](docs/model.md) explain these distinctions.

## Recorded example

48 synthetic requests, four bays, normal deviations, 500 shared Monte Carlo trials, seed 20261020 and weighted-admission objective. These are software-example results, not thesis or field results.

| Method | Admitted | Weighted admissions | Booked fees | Simulated conflict involvement |
| --- | ---: | ---: | ---: | ---: |
| FCFS | 25/48 | 52 | 195.85 | 51.05% |
| Nominal intervals | 27/48 | 69 | 205.86 | 66.70% |
| Fixed buffers | 23/48 | 62 | 177.57 | 9.66% |
| Quantile buffers | 20/48 | 56 | 156.00 | 0.00% |
| Per-request risk budget | 23/48 | 59 | 163.73 | 1.29% |

The risk allocation admits three more requests than the marginal-window policy here, with a higher simulated conflict rate. Compared with fixed buffers, it has fewer weighted admissions and lower booked fees, while respecting individual model risk budgets. It does not dominate every baseline. Zero sampled conflicts for quantile buffers is not proof of zero probability.

[Input and full result](examples/risk-allocation-run) include request parameters and a scenario hash. Booked fees are not profit. Expected conflict-free booking fees are an auxiliary diagnostic; refunds, compensation and service recovery are not modeled.

```bash
python -m parkinglab --csv examples/risk-allocation-run/input.csv --slots 4 --trials 500 --output results/custom
python -m parkinglab --replay examples/risk-allocation-run/result.json --output results/replayed
```

JSON replay uses the saved input/config. In a time-limited solve, runtime and the selected tied/partial incumbent can vary by machine, so replay is not a byte-identical schedule guarantee. Seeded Monte Carlo deviations are identical given the same input order, seed and distribution implementation.

## Scaling and solution quality

```bash
python scripts/benchmark.py
```

The frozen [protocol](scenarios/scale-protocol.json) evaluates 24, 48, 96 and 192 requests, two deviation distributions and three independent demand seeds: 24 input instances and 120 policy runs. Each uses 300 common-random-number trials. [Raw records](docs/scale-benchmark.json) and [summary CSV](docs/scale-benchmark.csv) retain admissions, conflicts, model size, runtime, optimality gaps and fallback use. The browser displays the recorded experiment separately from the current user's run.

Smaller risk-assignment cases were solved to optimality in the recorded experiment. The 192-request cases reached the two-second solver limit; their feasible solutions and available upper bounds are kept. Timings include model construction and verification, so total method runtime may exceed the solver limit. Median/IQR values span different input seeds, not repeated identical hardware timing trials. [Interpretation](docs/scaling.md) covers the measured trade-offs.

## Checks

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests compare tiny MILPs with exhaustive bay assignments, check pair probabilities against independent Monte Carlo, verify deterministic endpoint boundaries and uniform convolution, cover repaired invalid durations, and exercise timeout fallback, individual budgets, FCFS order, CSV/API validation and exports. The CI workflow also runs the command-line example on Linux.

## Scope

This is an offline decision prototype built from the parking-reservation problem. It is not an exact implementation of the dissertation: it does not reproduce its conflict formula, multi-objective algorithm, loyalty estimation or reported numerical improvements. The current model has identical bays, independent endpoint distributions and fixed booking times. It does not model queues, online rescheduling, correlated disruption, payment settlement or field deployment. Distribution calibration must precede operational use.

The local server keeps at most 20 runs in memory; exported records are needed for persistence. It has no accounts or production monitoring. Optional local Ollama text explanations receive scalar aggregate metrics only and never determine the allocation. Actual Ollama inference remains unverified; optimization and reports work without it. The older three-policy artifact under `examples/default-run` records the earlier model and should not be compared as a current five-policy run. Docker configuration is included but has not been build-tested here.

References: [SciPy MILP and solver bounds](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html), [Normal CDF](https://docs.scipy.org/doc/scipy/reference/generated/scipy.special.ndtr.html).
