"""Bernoulli CEM over feasible joint action sequences.

This is a discrete sampling planner, not a reproduction of iCEM.
"""
from dataclasses import asdict, dataclass
from time import perf_counter
import numpy as np
from .environment import NEIGHBORS
from .policies import IndependentQ, coordinated


@dataclass(frozen=True)
class CEMConfig:
    horizon: int = 5
    population: int = 32
    elite: int = 6
    iterations: int = 3
    smoothing: float = .7
    discount: float = .95

    def __post_init__(self):
        if not 2<=self.horizon<=12 or not 4<=self.population<=256:
            raise ValueError("Invalid horizon or population")
        if not 1<=self.elite<=self.population or not 1<=self.iterations<=10:
            raise ValueError("Invalid elite count or iteration count")
        if not 0<self.smoothing<=1 or not 0<self.discount<=1:
            raise ValueError("Invalid smoothing or discount")


def rollout_batch(env, plans, discount=.95):
    """Simulate B plans together. No future arrival stream is read.

    Requested actions are repaired against each candidate's evolving masks.
    The scalar environment is kept as an independent reference in tests.
    """
    plans=np.asarray(plans)
    if plans.ndim!=3 or plans.shape[0]<1 or plans.shape[1]<1 or plans.shape[2]!=4:
        raise ValueError("Plans must have shape (population, horizon, 4)")
    if not np.issubdtype(plans.dtype,np.integer) or np.any((plans<0)|(plans>1)):
        raise ValueError("Plan actions must be binary integers")
    batch,horizon,_=plans.shape
    queues=np.repeat(env.queues[None,:,:],batch,axis=0)
    phase=np.repeat(env.phase[None,:],batch,axis=0)
    elapsed=np.repeat(env.elapsed[None,:],batch,axis=0)
    executed=np.empty_like(plans)
    scores=np.zeros(batch)
    repairs=np.zeros(batch,dtype=int)
    for step in range(horizon):
        requested=plans[:,step,:]
        actions=np.where(elapsed>=env.config.max_green,1,
                         np.where(elapsed<env.config.min_green,0,requested))
        executed[:,step,:]=actions
        repairs+=np.sum(actions!=requested,axis=1)
        phase=phase^actions
        elapsed=np.where(actions==1,0,elapsed+1)
        delta=np.zeros_like(queues)
        blocked=np.zeros(batch,dtype=int)
        exited=np.zeros(batch,dtype=int)
        for node in range(4):
            for direction in range(4):
                green=(actions[:,node]==0)&(phase[:,node]==direction%2)
                possible=np.minimum(env.config.saturation,queues[:,node,direction])*green
                destination=NEIGHBORS[node,direction]
                available=env.config.capacity-queues[:,destination,direction] if destination>=0 else possible
                served=np.minimum(possible,available)
                blocked+=possible-served
                delta[:,node,direction]-=served
                if destination>=0:delta[:,destination,direction]+=served
                else:exited+=served
        queues+=delta
        stage=(np.square(queues.astype(float)).sum(axis=(1,2))/env.config.capacity
               +.5*actions.sum(axis=1)+2*blocked-.1*exited)
        scores+=(discount**step)*stage
    return {"scores":scores,"executed":executed,"queues":queues,"repairs":repairs}


class CEMPlanner:
    def __init__(self,seed=23,config=CEMConfig()):
        self.config=config
        self.rng=np.random.default_rng(seed)
        self.probabilities=np.full((config.horizon,4),.2)
        self.previous_plan=None
        self._zero_q=IndependentQ()
        self.last_diagnostics={}

    def actions(self,env):
        started=perf_counter()
        config=self.config
        # Include the existing no-Q controller as a first-action seed.
        seed=np.zeros((config.horizon,4),dtype=int)
        seed[0]=coordinated(env,self._zero_q,learning_weight=0.)
        initial=rollout_batch(env,seed[None,:,:],config.discount)
        best_plan=initial["executed"][0].copy()
        initial_cost=best_cost=float(initial["scores"][0])
        probabilities=self.probabilities.copy()
        repairs=0
        for _ in range(config.iterations):
            plans=(self.rng.random((config.population,config.horizon,4))<probabilities).astype(int)
            plans[0]=best_plan
            if self.previous_plan is not None:
                plans[1]=np.vstack((self.previous_plan[1:],np.zeros((1,4),dtype=int)))
            plans[-1]=(probabilities>=.5).astype(int)
            rollout=rollout_batch(env,plans,config.discount)
            scores=rollout["scores"]
            winner=int(np.argmin(scores))
            if scores[winner]<best_cost:
                best_cost=float(scores[winner]);best_plan=rollout["executed"][winner].copy()
            elite_indices=np.argsort(scores,kind='stable')[:config.elite]
            elite_mean=rollout["executed"][elite_indices].mean(axis=0)
            probabilities=np.clip((1-config.smoothing)*probabilities+config.smoothing*elite_mean,.03,.97)
            repairs+=int(rollout["repairs"].sum())
        self.previous_plan=best_plan
        self.probabilities=np.vstack((probabilities[1:],np.full((1,4),.2)))
        self.last_diagnostics={"planning_ms":(perf_counter()-started)*1000,
            "seed_plan_cost":initial_cost,"selected_plan_cost":best_cost,
            "candidate_rollouts":1+config.iterations*config.population,
            "model_transition_evaluations":(1+config.iterations*config.population)*config.horizon+3*int(np.prod(env.action_mask().sum(axis=1))),
            "sample_action_repairs":repairs,"config":asdict(config)}
        return best_plan[0].copy()
