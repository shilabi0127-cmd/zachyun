# SUMO experiment

This backend runs Eclipse SUMO 1.28.0 through TraCI. Vehicles accelerate, brake, follow one another and wait at actual signal links. The queue simulator is used only as a planning surrogate, not as the source of the SUMO measurements.

## Reproduction

Run from `software/junction-agents` with Python 3.12.

```bash
python -m pip install -r requirements-sumo.txt
python -m junction_agents.sumo_benchmark
```

The optional `--work PATH` selects the output directory. `--episodes 1` is a quick 18-run installation check. Default execution covers all 90 runs. Existing output files at the selected path are replaced. The adapter rejects protocol timing changes it cannot execute and checks the installed SUMO version against the protocol. `SUMO_BINARY` and `NETCONVERT_BINARY` can point to explicit executables; otherwise the wheel installation is discovered automatically.

The committed [protocol](../scenarios/sumo-protocol.json), [report](../examples/sumo-validation.json) and [CSV](../examples/sumo-summary.csv) belong together. The report stores SHA-256 hashes for the protocol, networks, route schedules and frozen Q table. Hardware-dependent planning times need not reproduce exactly.

## Scenarios and separation

Each network has four signal junctions, eight boundary nodes and 24 directed single-lane edges. Vehicles travel straight through two junctions. There are no turning movements, pedestrians or lane changes. Road speed is 13.9 m/s. Networks are generated rather than taken from a city map and are **not calibrated to real traffic**.

| Case | Junction spacing | Base arrivals per boundary per second | Demand |
| --- | ---: | ---: | --- |
| tidal_regular | 250 m | 0.10 | North/south load moves to east/west halfway through |
| tidal_heavy | 250 m | 0.16 | Same directional change, more demand |
| long_asymmetric | 380 m | 0.10 | Heavier main row, with a middle-period pulse |

These are changes in demand and link length, not three independent real-world datasets or network topologies. Boundary scales are seeded. Departures are Poisson counts with within-second offsets. Krauss driving noise and speed variation are set to zero; randomized demand supplies the variation between seeds.

Development seeds are 200000–200004; final seeds are 210000–210004. The protocol was fixed before the final run. No policy was tuned using the final-seed outcomes. Each route schedule is generated once and reused across all six policies with the same SUMO seed. Controllers receive current observations, not future departures. Demand lasts 600 seconds, followed by up to 300 seconds to clear the network.

The queue-trained Q table is frozen and evaluated zero-shot. It has not been trained in SUMO. Longer links and different vehicle dynamics therefore test transfer as well as control performance.

## Control and checks

External controllers decide every five seconds. Their actions pass the same minimum/maximum-green mask. A switch applies three seconds yellow, two seconds all-red, then the opposite green. Signal indices are derived from TraCI controlled-link mappings, rather than assumed to match an array order.

The actuated baseline uses SUMO's native detector-based program with 10–60 second greens and the same yellow/all-red durations. Its phase decisions can respond every simulator second; the external planners decide every five seconds. The comparison deliberately retains this practical baseline advantage rather than calling the algorithms equivalent control implementations.

An independent observer checks actual signal strings every second and at externally commanded transitions. It rejects conflicting or unsupported states, direct green-to-green switches, and duration violations. Vehicle conservation is checked against both live counts and TripInfo output. Teleporting is disabled; collision vehicle reports and teleport starts are counted. Zero recorded events in these cases do not establish real-road safety.

## Results

Mean total halted approach vehicles, averaged over the fixed 900-second horizon and then over five seeds.

| Controller | Tidal regular | Tidal heavy | Long asymmetric |
| --- | ---: | ---: | ---: |
| Fixed time | 13.51 | 31.75 | 21.65 |
| SUMO actuated | 6.18 | 15.76 | 5.84 |
| Pressure heuristic | 8.59 | 22.16 | 10.10 |
| Joint rollout, no Q | 10.19 | 24.66 | 10.12 |
| CEM sequence planner | 10.35 | 25.86 | 9.82 |
| Queue-trained IQL, zero-shot | 14.16 | 37.23 | 16.07 |

Native actuated control is better on all three cases. Compared with fixed time, joint rollout reduces this queue measure by approximately 24.5%, 22.3% and 53.2%, respectively, but comparison with fixed time alone would hide the stronger baseline. CEM is not consistently better than joint rollout and costs more planning time. These results support simulator integration and the ability to diagnose transfer failure; they do not establish a new superior traffic controller.

All scheduled trips completed in each recorded run; end-of-horizon running and pending counts were zero. There were no recorded signal audit violations, collision vehicle reports or teleport starts. [One run's decision log, time series and signal audit](../examples/sumo-sample) provide a compact inspection sample. Full raw files are regenerated locally.

## Measurement details

- `mean_approach_halted_vehicles` sums halted vehicles on the 16 incoming lanes once per second, integrates that count and divides by 900. It excludes boundary waiting outside the network. Runs can stop after all trips finish; the remaining fixed-horizon contribution is zero.
- `insertion_backlog_vehicle_seconds` separately integrates scheduled departures not yet inserted, using one-second samples. It is a rectangular approximation and is not exactly the sum of TripInfo departure delays with fractional departure times.
- `completed_mean_time_loss_seconds` comes from actual SUMO TripInfo, not the queue objective. It is conditional on trip completion. Running and pending counts must be inspected alongside it; unfinished trips are never silently averaged as completed.
- `scheduled = arrived + running_at_end + pending_insertion_at_end` must hold. TripInfo completed/unfinished counts must match live arrived/running counts.
- `paired_halted_difference_vs_actuated` matches each policy to the native baseline on the same seed. Its standard error describes only five synthetic demand draws, not generalization to cities.
- `mean_episode_decision_p95_ms` averages five per-episode Python planning p95 values. It is not a pooled p95 or total simulator runtime. Native actuation happens inside SUMO and has no comparable Python planning latency, so its entry is blank.

## Why the queue controllers transfer poorly

The adapter projects actual lane halting counts onto the queue environment. Storage is approximated by lane length divided by 7.5 m; the surrogate serves two vehicles per five-second step. These assumptions are uncalibrated. It ignores approaching moving vehicles, acceleration, startup loss and travel time between junctions. The Q table was also trained under different storage and demand dynamics. Joint rollout and CEM plan through this same imperfect model, so a wider search can optimize the wrong prediction.

The native controller uses gap detection from the microscopic simulation. The present experiment does not isolate how much of the performance gap comes from observation, control frequency or model mismatch. A useful next experiment would calibrate discharge/travel times on development seeds, add incoming moving vehicles to the state, then evaluate on a newly reserved seed range. The current final seeds should not be reused to select a claimed improvement.

## Files produced

`report.json` contains every episode and summary; `summary.csv` is suitable for analysis. Each scenario/seed has its route XML and demand metadata. Each policy directory contains TripInfo, SUMO summary/warnings, a decision trace, one-second time series, observed signal transitions and result metrics. The first regular-seed joint-rollout run also records actual vehicle positions and speeds every five seconds in `trajectory.jsonl`. This is a sampled trajectory, not a complete signal-program replay file.

The committed 250 m and 380 m fixtures are under `scenarios/sumo-grid` and `scenarios/sumo-long-grid`. Regeneration uses the pinned netconvert version. Runtime output stays under ignored `.sumo/`; binaries, logs for all 90 runs and model weights are not committed.

## References

- [Official Python/TraCI interface](https://sumo.dlr.de/docs/TraCI/Interfacing_TraCI_from_Python.html)
- [Controlled links and signal state retrieval](https://sumo.dlr.de/docs/TraCI/Traffic_Lights_Value_Retrieval.html)
- [TripInfo definitions and unfinished trips](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html)
- [Official SUMO distribution](https://sumo.dlr.de/docs/Downloads.php)
