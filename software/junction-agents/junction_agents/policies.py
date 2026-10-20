"""Masked independent Q-learning and a finite joint-action coordinator."""
from itertools import product
from copy import copy
import numpy as np


def fixed_time(env):
    return ((env.elapsed>=6)&env.action_mask()[:,1]).astype(int)


def max_pressure(env):
    pressure=env.pressure()
    other=1-env.phase
    gain=pressure[np.arange(4),other]-pressure[np.arange(4),env.phase]
    return (((gain>2)&env.action_mask()[:,1])|~env.action_mask()[:,0]).astype(int)


class IndependentQ:
    def __init__(self,seed=17,q=None):
        self.q=np.zeros((4,196,2)) if q is None else np.asarray(q,dtype=float).copy()
        if self.q.shape!=(4,196,2) or not np.isfinite(self.q).all():raise ValueError("Invalid Q table")
        self.rng=np.random.default_rng(seed)

    def actions(self,env,epsilon=0.):
        state=env.state();mask=env.action_mask()
        scores=np.where(mask,self.q[np.arange(4),state],-np.inf)
        action=np.argmax(scores,axis=1)
        explore=self.rng.random(4)<epsilon
        for i in np.flatnonzero(explore):action[i]=self.rng.choice(np.flatnonzero(mask[i]))
        return action

    def update(self,state,action,reward,next_state,next_mask,done,alpha=.08,gamma=.95):
        future=np.max(np.where(next_mask,self.q[np.arange(4),next_state],-np.inf),axis=1)
        target=reward if done else reward+gamma*future
        current=self.q[np.arange(4),state,action]
        self.q[np.arange(4),state,action]+=alpha*(target-current)


def joint_cost(env,actions,learner,learning_weight=.15):
    # Three-step constant-action rollout captures service after an all-red step.
    # Only the first decision is optimized. Later steps hold unless forced.
    simulated=copy(env)
    potential=0.
    for step in range(3):
        action=actions if step==0 else (~simulated.action_mask()[:,0]).astype(int)
        queues,phase,elapsed,_,info=simulated.predict(action)
        potential+=(.95**step)*(np.square(queues.astype(float)).sum()/env.config.capacity
                     +.5*info["switches"]+2*info["blocked"]-.1*info["exited"])
        simulated.queues,simulated.phase,simulated.elapsed=queues,phase,elapsed
    states=env.state()
    values=learner.q[np.arange(4),states]
    valid=np.where(env.action_mask(),values,-np.inf)
    regret=np.sum(np.max(valid,axis=1)-values[np.arange(4),actions])
    # Queue curvature creates interaction between a junction and its neighbors.
    return float(potential+learning_weight*regret)


def coordinated(env,learner,learning_weight=.15):
    choices=[np.flatnonzero(mask).tolist() for mask in env.action_mask()]
    candidates=[np.array(action,dtype=int) for action in product(*choices)]
    return min(candidates,key=lambda actions:joint_cost(env,actions,learner,learning_weight))
