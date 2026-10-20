"""Closed-loop SUMO execution with explicit clearance and censored-trip metrics."""
from bisect import bisect_left
import csv
import hashlib
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4
import xml.etree.ElementTree as ET
import numpy as np

from .environment import Config, Network
from .policies import IndependentQ, coordinated, fixed_time, max_pressure
from .cem import CEMPlanner
from .sumo_scenarios import NODES, binary, movement_lanes
from .sumo_signals import SignalAudit

POLICIES = ('fixed_time', 'sumo_actuated', 'pressure', 'joint_rollout', 'cem', 'q_zero_shot')
DECISION_SECONDS = 5
YELLOW_SECONDS = 3
ALL_RED_SECONDS = 2


def signal_binding(node, links):
    incoming, outgoing = movement_lanes(node)
    axes = []
    if len(links) != 4:
        raise ValueError('Expected exactly four straight controlled links at ' + node)
    used = set()
    for group in links:
        if len(group) != 1:
            raise ValueError('Grouped or missing controlled links are unsupported')
        source, target = group[0][:2]
        if source not in incoming:
            raise ValueError('Unexpected incoming lane at ' + node)
        direction = incoming.index(source)
        if direction in used or target != outgoing[direction]:
            raise ValueError('Expected unique straight movements')
        used.add(direction)
        axes.append(direction % 2)
    return {'incoming': incoming, 'axes': axes,
            'green': [''.join('G' if axis == phase else 'r' for axis in axes) for phase in range(2)],
            'yellow': [''.join('y' if axis == phase else 'r' for axis in axes) for phase in range(2)],
            'red': 'r' * len(axes)}


def trip_metrics(path):
    trips = [row.attrib for row in ET.parse(path).getroot().findall('tripinfo')]
    completed = [row for row in trips if float(row['arrival']) >= 0]
    unfinished = [row for row in trips if float(row['arrival']) < 0]
    def mean(field):
        return float(np.mean([float(row[field]) for row in completed])) if completed else None
    return {'tripinfo_completed': len(completed), 'tripinfo_unfinished': len(unfinished),
            'completed_mean_time_loss_seconds': mean('timeLoss'),
            'completed_mean_duration_seconds': mean('duration'),
            'completed_mean_waiting_seconds': mean('waitingTime'),
            'completed_mean_departure_delay_seconds': mean('departDelay')}


def run_episode(network_path, route_path, demand, policy, output, checkpoint=None,
                end_seconds=900, record_trajectory=False):
    if policy not in POLICIES:
        raise ValueError('Unknown SUMO policy')
    if end_seconds <= demand['departure_window_seconds'] or end_seconds % DECISION_SECONDS:
        raise ValueError('End time must include a drain window and be divisible by five')
    import traci
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    label = 'junction-' + uuid4().hex
    command = [binary('sumo'), '-n', str(Path(network_path).resolve()), '-r', str(Path(route_path).resolve()),
               '--seed', str(demand['seed']), '--step-length', '1', '--no-step-log', 'true',
               '--duration-log.disable', 'true', '--time-to-teleport', '-1', '--collision.action', 'warn',
               '--tripinfo-output', str(output/'tripinfo.xml'), '--tripinfo-output.write-unfinished', 'true',
               '--summary-output', str(output/'summary.xml'), '--error-log', str(output/'warnings.log')]
    learner = IndependentQ(q=checkpoint['q']) if checkpoint else IndependentQ()
    native = policy == 'sumo_actuated'
    planner = CEMPlanner(demand['seed']+1000000)
    connection = None
    process_log = (output/'process.log').open('w', encoding='utf-8')
    decisions = (output/'decisions.csv').open('w', encoding='utf-8', newline='')
    writer = csv.DictWriter(decisions, fieldnames=['time','actions','phase_before','green_steps_before','halted_queues','planning_ms'])
    writer.writeheader()
    trajectory = (output/'trajectory.jsonl').open('w', encoding='utf-8') if record_trajectory else None
    departed = arrived = queue_area = backlog_area = collisions = teleports = switches = 0
    series = []
    planning = []
    clamp_count = 0
    started = perf_counter()
    try:
        traci.start(command, label=label, stdout=process_log)
        connection = traci.getConnection(label)
        version = connection.getVersion()[1]
        if set(connection.trafficlight.getIDList()) != set(NODES):
            raise ValueError('Network must contain exactly the four supported signal agents')
        bindings = {node: signal_binding(node, connection.trafficlight.getControlledLinks(node)) for node in NODES}
        lanes = [lane for node in NODES for lane in bindings[node]['incoming']]
        capacity = max(1, int(np.ceil(max(connection.lane.getLength(lane) for lane in lanes) / 7.5)))
        projection = Network(0, Config(horizon=1, demand=0, capacity=capacity))
        for node in NODES:
            if native:
                connection.trafficlight.setProgram(node,'actuated')
            else:
                connection.trafficlight.setRedYellowGreenState(node, bindings[node]['green'][0])
        audit=SignalAudit(bindings)
        def audit_states(time):
            audit.observe(time,{node:connection.trafficlight.getRedYellowGreenState(node) for node in NODES})
        audit_states(0)
        elapsed_seconds = 0
        while elapsed_seconds < end_seconds:
            observed = np.array([[connection.lane.getLastStepHaltingNumber(lane) for lane in bindings[node]['incoming']] for node in NODES])
            clamp_count += int(np.sum(observed > capacity))
            projection.queues = np.minimum(observed, capacity)
            tick = perf_counter()
            if native:
                action=np.zeros(4,dtype=int)
            elif policy == 'fixed_time':
                action = fixed_time(projection)
            elif policy == 'pressure':
                action = max_pressure(projection)
            elif policy == 'joint_rollout':
                action = coordinated(projection, learner, learning_weight=0.)
            elif policy == 'cem':
                action = planner.actions(projection)
            else:
                if checkpoint is None:
                    raise ValueError('Queue-trained IQL transfer requires a checkpoint')
                action = learner.actions(projection)
            latency = (perf_counter()-tick)*1000
            if not native:
                planning.append(latency)
            if not native and not np.all(projection.action_mask()[np.arange(4), action]):
                raise RuntimeError('Controller proposed an infeasible signal action')
            writer.writerow({'time': elapsed_seconds, 'actions': json.dumps(action.tolist()) if not native else 'native',
                'phase_before': json.dumps(projection.phase.tolist()) if not native else '',
                'green_steps_before': json.dumps(projection.elapsed.tolist()) if not native else '',
                'halted_queues': json.dumps(observed.tolist()), 'planning_ms': latency if not native else ''})
            if not native:
                for i,node in enumerate(NODES):
                    state = bindings[node]['yellow' if action[i] else 'green'][projection.phase[i]]
                    connection.trafficlight.setRedYellowGreenState(node,state)
                audit_states(elapsed_seconds)
            switches += int(action.sum())
            for second in range(DECISION_SECONDS):
                if not native and second == YELLOW_SECONDS:
                    for i,node in enumerate(NODES):
                        if action[i]:
                            connection.trafficlight.setRedYellowGreenState(node,bindings[node]['red'])
                    audit_states(elapsed_seconds)
                connection.simulationStep()
                elapsed_seconds += 1
                audit_states(elapsed_seconds)
                departed += connection.simulation.getDepartedNumber()
                arrived += connection.simulation.getArrivedNumber()
                collisions += connection.simulation.getCollidingVehiclesNumber()
                teleports += connection.simulation.getStartingTeleportNumber()
                halted = sum(connection.lane.getLastStepHaltingNumber(lane) for lane in lanes)
                backlog = max(0,bisect_left(demand['departures'],elapsed_seconds)-departed)
                queue_area += halted
                backlog_area += backlog
                series.append({'time':elapsed_seconds,'halted':halted,'insertion_backlog':backlog,
                               'running':connection.vehicle.getIDCount(),'arrived':arrived,'departed':departed})
                if trajectory is not None and elapsed_seconds % DECISION_SECONDS == 0:
                    vehicles = [{'id':v,'position':connection.vehicle.getPosition(v),'speed':connection.vehicle.getSpeed(v)} for v in connection.vehicle.getIDList()]
                    trajectory.write(json.dumps({'time':elapsed_seconds,'signals':{node:connection.trafficlight.getRedYellowGreenState(node) for node in NODES},'vehicles':vehicles})+'\n')
            if not native:
                projection.phase ^= action
                projection.elapsed = np.where(action==1,0,projection.elapsed+1)
                for i,node in enumerate(NODES):
                    connection.trafficlight.setRedYellowGreenState(node,bindings[node]['green'][projection.phase[i]])
                audit_states(elapsed_seconds)
            if arrived == demand['scheduled']:
                break
        running = connection.vehicle.getIDCount()
        expected = connection.simulation.getMinExpectedNumber()
    finally:
        if connection is not None:
            connection.close()
        decisions.close();process_log.close()
        if trajectory is not None:
            trajectory.close()
    trips = trip_metrics(output/'tripinfo.xml')
    if trips['tripinfo_completed'] != arrived or trips['tripinfo_unfinished'] != running:
        raise RuntimeError('TripInfo and online arrival/running counts disagree')
    pending = demand['scheduled'] - departed
    if departed != arrived + running or expected != running + pending:
        raise RuntimeError('Vehicle accounting mismatch')
    result = {'policy':policy,'seed':demand['seed'],'sumo_version':version,
        'network_sha256':hashlib.sha256(Path(network_path).read_bytes()).hexdigest(), 'route_sha256':demand['route_sha256'],
        'scheduled':demand['scheduled'],'inserted':departed,'arrived':arrived,'running_at_end':running,'pending_insertion_at_end':pending,
        'observation_horizon_seconds':end_seconds,'simulated_seconds':elapsed_seconds,
        'approach_queue_vehicle_seconds':queue_area,'insertion_backlog_vehicle_seconds':backlog_area,
        'mean_approach_halted_vehicles':queue_area/end_seconds,'phase_changes':switches,
        'collision_vehicle_reports':collisions,'teleport_starts':teleports,
        'observation_clamps':clamp_count,'surrogate_capacity':capacity,'surrogate_saturation_per_5s':2,
        'decision_p50_ms':float(np.quantile(planning,.5)) if planning else None,
        'decision_p95_ms':float(np.quantile(planning,.95)) if planning else None,
        'wall_seconds':round(perf_counter()-started,3),**trips,**audit.metrics(elapsed_seconds)}
    (output/'signal-audit.json').write_text(json.dumps(audit.history,indent=2),encoding='utf-8')
    (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    with (output/'timeseries.csv').open('w',encoding='utf-8',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(series[0]));w.writeheader();w.writerows(series)
    return result
