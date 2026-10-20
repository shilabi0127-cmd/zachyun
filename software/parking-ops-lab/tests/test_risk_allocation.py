import itertools
import math
from types import SimpleNamespace

import numpy as np
import pytest

from parkinglab import allocation
from parkinglab.domain import Reservation, ExperimentConfig, ExperimentRequest, to_csv, parse_csv
from parkinglab.risk import difference_positive, risk_matrix, assigned_risk_bounds, tolerance, recommended_gap
from parkinglab.simulation import run_experiment
from parkinglab.optimizer import greedy


def booking(id,start,end,**kwargs):
    return Reservation(id=id,start=start,end=end,**kwargs)


@pytest.mark.parametrize('distribution',['normal','uniform'])
def test_pair_probability_against_independent_monte_carlo(distribution):
    rows=[booking('a',0,35),booking('b',42,70,arrival_std=6,departure_std=7)]
    model=risk_matrix(rows,distribution)
    rng=np.random.default_rng(42);size=150000
    def draw(mean,std):
        return rng.normal(mean,std,size) if distribution=='normal' else mean+rng.uniform(-math.sqrt(3),math.sqrt(3),size)*std
    a,b=rows
    sa=draw(a.start+a.arrival_mean,a.arrival_std)
    sb=draw(b.start+b.arrival_mean,b.arrival_std)
    ea=draw(a.end+a.departure_mean,a.departure_std)
    eb=draw(b.end+b.departure_mean,b.departure_std)
    actual=np.mean((sa<eb)&(sb<ea))
    assert abs(actual-model['raw'][0,1])<.005
    assert model['upper'][0,1]>=model['raw'][0,1]


def test_uniform_difference_known_triangular_distribution():
    std=1/math.sqrt(3)
    assert difference_positive(0,std,0,std,'uniform')==pytest.approx(.5)
    assert difference_positive(1,std,0,std,'uniform')==pytest.approx(.875)
    assert difference_positive(2,std,0,std,'uniform')==1
    assert difference_positive(0,0,0,0,'uniform')==0
    assert difference_positive(1,0,0,0,'normal')==1


@pytest.mark.parametrize('distribution',['normal','uniform'])
def test_repair_allowance_bounds_actual_clamped_overlap(distribution):
    rows=[booking('a',0,5,arrival_std=12,departure_std=12),booking('b',15,20,arrival_std=10,departure_std=10)]
    request=ExperimentRequest(reservations=rows,config=ExperimentConfig(slots=1,trials=3000,deviation_distribution=distribution,time_limit=1))
    result=run_experiment(request)
    nominal=result['policies']['nominal_milp']
    assert result['clamped_realizations']>0
    assert nominal['conflict_rate']<=nominal['risk_pairs'][0]['overlap_probability_upper_bound']+.02


@pytest.mark.parametrize('objective',['weighted_admission','revenue'])
@pytest.mark.parametrize('distribution',['normal','uniform'])
def test_risk_milp_matches_exhaustive_bay_assignments(objective,distribution):
    rows=[booking('a',0,30,fee=7,priority=2),booking('b',15,40,fee=3,priority=1),
          booking('c',40,65,fee=9,priority=4),booking('d',55,90,fee=6),booking('e',75,100,fee=5)]
    config=ExperimentConfig(slots=2,objective=objective,deviation_distribution=distribution,time_limit=5)
    model=risk_matrix(rows,distribution);best=0
    for bays in itertools.product(range(3),repeat=len(rows)):
        assignments={i:bay for i,bay in enumerate(bays) if bay}
        upper=assigned_risk_bounds(assignments,model['upper'],len(rows))
        if all(upper[i]<=tolerance(rows[i],config.risk_budget) for i in assignments):
            best=max(best,sum(rows[i].priority if objective=='weighted_admission' else rows[i].fee for i in assignments))
    solution=allocation.optimize_risk(rows,config,model)
    assert solution['optimal']
    assert solution['objective_value']==best
    assert solution['objective_upper_bound']==pytest.approx(best)


def test_individual_budget_overrides_priority_default_and_csv_roundtrips():
    rows=[booking('a',0,30,failure_tolerance=.025),booking('b',35,60,priority=4)]
    assert parse_csv(to_csv(rows))==rows
    assert tolerance(rows[0],.1)==.025
    assert tolerance(rows[1],.1)==.05


def test_fcfs_uses_submission_order_not_scheduled_start():
    rows=[booking('later_arrival_first_booking',20,60,booking_order=1),
          booking('earlier_arrival_later_booking',0,30,booking_order=2)]
    assert greedy(rows,1)['selected']==[0]
    swapped=[rows[0].model_copy(update={'booking_order':3}),rows[1]]
    assert greedy(swapped,1)['selected']==[1]


def test_time_limit_without_solver_incumbent_keeps_verified_feasible_allocation(monkeypatch):
    rows=[booking('a',0,30),booking('b',40,70),booking('c',80,110)]
    monkeypatch.setattr(allocation,'milp',lambda *args,**kwargs:SimpleNamespace(status=1,x=None,message='time limit',mip_dual_bound=None))
    result=allocation.optimize_risk(rows,ExperimentConfig(slots=1))
    bounds=assigned_risk_bounds(result['assignments'],risk_matrix(rows)['upper'],len(rows))
    assert result['solution_source']=='verified_greedy_fallback'
    assert not result['optimal'] and result['gap'] is None
    assert result['selected']
    assert all(bounds[i]<=.1 for i in result['selected'])


@pytest.mark.parametrize('distribution',['normal','uniform'])
def test_directional_buffer_matches_requested_tail_probability(distribution):
    a,b=booking('a',0,30),booking('b',40,70)
    gap=recommended_gap(a,b,.05,distribution)
    assert difference_positive(a.departure_mean,a.departure_std,gap+b.arrival_mean,b.arrival_std,distribution)==pytest.approx(.05)
