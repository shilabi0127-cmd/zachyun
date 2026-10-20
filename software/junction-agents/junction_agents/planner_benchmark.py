"""Separate CEM comparison; does not replace the original controller experiment."""
import argparse
import json
import platform
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
import numpy as np
from .cem import CEMConfig,CEMPlanner
from .environment import Config,Network
from .policies import IndependentQ,fixed_time,max_pressure,coordinated


def benchmark(episodes=10,seed_start=70000,config=CEMConfig()):
    if not 2<=episodes<=100 or seed_start<70000:
        raise ValueError("Use 2..100 new scenarios with seed_start >= 70000")
    records=[];started=perf_counter()
    zero_q=IndependentQ()
    for regime,demand in [('regular',.65),('higher',1.1)]:
        for seed in range(seed_start,seed_start+episodes):
            for name in ['fixed_time','pressure','joint_rollout','cem']:
                env=Network(seed,Config(demand=demand))
                planner=CEMPlanner(seed+100000,config)
                latency=[];cost_improvements=[]
                while env.t<env.config.horizon:
                    tick=perf_counter()
                    if name=='fixed_time':action=fixed_time(env)
                    elif name=='pressure':action=max_pressure(env)
                    elif name=='joint_rollout':action=coordinated(env,zero_q,0.)
                    else:action=planner.actions(env)
                    latency.append((perf_counter()-tick)*1000)
                    if name=='cem':
                        d=planner.last_diagnostics
                        cost_improvements.append(d['seed_plan_cost']-d['selected_plan_cost'])
                    env.step(action)
                records.append({'regime':regime,'seed':seed,'policy':name,**env.metrics(),
                    'decision_ms':latency,'mean_predicted_cost_improvement':float(np.mean(cost_improvements)) if cost_improvements else None})
    summary=[]
    for regime in ['regular','higher']:
        base={r['seed']:r for r in records if r['regime']==regime and r['policy']=='joint_rollout'}
        for name in ['fixed_time','pressure','joint_rollout','cem']:
            cases=[r for r in records if r['regime']==regime and r['policy']==name]
            latency=np.concatenate([r['decision_ms'] for r in cases])
            delta=np.array([r['average_queued_vehicles']-base[r['seed']]['average_queued_vehicles'] for r in cases])
            summary.append({'regime':regime,'policy':name,
                **{key:float(np.mean([r[key] for r in cases])) for key in ['average_queued_vehicles','exited','overflow','switches']},
                'decision_p50_ms':float(np.quantile(latency,.5)),'decision_p95_ms':float(np.quantile(latency,.95)),
                'paired_queue_difference_vs_joint':float(delta.mean()),
                'paired_difference_standard_error':float(delta.std(ddof=1)/np.sqrt(episodes))})
    return {'scenario_seeds':[seed_start,seed_start+episodes-1],'episodes_per_policy_and_regime':episodes,
        'planner_config':asdict(config),'environment_configs':{name:asdict(Config(demand=demand)) for name,demand in [('regular',.65),('higher',1.1)]},
        'summary':summary,'episodes':records,'runtime_seconds':round(perf_counter()-started,3),
        'versions':{'python':platform.python_version(),'numpy':np.__version__,'platform':platform.platform()},
        'scope':'Synthetic queue control; zero-arrival planning forecasts. Lower predicted planning cost does not guarantee better realized performance. Single-machine latency, not a real-time deployment claim.'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--episodes',type=int,default=10)
    parser.add_argument('--seed-start',type=int,default=70000)
    parser.add_argument('--output',type=Path,default=Path('examples/cem-evaluation.json'))
    args=parser.parse_args()
    result=benchmark(args.episodes,args.seed_start)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='episodes'},indent=2))


if __name__=='__main__':main()
