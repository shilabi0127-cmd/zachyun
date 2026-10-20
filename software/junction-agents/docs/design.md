# Controller notes

## Why the first version barely switched

A one-step queue objective immediately charges the clearance interval when a signal changes. It cannot see the discharge that occurs after clearance. In the development run, the rollout controller stayed in the initial phase too often. Its low queue values under heavy demand partly came from refusing many external arrivals, while throughput suffered.

The early output is kept in `examples/initial-myopic-run.json`. It was produced before the rollout and maximum-green changes and is not an output of the current controller. It is a development failure record, not a final comparison.

The current controller evaluates three steps, enough to include service after one clearance step. A maximum-green constraint also ensures that each phase gets another service opportunity. These changes were made after looking at the development scenarios; final scenarios use a separate seed range.

## Joint search

At a decision step there are four binary actions, hold or change phase. Masked actions are removed before enumeration. For each feasible first action `a`, a copied queue/phase state is advanced three times. Future simulated actions hold unless a maximum-green change is compulsory. No sampled future arrivals are consulted.

The rollout stage cost is

```text
L = sum(queue_j ** 2) / capacity
    + 0.5 * phase_changes
    + 2.0 * blocked_service
    - 0.1 * network_exits
```

The candidate score adds `sum(0.95 ** t * L_t)` over the three steps and

```text
0.15 * sum(max_feasible Q_i(state_i, action) - Q_i(state_i, candidate_i))
```

Quadratic queue potential couples neighboring decisions through transfers. The Q term expresses a preference for actions with better learned values; it is not a learned transition model or a centralized neural critic.

Only the first action is executed, then the state is observed again. Searching all feasible first actions is exact for this finite surrogate score, but says nothing about optimality of the actual episode or unobserved future demand.

## What the ablation says

Removing the Q term leaves almost the same performance on the final regular-demand cases. The independent Q policy by itself is weaker than the hand-written pressure baseline. Current evidence supports the short-horizon model-based coordination, not a claim that reinforcement learning caused the improvement.

The learned observations are deliberately small and the training reward is global. This can make credit assignment difficult. More training, independent seeds, richer local observations or a different value factorization are reasonable experiments, but they have not been used to retroactively relabel the current results as successful deep RL.
