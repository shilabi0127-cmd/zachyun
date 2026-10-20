"""A 2x2 straight-through queue network, not a calibrated traffic simulator."""
from dataclasses import asdict, dataclass
import numpy as np


@dataclass(frozen=True)
class Config:
    horizon: int = 120
    capacity: int = 24
    saturation: int = 2
    min_green: int = 2
    max_green: int = 12
    demand: float = .65

    def __post_init__(self):
        if self.horizon<1 or self.capacity<1 or self.saturation<1 or self.min_green<1 or self.max_green<self.min_green or self.demand<0:
            raise ValueError("Invalid environment configuration")


# Approach order N,E,S,W. A vehicle continues straight through each junction.
DIRECTION = [(1,0),(0,-1),(-1,0),(0,1)]
NEIGHBORS = np.full((4,4),-1,dtype=int)
EXTERNAL = np.zeros((4,4),dtype=bool)
for node in range(4):
    row,col=divmod(node,2)
    for direction,(dr,dc) in enumerate(DIRECTION):
        nr,nc=row+dr,col+dc
        if 0<=nr<2 and 0<=nc<2:NEIGHBORS[node,direction]=nr*2+nc
        sr,sc=row-dr,col-dc
        EXTERNAL[node,direction]=not (0<=sr<2 and 0<=sc<2)


class Network:
    def __init__(self,seed:int,config:Config=Config()):
        self.config=config
        rng=np.random.default_rng(seed)
        rates=np.empty((config.horizon,4,4))
        boundary_scale=rng.uniform(.85,1.15,size=(4,4))
        for t in range(config.horizon):
            vertical=1.6 if t<config.horizon//2 else .6
            horizontal=.6 if t<config.horizon//2 else 1.6
            rates[t]=config.demand*np.array([vertical,horizontal,vertical,horizontal])*boundary_scale*EXTERNAL
        self._arrivals=rng.poisson(rates)
        self._arrivals.flags.writeable=False
        self.queues=np.zeros((4,4),dtype=int)
        self.phase=np.zeros(4,dtype=int)  # 0 NS, 1 EW
        self.elapsed=np.zeros(4,dtype=int)
        self.t=0
        self.totals={"queue_area":0,"external_demand":0,"exited":0,"overflow":0,"switches":0,"blocked":0,"max_queue":0}

    def action_mask(self):
        mask=np.ones((4,2),dtype=bool)
        mask[:,0]=self.elapsed<self.config.max_green
        mask[:,1]=self.elapsed>=self.config.min_green
        return mask

    def pressure(self):
        downstream=np.zeros_like(self.queues)
        for i in range(4):
            for d in range(4):
                if NEIGHBORS[i,d]>=0:downstream[i,d]=self.queues[NEIGHBORS[i,d],d]
        p=self.queues-downstream
        return np.column_stack((p[:,0]+p[:,2],p[:,1]+p[:,3]))

    def state(self):
        bins=np.digitize(self.pressure(),[-20,-8,-2,2,8,20])
        return (bins[:,0]*7+bins[:,1])*4+self.phase*2+self.action_mask()[:,1].astype(int)

    def predict(self,actions,external=None):
        actions=np.asarray(actions)
        if actions.shape!=(4,) or not np.issubdtype(actions.dtype,np.integer) or np.any((actions<0)|(actions>1)):
            raise ValueError("Expected four binary actions")
        if not np.all(self.action_mask()[np.arange(4),actions]):raise ValueError("Action violates minimum green or maximum green")
        if external is None:external=np.zeros((4,4),dtype=int)
        q=self.queues.copy();phase=self.phase^actions
        elapsed=np.where(actions==1,0,self.elapsed+1)
        delta=np.zeros_like(q)
        exited=blocked=0
        for i in range(4):
            if actions[i]:continue  # One all-red step when changing phase.
            approaches=(0,2) if phase[i]==0 else (1,3)
            for d in approaches:
                possible=min(self.config.saturation,int(q[i,d]))
                destination=NEIGHBORS[i,d]
                available=self.config.capacity-int(q[destination,d]) if destination>=0 else possible
                served=min(possible,available)
                blocked+=possible-served
                delta[i,d]-=served
                if destination>=0:delta[destination,d]+=served
                else:exited+=served
        q+=delta
        demand=int(external.sum())
        overflow=int(np.maximum(q+external-self.config.capacity,0).sum())
        q=np.minimum(q+external,self.config.capacity)
        info={"external_demand":demand,"exited":exited,"overflow":overflow,
              "switches":int(actions.sum()),"blocked":blocked,"queue_area":int(q.sum()),"max_queue":int(q.max())}
        reward=-(info["queue_area"]+5*overflow+.25*info["switches"])/16
        return q,phase,elapsed,float(reward),info

    def step(self,actions):
        if self.t>=self.config.horizon:raise RuntimeError("Episode already ended")
        self.queues,self.phase,self.elapsed,reward,info=self.predict(actions,self._arrivals[self.t])
        self.t+=1
        for key,value in info.items():
            if key=="max_queue":self.totals[key]=max(self.totals[key],value)
            else:self.totals[key]+=value
        return reward,self.t>=self.config.horizon,info

    def metrics(self):
        return {**self.totals,"average_queued_vehicles":self.totals["queue_area"]/max(1,self.t),
                "remaining_vehicles":int(self.queues.sum()),"steps":self.t}
