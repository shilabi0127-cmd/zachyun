# allocation & control

Reservation allocation, traffic control and local inference tools. Python 3.12.

## parking-ops-lab

[Source](software/parking-ops-lab) · [Model](software/parking-ops-lab/docs/model.md) · [Recorded example](software/parking-ops-lab/examples/risk-allocation-run) · [中文使用说明](software/parking-ops-lab/docs/使用说明.md)

An offline parking-reservation decision tool. Import orders, specify arrival/departure uncertainty and individual service-risk limits, then inspect accepted/rejected bookings, bay assignments, risky pairs and inter-booking gaps in a browser.

- The bay-assignment MILP enforces a per-request union bound over all coassigned pairs. Its probability model includes an allowance for repaired invalid durations.
- FCFS, nominal intervals, fixed buffers and quantile buffers provide explicit baselines. Every policy uses the same Monte Carlo realizations for comparison.
- A recorded scale experiment covers 24–192 orders, two distributions and three seeds. Timed-out solutions keep their actual status, bound and fallback source.

```bash
cd software/parking-ops-lab
python -m pip install -r requirements.txt
python -m uvicorn parkinglab.api:app --host 127.0.0.1 --port 8000
```

## Supporting projects

- [junction-agents](software/junction-agents) connects constrained signal controllers to SUMO/TraCI. Its [90-run experiment](software/junction-agents/docs/sumo.md) retains the stronger native actuated baseline and the queue-to-microsimulation transfer failure.
- [local-research-kit](software/local-research-kit) implements SQLite retrieval, bounded context, local GGUF/Ollama inference and quote checks, with a recorded CPU GGUF run.
- [choice-model-lab](software/choice-model-lab) implements conditional logit with grouped holdout and cluster-robust uncertainty.

Bundled traffic inputs are synthetic. These implementations document their assumptions and do not claim field deployment or reproduce dissertation performance numbers.
