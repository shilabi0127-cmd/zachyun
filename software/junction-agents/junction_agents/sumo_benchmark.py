"""Frozen-protocol SUMO comparison and machine-readable evidence bundle."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from time import perf_counter
import numpy as np
from .sumo_backend import run_episode
from .sumo_scenarios import build_network, generate_demand


def validate_timing(protocol):
    """Reject protocol edits that the current controller adapter cannot execute."""
    supported = {'decision_interval_seconds': 5, 'yellow_seconds': 3,
                 'all_red_seconds': 2, 'minimum_green_seconds': 10,
                 'maximum_green_seconds': 60}
    for key, value in supported.items():
        if protocol.get(key) != value:
            raise ValueError(f'{key} must be {value} for this adapter')


def run_protocol(protocol_path,work,checkpoint_path,episodes=None):
    protocol_path=Path(protocol_path)
    raw=protocol_path.read_bytes();protocol=json.loads(raw)
    validate_timing(protocol)
    work=Path(work).resolve();work.mkdir(parents=True,exist_ok=True)
    checkpoint=json.loads(Path(checkpoint_path).read_text(encoding='utf-8'))
    q_sha=hashlib.sha256(json.dumps(checkpoint['q'],separators=(',',':')).encode()).hexdigest()
    first,last=protocol['evaluation_seeds']
    if episodes is not None:
        if not 1<=episodes<=last-first+1:raise ValueError('episodes exceeds the frozen seed range')
        last=first+episodes-1
    if first<=protocol['development_seeds'][1]:raise ValueError('Development/evaluation seeds overlap')
    started=perf_counter();records=[];network_manifests={}
    for case in protocol['scenarios']:
        network_dir=work/'networks'/str(case['spacing_metres'])
        network_manifests[case['name']]=build_network(network_dir,case['spacing_metres'])
        for seed in range(first,last+1):
            scenario_dir=work/case['name']/str(seed)
            scenario_dir.mkdir(parents=True,exist_ok=True)
            route=scenario_dir/'demand.rou.xml'
            demand=generate_demand(route,seed,case['rate'],protocol['departure_window_seconds'],case['profile'])
            (scenario_dir/'demand.json').write_text(json.dumps(demand,indent=2),encoding='utf-8')
            hashes=set()
            for policy in protocol['policies']:
                result=run_episode(network_dir/'network.net.xml',route,demand,policy,scenario_dir/policy,
                    checkpoint=checkpoint,end_seconds=protocol['observation_horizon_seconds'],
                    record_trajectory=seed==first and case['name']=='tidal_regular' and policy=='joint_rollout')
                if result['sumo_version']!='SUMO '+protocol['sumo_version']:
                    raise RuntimeError('SUMO version differs from the evaluation protocol')
                result['scenario']=case['name'];records.append(result);hashes.add(result['route_sha256'])
                print(json.dumps({'scenario':case['name'],'seed':seed,'policy':policy,'arrived':result['arrived'],
                    'scheduled':result['scheduled'],'mean_halted':round(result['mean_approach_halted_vehicles'],3)}),flush=True)
                (work/'partial-results.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
            if len(hashes)!=1:raise RuntimeError('Policies used different demand schedules')
    summary=[]
    for case in protocol['scenarios']:
        reference={r['seed']:r for r in records if r['scenario']==case['name'] and r['policy']=='sumo_actuated'}
        for policy in protocol['policies']:
            rows=[r for r in records if r['scenario']==case['name'] and r['policy']==policy]
            def mean(key):
                values=[r[key] for r in rows if r[key] is not None]
                return float(np.mean(values)) if values else None
            delta=np.array([r['mean_approach_halted_vehicles']-reference[r['seed']]['mean_approach_halted_vehicles'] for r in rows])
            summary.append({'scenario':case['name'],'policy':policy,'episodes':len(rows),
                **{key:mean(key) for key in ['scheduled','arrived','running_at_end','pending_insertion_at_end','mean_approach_halted_vehicles',
                    'completed_mean_time_loss_seconds','insertion_backlog_vehicle_seconds','phase_changes']},
                'mean_episode_decision_p95_ms':mean('decision_p95_ms'),
                'paired_halted_difference_vs_actuated':float(delta.mean()),
                'paired_difference_standard_error':float(delta.std(ddof=1)/np.sqrt(len(rows))) if len(rows)>1 else None})
    report={'protocol':protocol,'protocol_sha256':hashlib.sha256(raw).hexdigest(),
        'actual_evaluation_seeds':[first,last],'checkpoint_q_sha256':q_sha,
        'network_manifests':network_manifests,'records':records,'summary':summary,
        'runtime_seconds':round(perf_counter()-started,3),
        'safety_accounting':{'signal_audit_violations':sum(r['signal_audit_violations'] for r in records),
            'collision_vehicle_reports':sum(r['collision_vehicle_reports'] for r in records),
            'teleport_starts':sum(r['teleport_starts'] for r in records)},
        'scope':'Actual headless SUMO execution on synthetic, uncalibrated networks. Completed-trip time loss is conditional on completion; inspect remaining and pending counts. Native actuated runtime is inside SUMO and excluded from Python planning latency.'}
    (work/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    with (work/'summary.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(summary[0]));writer.writeheader();writer.writerows(summary)
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--protocol',type=Path,default=Path('scenarios/sumo-protocol.json'))
    parser.add_argument('--checkpoint',type=Path,default=Path('examples/checkpoint.json'))
    parser.add_argument('--work',type=Path,default=Path('.sumo/validation'))
    parser.add_argument('--episodes',type=int)
    args=parser.parse_args()
    result=run_protocol(args.protocol,args.work,args.checkpoint,args.episodes)
    print(json.dumps({'completed_runs':len(result['records']),'seconds':result['runtime_seconds'],'audit':result['safety_accounting']}))


if __name__=='__main__':main()
