# parking-ops-lab

Booking allocation with fixed intervals, uncertain arrival/departure times and a small browser client.

```bash
python -m pip install -r requirements.txt
python -m uvicorn parkinglab.api:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Import a CSV or generate sample requests, choose the objective and run the comparison. JSON, schedule CSV and a Markdown report can be downloaded from the result page.

## Policies

- **FCFS** sorts by scheduled arrival, breaking ties by input order. This is not actual booking-submission order.
- **Nominal MILP** selects intervals to maximize either priority-weighted admissions or booking fees under bay-capacity constraints.
- **Buffered MILP** expands each interval with arrival/departure quantiles, then solves the same selection problem.

The solver is SciPy/HiGHS. Maximum interval occupancy occurs at a start event, so capacity is checked at these events. A heap-based interval coloring assigns selected intervals to identical bays. The solver status and available optimality gap are retained; a time-limited feasible solution is not labelled optimal.

The interval-selection formulation also admits network-flow approaches. This implementation uses MILP as an explicit modelling baseline, not a new solver algorithm.

## Input

```csv
id,start,end,fee,priority,arrival_mean,arrival_std,departure_mean,departure_std
R001,08:00,09:00,10,4,-2,4,4,5
R002,09:00,10:00,8,1,-2,4,4,5
```

Only `id,start,end` are required. Times are minutes or `HH:MM`, within one day. Deviations are in minutes. Priority is an input weight from 1 to 10; the separate priority-admission metric uses requests with weight ≥3. Booking fees are not net profit. Limits are 300 requests, 20 bays and 3000 simulation trials.

## Buffer rule

```text
alpha_i = alpha / sqrt(priority_i)
z_i = NormalQuantile(1 - alpha_i / 2)
early_i = max(0, z_i * arrival_std_i - arrival_mean_i)
late_i  = max(0, departure_mean_i + z_i * departure_std_i)
window_i = [start_i - early_i, end_i + late_i)
```

These are marginal quantile windows. They are a planning heuristic, not a system-wide joint chance-constraint guarantee. A larger buffer consumes capacity and can reduce admissions or revenue.

## Simulation

All policies share the same sampled arrival/departure deviations. A request is counted as conflicting when its actual interval overlaps another admitted request on the same bay. Each request is counted once per trial; the denominator is admitted requests. Zero admissions produces `null`, not a zero-risk score.

The 95% sampling interval uses a Hoeffding bound across independent trial-level rates. It is conservative and does not cover model error. Request outcomes within a trial are not treated as independent observations.

Assumptions include independent normal deviations, identical bays and fixed intervals. Actual departure before arrival is clamped to arrival plus 0.001 minute and counted in the output. There is no queue, online reassignment or downstream loss model. The synthetic examples are separate from any survey or field results.

```bash
python -m parkinglab --slots 4 --trials 500 --seed 20261020 --output results
python -m parkinglab --csv examples/default-run/input.csv --output results/imported
python scripts/sweep.py
```

Inputs, versions, seeds and a scenario hash are saved with the output. The sensitivity script covers three input sizes and three risk settings; its one-off runtime records are not a rigorous speed benchmark.

## Optional Ollama report

The browser lists models already available through a local Ollama service. Only server-side aggregate metrics and configuration are sent to the model, not the CSV or individual schedules. The endpoint is restricted to loopback HTTP addresses. A deterministic report remains available without a model.

The adapter has HTTP contract tests. Actual Ollama inference has not been exercised in this project; the separate local-research-kit supports direct GGUF experiments. Upstream models keep their own licenses.

## Tests and deployment

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests include brute-force objective checks on tiny cases, interval boundaries, independent pairwise conflict checks, reproducibility, CSV validation and API flows.

The local server retains at most 20 runs in memory. It has no user accounts, durable task queue or production monitoring. A Dockerfile is included but has not been build-tested on the development machine.

```bash
docker build -t parkingops-lab .
docker run --rm -p 127.0.0.1:8000:8000 parkingops-lab
```

References: [SciPy milp](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html), [Ollama chat](https://docs.ollama.com/api/chat).
