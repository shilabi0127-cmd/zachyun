# control & inference

Traffic-control algorithms and local inference tools. Python 3.12.

## junction-agents

[Code](software/junction-agents) · [Controller notes](software/junction-agents/docs/design.md) · [Episode-level results](software/junction-agents/examples/evaluation.json)

Four signal agents share a queue network. The experiment compares fixed-time control, a pressure heuristic, independent Q-learning and a constrained joint rollout controller.

- Minimum/maximum green, clearance time and downstream storage are enforced in the environment and action masks.
- The joint controller searches feasible first actions with three-step rollouts. A no-Q ablation checks whether learned values actually help.
- Training, development and final evaluation use separate seed ranges. Every policy receives the same arrivals per scenario.
- The current result supports the model-based coordination; the Q term has not demonstrated an additional queue-reduction benefit.
- An optional [CEM sequence planner](software/junction-agents/docs/cem.md) includes vectorized model evaluation and a separate control/latency comparison.

```bash
cd software/junction-agents
python -m pip install -r requirements.txt
python -m junction_agents train --episodes 600
python -m junction_agents evaluate --episodes 25
```

## local-research-kit

[Code](software/local-research-kit) · [Actual GGUF run](software/local-research-kit/docs/generation-notes.md)

Local document retrieval with SQLite FTS5, bounded context selection, schema-constrained GGUF/Ollama generation and exact quote checks. Saved inputs can be replayed independently of the current index. Model weights stay outside the repository.

## Other tools

- [parking-ops-lab](software/parking-ops-lab) — interval MILP allocation, shared Monte Carlo samples and a browser schedule.
- [choice-model-lab](software/choice-model-lab) — conditional logit, grouped holdout and cluster-robust uncertainty.

All bundled traffic inputs are synthetic. Model limits, tests and reproduction commands are documented beside each implementation.
