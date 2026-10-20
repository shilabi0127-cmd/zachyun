import hashlib
import json
import platform
from dataclasses import asdict
from time import perf_counter
import numpy as np
from .environment import Config,Network
from .policies import IndependentQ,fixed_time,max_pressure,coordinated


def train(episodes=800,seed=17):
    if not 1<=episodes<=10000:raise ValueError("episodes must be 1..10000")
    agent=IndependentQ(seed)
    config=Config(horizon=96)
    history=[];started=perf_counter()
    for episode in range(episodes):
        env=Network(episode,config)
        epsilon=.03+.97*np.exp(-episode/max(1,episodes*.3))
        reward_sum=0.
        for _ in range(config.horizon):
            state=env.state();action=agent.actions(env,epsilon)
            reward,done,_=env.step(action)
            agent.update(state,action,reward,env.state(),env.action_mask(),done)
            reward_sum+=reward
        if episode%max(1,episodes//20)==0 or episode==episodes-1:
            history.append({"episode":episode,"epsilon":float(epsilon),"return":reward_sum,**env.metrics()})
    checkpoint={"algorithm":"Independent tabular Q-learning with shared network reward",
        "training_seed":seed,"environment_seeds":[0,episodes-1],"episodes":episodes,
        "config":asdict(config),"alpha":.08,"gamma":.95,"q":agent.q.tolist(),"history":history,
        "training_seconds":round(perf_counter()-started,3),"versions":{"python":platform.python_version(),"numpy":np.__version__}}
    return checkpoint


def evaluate(checkpoint,episodes=25,seed_start=60000):
    if not 2<=episodes<=200:raise ValueError("evaluation episodes must be 2..200")
    training=checkpoint["environment_seeds"]
    if seed_start<=training[1] and seed_start+episodes-1>=training[0]:raise ValueError("Training and test environment seeds overlap")
    learner=IndependentQ(q=checkpoint["q"])
    rows=[];started=perf_counter()
    policies={"fixed_time":fixed_time,"max_pressure":max_pressure,
              "independent_q":lambda env:learner.actions(env),
              "joint_q_coordinator":lambda env:coordinated(env,learner),
              "joint_without_q":lambda env:coordinated(env,learner,learning_weight=0.)}
    for regime,demand in [("held_out",.65),("higher_demand",1.1)]:
        for seed in range(seed_start,seed_start+episodes):
            for policy,choose in policies.items():
                env=Network(seed,Config(demand=demand))
                while env.t<env.config.horizon:env.step(choose(env))
                rows.append({"regime":regime,"seed":seed,"policy":policy,**env.metrics()})
    summary=[]
    for regime in ["held_out","higher_demand"]:
        reference={r["seed"]:r for r in rows if r["regime"]==regime and r["policy"]=="max_pressure"}
        for policy in policies:
            cases=[r for r in rows if r["regime"]==regime and r["policy"]==policy]
            delta=np.array([r["average_queued_vehicles"]-reference[r["seed"]]["average_queued_vehicles"] for r in cases])
            summary.append({"regime":regime,"policy":policy,
                **{metric:float(np.mean([r[metric] for r in cases])) for metric in ["average_queued_vehicles","exited","overflow","switches","remaining_vehicles"]},
                "paired_queue_difference_vs_pressure":float(delta.mean()),
                "paired_difference_standard_error":float(delta.std(ddof=1)/np.sqrt(episodes))})
    digest=hashlib.sha256(json.dumps(checkpoint["q"],separators=(",",":")).encode()).hexdigest()
    return {"checkpoint_q_sha256":digest,"test_seeds":[seed_start,seed_start+episodes-1],
        "episodes_per_policy_and_regime":episodes,"summary":summary,"episodes":rows,
        "evaluation_seconds":round(perf_counter()-started,3),
        "scope":"Synthetic queue network. Three-step constant-action rollout is not trajectory-optimal control. Standard errors describe paired episode differences, not deployment guarantees.",
        "development_seeds":[50000,50024]}
