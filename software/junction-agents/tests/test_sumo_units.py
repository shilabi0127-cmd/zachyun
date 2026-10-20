import hashlib
import xml.etree.ElementTree as ET
import numpy as np
import pytest
from junction_agents.sumo_scenarios import NODES, adjacent, generate_demand, movement_lanes, routes
from junction_agents.sumo_backend import signal_binding, trip_metrics
from junction_agents.sumo_signals import SignalAudit
from junction_agents.sumo_benchmark import validate_timing


def test_changed_protocol_timing_cannot_be_silently_ignored():
    protocol = {'decision_interval_seconds': 5, 'yellow_seconds': 3,
                'all_red_seconds': 2, 'minimum_green_seconds': 10,
                'maximum_green_seconds': 60}
    validate_timing(protocol)
    protocol['yellow_seconds'] = 4
    with pytest.raises(ValueError, match='yellow_seconds'):
        validate_timing(protocol)


def binding():
    incoming,outgoing=movement_lanes('j00')
    # Deliberately noncanonical signal index order.
    links=[[(incoming[d],outgoing[d],'internal')] for d in [3,0,1,2]]
    return signal_binding('j00',links)


def test_signal_indices_come_from_controlled_links():
    result=binding()
    assert result['green']==['rGrG','GrGr']
    assert result['yellow']==['ryry','yryr']


def test_unsupported_turns_fail_before_control():
    incoming,outgoing=movement_lanes('j00')
    links=[[(incoming[d],outgoing[d],'internal')] for d in range(4)]
    links[0]=[(incoming[0],outgoing[1],'internal')]
    with pytest.raises(ValueError,match='straight'):signal_binding('j00',links)


def test_demand_is_byte_reproducible_and_departure_sorted(tmp_path):
    a,b=tmp_path/'a.xml',tmp_path/'b.xml'
    x=generate_demand(a,23,duration=60)
    y=generate_demand(b,23,duration=60)
    assert a.read_bytes()==b.read_bytes() and x==y
    assert x['departures']==sorted(x['departures'])
    vehicles=ET.parse(a).getroot().findall('vehicle')
    assert len(vehicles)==x['scheduled']
    assert x['route_sha256']==hashlib.sha256(a.read_bytes()).hexdigest()


def test_different_profiles_produce_distinct_heldout_inputs(tmp_path):
    a=generate_demand(tmp_path/'a.xml',2,duration=90)
    b=generate_demand(tmp_path/'b.xml',2,duration=90,profile='asymmetric')
    assert a['route_sha256']!=b['route_sha256']
    assert all(len(route)==3 for route in routes().values())


def test_valid_clearance_and_observed_green_metrics():
    b=binding();audit=SignalAudit({'j00':b})
    audit.observe(0,{'j00':b['green'][0]})
    audit.observe(10,{'j00':b['yellow'][0]})
    audit.observe(13,{'j00':b['red']})
    audit.observe(15,{'j00':b['green'][1]})
    assert audit.metrics(20)['minimum_green_before_switch_seconds']==10
    assert audit.metrics(20)['signal_audit_violations']==0


@pytest.mark.parametrize('event_time',[1,9,61])
def test_green_time_violation_is_detected(event_time):
    b=binding();audit=SignalAudit({'j00':b});audit.observe(0,{'j00':b['green'][0]})
    with pytest.raises(RuntimeError):audit.observe(event_time,{'j00':b['yellow'][0]})


def test_direct_conflicting_green_change_is_rejected():
    b=binding();audit=SignalAudit({'j00':b});audit.observe(0,{'j00':b['green'][0]})
    with pytest.raises(RuntimeError):audit.observe(20,{'j00':b['green'][1]})


@pytest.mark.parametrize('red_time,green_time',[(12,15),(13,14),(13,16)])
def test_short_or_long_clearance_is_rejected(red_time,green_time):
    b=binding();audit=SignalAudit({'j00':b});audit.observe(0,{'j00':b['green'][0]})
    audit.observe(10,{'j00':b['yellow'][0]})
    with pytest.raises(RuntimeError):
        audit.observe(red_time,{'j00':b['red']})
        audit.observe(green_time,{'j00':b['green'][1]})


def test_unfinished_trip_is_not_averaged_as_completed(tmp_path):
    path=tmp_path/'trips.xml'
    path.write_text('<tripinfos><tripinfo arrival="10" timeLoss="4" duration="10" waitingTime="2" departDelay="1"/><tripinfo arrival="-1" timeLoss="999"/></tripinfos>')
    result=trip_metrics(path)
    assert result['tripinfo_unfinished']==1 and result['tripinfo_completed']==1
    assert result['completed_mean_time_loss_seconds']==4
