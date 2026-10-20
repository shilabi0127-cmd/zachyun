# control & inference

Traffic control with a queue prototype and a SUMO backend. Python 3.12.

## junction-agents

[Source](software/junction-agents) · [SUMO experiment](software/junction-agents/docs/sumo.md) · [Protocol](software/junction-agents/scenarios/sumo-protocol.json) · [Recorded results](software/junction-agents/examples/sumo-summary.csv)

Four signal agents control a 2×2 network through TraCI. Fixed-time and native SUMO actuated control are compared with a pressure heuristic, constrained joint rollout, CEM and zero-shot transfer of a queue-trained Q table.

```bash
cd software/junction-agents
python -m pip install -r requirements-sumo.txt
python -m junction_agents.sumo_benchmark
```

The recorded experiment contains 90 simulator runs across three demand/geometry cases and five held-out seeds. Inputs are shared between policies. Actual signal states are checked for green-time bounds, yellow and all-red clearance; vehicle accounting includes trips still running or waiting to enter.

Native actuated control performs best in these SUMO cases. The queue-model gains do not transfer directly. The implementation keeps this result, its input hashes and per-seed records rather than presenting the prototype as a deployment result.

The [queue experiment](software/junction-agents/docs/queue-model.md) isolates action masking and the learned-value ablation. The [CEM notes](software/junction-agents/docs/cem.md) compare search cost and control outcomes. [Integration tests](software/junction-agents/tests/test_sumo_integration.py) launch the actual simulator in CI.

## Supporting tools

- [local-research-kit](software/local-research-kit) provides SQLite retrieval, bounded context selection, local GGUF/Ollama inference and quote checks. An [actual CPU GGUF run](software/local-research-kit/docs/generation-notes.md) is recorded; model weights stay outside the repository.
- [parking-ops-lab](software/parking-ops-lab) compares interval MILP allocation with common Monte Carlo samples and a browser schedule.
- [choice-model-lab](software/choice-model-lab) implements conditional logit with grouped holdout and cluster-robust uncertainty.

Traffic inputs are synthetic. Each implementation documents its assumptions and reproduction commands.
