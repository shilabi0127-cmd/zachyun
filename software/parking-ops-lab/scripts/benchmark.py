"""Record scale/quality trade-offs with independent simulated service outcomes."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
from time import perf_counter

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from parkinglab.domain import ExperimentRequest, ExperimentConfig, sample_reservations
from parkinglab.simulation import run_experiment


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--protocol',type=Path,default=ROOT/'scenarios/scale-protocol.json')
    parser.add_argument('--output',type=Path,default=ROOT/'docs/scale-benchmark.json')
    args=parser.parse_args();raw=args.protocol.read_bytes();protocol=json.loads(raw)
    started=perf_counter();records=[]
    for distribution in protocol['distributions']:
        for n in protocol['sizes']:
            for seed in protocol['seeds']:
                config=ExperimentConfig(slots=max(1,math.ceil(n/protocol['requests_per_bay'])),
                    seed=seed,trials=protocol['trials'],risk_budget=protocol['risk_budget'],
                    fixed_buffer_minutes=protocol['fixed_buffer_minutes'],objective=protocol['objective'],
                    deviation_distribution=distribution,time_limit=protocol['solver_time_limit_seconds'])
                result=run_experiment(ExperimentRequest(reservations=sample_reservations(n,seed),config=config))
                for key,row in result['policies'].items():
                    records.append({'size':n,'slots':config.slots,'seed':seed,'distribution':distribution,
                        'policy':key,'scenario_hash':result['scenario_hash'],
                        **{name:row[name] for name in ['accepted','acceptance_rate','accepted_weight','revenue',
                            'conflict_rate','priority_acceptance_rate','solver_runtime_ms','optimal','mip_gap',
                            'objective_value','objective_upper_bound','solution_source','requests_over_risk_budget',
                            'model_variables','model_constraints']}})
                print(json.dumps({'size':n,'seed':seed,'distribution':distribution,
                    'risk_status':result['policies']['risk_milp']['solver_status']}),flush=True)
    summary=[]
    for distribution in protocol['distributions']:
        for n in protocol['sizes']:
            for policy in result['policies']:
                rows=[r for r in records if r['size']==n and r['distribution']==distribution and r['policy']==policy]
                times=[r['solver_runtime_ms'] for r in rows]
                gaps=[r['mip_gap'] for r in rows if r['mip_gap'] is not None]
                summary.append({'distribution':distribution,'size':n,'slots':rows[0]['slots'],'policy':policy,
                    'instances':len(rows),'runtime_median_ms':float(np.median(times)),
                    'runtime_q25_ms':float(np.quantile(times,.25)),'runtime_q75_ms':float(np.quantile(times,.75)),
                    'acceptance_rate_mean':float(np.mean([r['acceptance_rate'] for r in rows])),
                    'accepted_weight_mean':float(np.mean([r['accepted_weight'] for r in rows])),
                    'revenue_mean':float(np.mean([r['revenue'] for r in rows])),
                    'conflict_rate_mean':float(np.mean([r['conflict_rate'] for r in rows if r['conflict_rate'] is not None])) if any(r['conflict_rate'] is not None for r in rows) else None,
                    'proven_optimal_instances':sum(r['optimal'] for r in rows),
                    'fallback_instances':sum(r['solution_source']=='verified_greedy_fallback' for r in rows),
                    'gap_mean_when_available':float(np.mean(gaps)) if gaps else None,
                    'gap_available_instances':len(gaps),
                    'requests_over_risk_budget_total':sum(r['requests_over_risk_budget'] for r in rows)})
    sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'parkinglab').glob('*.py')}
    output={'protocol':protocol,'protocol_sha256':hashlib.sha256(raw).hexdigest(),
        'source_sha256':sources,'versions':result['versions'],
        'machine':{'system':platform.system(),'machine':platform.machine(),'processor':platform.processor()},
        'runtime_seconds':perf_counter()-started,'records':records,'summary':summary}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,indent=2),encoding='utf-8')
    with args.output.with_suffix('.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(summary[0]));writer.writeheader();writer.writerows(summary)
    print(json.dumps({'instances':len(records)//5,'policy_runs':len(records),'seconds':output['runtime_seconds']}))


if __name__=='__main__':main()
