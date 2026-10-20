# Recorded scale experiment

24 synthetic input instances, 120 policy runs, 300 Monte Carlo trials per instance. The frozen protocol uses three independent demand seeds for each size/distribution. Bay count increases with demand size to keep roughly comparable load.

| Distribution | Orders / bays | Method | Runtime median ms | Admissions | Conflict involvement | Mean gap when available | Proven optimal / 3 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| normal | 24 / 2 | fixed_buffer_milp | 5.6 | 45.8% | 12.08% | 0.00% | 3 |
| normal | 24 / 2 | buffered_milp | 4.9 | 36.1% | 0.06% | 0.00% | 3 |
| normal | 24 / 2 | risk_milp | 5.4 | 38.9% | 1.09% | 0.00% | 3 |
| normal | 48 / 3 | fixed_buffer_milp | 4.8 | 34.7% | 12.16% | 0.00% | 3 |
| normal | 48 / 3 | buffered_milp | 4.6 | 30.6% | 0.03% | 0.00% | 3 |
| normal | 48 / 3 | risk_milp | 38.6 | 33.3% | 1.07% | 0.00% | 3 |
| normal | 96 / 6 | fixed_buffer_milp | 5.1 | 40.6% | 18.95% | 0.00% | 3 |
| normal | 96 / 6 | buffered_milp | 5.5 | 32.6% | 0.10% | 0.00% | 3 |
| normal | 96 / 6 | risk_milp | 1043.6 | 35.1% | 0.83% | 0.00% | 3 |
| normal | 192 / 12 | fixed_buffer_milp | 8.4 | 41.7% | 23.69% | 0.00% | 3 |
| normal | 192 / 12 | buffered_milp | 11.4 | 33.3% | 0.10% | 0.00% | 3 |
| normal | 192 / 12 | risk_milp | 2111.0 | 30.4% | 0.59% | 6.34% | 0 |
| uniform | 24 / 2 | fixed_buffer_milp | 5.5 | 45.8% | 12.70% | 0.00% | 3 |
| uniform | 24 / 2 | buffered_milp | 4.2 | 36.1% | 0.00% | 0.00% | 3 |
| uniform | 24 / 2 | risk_milp | 5.1 | 38.9% | 1.96% | 0.00% | 3 |
| uniform | 48 / 3 | fixed_buffer_milp | 4.6 | 34.7% | 12.35% | 0.00% | 3 |
| uniform | 48 / 3 | buffered_milp | 3.9 | 30.6% | 0.00% | 0.00% | 3 |
| uniform | 48 / 3 | risk_milp | 23.9 | 33.3% | 0.52% | 0.00% | 3 |
| uniform | 96 / 6 | fixed_buffer_milp | 4.7 | 40.6% | 19.36% | 0.00% | 3 |
| uniform | 96 / 6 | buffered_milp | 5.6 | 32.6% | 0.00% | 0.00% | 3 |
| uniform | 96 / 6 | risk_milp | 489.7 | 35.1% | 0.56% | 0.00% | 3 |
| uniform | 192 / 12 | fixed_buffer_milp | 8.0 | 41.7% | 25.26% | 0.00% | 3 |
| uniform | 192 / 12 | buffered_milp | 11.3 | 33.3% | 0.00% | 0.00% | 3 |
| uniform | 192 / 12 | risk_milp | 2094.4 | 31.6% | 0.68% | 5.11% | 0 |

Every risk-allocation instance passed its individual-budget audit. This means compliance with the supplied probability model and numerical tolerance, not empirical calibration to a parking lot.

The 192-order risk models hit the two-second solve limit. Available dual bounds and verified fallback use are included in the full JSON; missing gaps are null, not zero. Smaller recorded cases were solved to optimality. A policy optimal for its own feasible set is not necessarily the best policy for a different risk/revenue trade-off.

Times include probability-matrix reuse for risk allocation, model construction and the independent allocation audit, but exclude Monte Carlo sampling and evaluation. The shared risk matrix is built once for all policies and is included in total experiment time, not in each policy solve time. These times are not total end-to-end response times. Quantile values are across different seeded instances, not repeated identical runs. Hardware, solver version and time-limited branching affect timings and incumbents.

The old sensitivity artifact was a three-policy one-off sweep; it belongs to an earlier version. Use [the current protocol](../scenarios/scale-protocol.json), [full records](scale-benchmark.json) and [CSV](scale-benchmark.csv) together. No parameters were changed to select a favorable post-run result.
