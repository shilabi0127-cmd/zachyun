"""Reproducible straight-through SUMO grid and seeded vehicle schedules."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
import numpy as np

NODES = ['j00', 'j01', 'j10', 'j11']


def binary(name):
    override = os.environ.get(name.upper() + '_BINARY')
    if override:
        if not Path(override).is_file():
            raise FileNotFoundError(override)
        return override
    found = shutil.which(name)
    if found:
        return found
    try:
        import sumo
        candidate = Path(sumo.SUMO_HOME) / 'bin' / (name + ('.exe' if os.name == 'nt' else ''))
        if candidate.is_file():
            return str(candidate)
    except ImportError:
        pass
    raise RuntimeError('Install requirements-sumo.txt or set ' + name.upper() + '_BINARY')


def edge(source, target):
    return source + '__' + target


def adjacent(row, col, direction):
    dr, dc = [(-1, 0), (0, 1), (1, 0), (0, -1)][direction]
    nr, nc = row + dr, col + dc
    if 0 <= nr < 2 and 0 <= nc < 2:
        return f'j{nr}{nc}'
    return [f'n{col}', f'e{row}', f's{col}', f'w{row}'][direction]


def movement_lanes(node):
    row, col = int(node[1]), int(node[2])
    incoming, outgoing = [], []
    for direction in range(4):
        incoming.append(edge(adjacent(row, col, direction), node) + '_0')
        outgoing.append(edge(node, adjacent(row, col, (direction + 2) % 4)) + '_0')
    return incoming, outgoing


def write_xml(root, path):
    ET.indent(root, space='  ')
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)


def build_network(directory, spacing=250):
    if not 150<=spacing<=500:
        raise ValueError('Spacing must be 150..500 metres')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    nodes, edges, connections, signals = (ET.Element(tag) for tag in ['nodes', 'edges', 'connections', 'additional'])
    coordinates = {f'j{r}{c}': (c*spacing, (1-r)*spacing) for r in range(2) for c in range(2)}
    coordinates.update({f'n{c}': (c*spacing, 2*spacing) for c in range(2)})
    coordinates.update({f's{c}': (c*spacing, -spacing) for c in range(2)})
    coordinates.update({f'w{r}': (-spacing, (1-r)*spacing) for r in range(2)})
    coordinates.update({f'e{r}': (2*spacing, (1-r)*spacing) for r in range(2)})
    for node, (x, y) in coordinates.items():
        ET.SubElement(nodes, 'node', id=node, x=str(x), y=str(y), type='traffic_light' if node in NODES else 'priority')
    pairs = set()
    for node in NODES:
        row, col = int(node[1]), int(node[2])
        for direction in range(4):
            other = adjacent(row, col, direction)
            pairs.update([(node, other), (other, node)])
    for source, target in sorted(pairs):
        ET.SubElement(edges, 'edge', id=edge(source, target), attrib={'from': source, 'to': target},
                      numLanes='1', speed='13.9', priority='1')
    for node in NODES:
        incoming, outgoing = movement_lanes(node)
        for direction in range(4):
            ET.SubElement(connections, 'connection', attrib={'from': incoming[direction][:-2], 'to': outgoing[direction][:-2]},
                          fromLane='0', toLane='0', tl=node, linkIndex=str(direction))
        for program,kind in [('controlled','static'),('actuated','actuated')]:
            logic = ET.SubElement(signals, 'tlLogic', id=node, type=kind, programID=program, offset='0')
            for duration, state in [(30,'GrGr'), (3,'yryr'), (2,'rrrr'), (30,'rGrG'), (3,'ryry'), (2,'rrrr')]:
                phase=ET.SubElement(logic, 'phase', duration=str(duration), state=state)
                if kind=='actuated' and 'G' in state:
                    phase.set('minDur','10');phase.set('maxDur','60')
    for name, root in [('nodes.nod.xml',nodes), ('edges.edg.xml',edges), ('connections.con.xml',connections), ('signals.tll.xml',signals)]:
        write_xml(root,directory/name)
    command = [binary('netconvert'), '--node-files','nodes.nod.xml','--edge-files','edges.edg.xml',
               '--connection-files','connections.con.xml','--tllogic-files','signals.tll.xml',
               '--output-file','network.net.xml','--no-turnarounds','true','--no-warnings','true']
    completed = subprocess.run(command,cwd=directory,capture_output=True,text=True,check=True,timeout=60)
    # Omit tool-generated path/timestamp comments from the committed network.
    ET.register_namespace('xsi','http://www.w3.org/2001/XMLSchema-instance')
    path = directory/'network.net.xml'
    parsed = ET.parse(path)
    parsed.write(path,encoding='utf-8',xml_declaration=True)
    return {'network_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'netconvert_version':subprocess.check_output([binary('netconvert'),'--version'],text=True).splitlines()[0]}


def routes():
    result = {}
    for col in range(2):
        result[f'n{col}'] = [edge(f'n{col}',f'j0{col}'),edge(f'j0{col}',f'j1{col}'),edge(f'j1{col}',f's{col}')]
        result[f's{col}'] = [edge(f's{col}',f'j1{col}'),edge(f'j1{col}',f'j0{col}'),edge(f'j0{col}',f'n{col}')]
    for row in range(2):
        result[f'w{row}'] = [edge(f'w{row}',f'j{row}0'),edge(f'j{row}0',f'j{row}1'),edge(f'j{row}1',f'e{row}')]
        result[f'e{row}'] = [edge(f'e{row}',f'j{row}1'),edge(f'j{row}1',f'j{row}0'),edge(f'j{row}0',f'w{row}')]
    return result


def generate_demand(path,seed,rate=.1,duration=600,profile='tidal'):
    if seed<0 or not 0<rate<=.5 or not 30<=duration<=7200:
        raise ValueError('Invalid demand parameters')
    if profile not in {'tidal','asymmetric'}:
        raise ValueError('Unknown demand profile')
    rng=np.random.default_rng(seed)
    route_map=routes()
    scales={name:float(rng.uniform(.85,1.15)) for name in route_map}
    departures=[]
    for second in range(duration):
        for name in route_map:
            vertical=name[0] in 'ns'
            preferred=vertical==(second<duration//2)
            factor=(1.6 if preferred else .6) if profile=='tidal' else (1.5 if name in {'w0','e0'} else .8)
            if profile=='asymmetric' and duration//3<=second<2*duration//3 and name in {'w0','e0'}:
                factor*=1.4
            mean=rate*factor*scales[name]
            for _ in range(rng.poisson(mean)):
                departures.append((round(second+float(rng.random()),3),name))
    departures.sort()
    root=ET.Element('routes')
    ET.SubElement(root,'vType',id='car',carFollowModel='Krauss',accel='2.6',decel='4.5',sigma='0',
                  tau='1.0',length='5',minGap='2.5',maxSpeed='13.9',speedFactor='1',speedDev='0')
    for name,route in route_map.items():
        ET.SubElement(root,'route',id=name,edges=' '.join(route))
    for i,(depart,name) in enumerate(departures):
        ET.SubElement(root,'vehicle',id=f'v{i:06}',type='car',route=name,depart=f'{depart:.3f}',departLane='0',departSpeed='max')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);write_xml(root,path)
    return {'seed':seed,'rate_per_boundary_per_second':rate,'departure_window_seconds':duration,'profile':profile,
            'scheduled':len(departures),'departures':[t for t,_ in departures],
            'boundary_scales':scales,'route_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
