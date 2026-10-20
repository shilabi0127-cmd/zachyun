"""Runs the actual simulator when explicitly enabled, never a mocked SUMO."""
import os
import pytest
from junction_agents.sumo_scenarios import build_network,generate_demand
from junction_agents.sumo_backend import run_episode

pytestmark=[pytest.mark.sumo,pytest.mark.skipif(os.environ.get('RUN_SUMO_TESTS')!='1',reason='Set RUN_SUMO_TESTS=1 and install requirements-sumo.txt')]


@pytest.mark.parametrize('policy',['fixed_time','sumo_actuated','pressure','joint_rollout','cem'])
def test_actual_sumo_controller_accounting(tmp_path,policy):
    build_network(tmp_path/'network')
    route=tmp_path/'demand.rou.xml'
    demand=generate_demand(route,200003,rate=.08,duration=60)
    result=run_episode(tmp_path/'network/network.net.xml',route,demand,policy,tmp_path/policy,end_seconds=180)
    assert result['scheduled']==result['arrived']+result['running_at_end']+result['pending_insertion_at_end']
    assert result['signal_audit_violations']==0 and result['teleport_starts']==0
    assert result['collision_vehicle_reports']==0
    assert result['maximum_green_observed_seconds']<=60
    assert result['minimum_green_before_switch_seconds']>=10
    assert result['route_sha256']==demand['route_sha256']
