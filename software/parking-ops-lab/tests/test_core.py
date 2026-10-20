import itertools
import numpy as np
import pytest
from parkinglab.domain import Reservation, ExperimentConfig, ExperimentRequest, parse_csv, to_csv, sample_reservations
from parkinglab.optimizer import optimize, protected_windows, color_intervals
from parkinglab.simulation import conflict_mask, run_experiment, evaluate


def row(id="a", start=0, end=30, **kw):
    return Reservation(id=id,start=start,end=end,**kw)


def test_csv_roundtrip():
    rows=sample_reservations(7)
    assert parse_csv(to_csv(rows))==rows
    assert parse_csv('id,start,end\na,08:00,09:15')[0].end==555


@pytest.mark.parametrize('text',[
    'id,start,end\na,0,30\na,30,60',
    'id,start,end\na,10,9',
    'id,start,end\na,24:01,25:00',
    'id,start,end\n=cmd,0,30',
    'id,start,end,fee\na,0,30,nan',
    'id,start,start,end\na,0,0,30',
    'id,start,end\na,0,30,extra',
    'id,start,end',
])
def test_reject_invalid_csv(text):
    with pytest.raises(ValueError): parse_csv(text)


def test_half_open_coloring():
    assert color_intervals([0,1],[(0,30),(30,60)],1)=={0:1,1:1}
    with pytest.raises(RuntimeError):color_intervals([0,1],[(0,31),(30,60)],1)


@pytest.mark.parametrize('objective',['weighted_admission','revenue'])
@pytest.mark.parametrize('buffered',[False,True])
def test_solver_matches_brute_force(objective,buffered):
    rows=[row('a',0,40,priority=1,fee=10),row('b',10,45,priority=4,fee=2),row('c',45,80,priority=2,fee=8),row('d',0,80,priority=8,fee=3)]
    config=ExperimentConfig(slots=1,objective=objective)
    windows=protected_windows(rows,config.risk_budget,buffered)
    values=[r.priority if objective=='weighted_admission' else r.fee for r in rows]
    expected=0
    for flags in itertools.product([0,1],repeat=len(rows)):
        valid=all(sum(flags[i] for i,(s,e) in enumerate(windows) if s<=t<e)<=config.slots for t,_ in windows)
        if valid:expected=max(expected,sum(v*f for v,f in zip(values,flags)))
    result=optimize(rows,config,buffered)
    assert result['optimal']
    assert sum(values[i] for i in result['selected'])==expected


def test_conservative_windows():
    rows=sample_reservations(30)
    loose=protected_windows(rows,.2,True)
    strict=protected_windows(rows,.01,True)
    assert all(a[0]<=b[0] and a[1]>=b[1] for a,b in zip(strict,loose))
    cfg=ExperimentConfig(slots=3)
    nominal=optimize(rows,cfg)
    buffered=optimize(rows,cfg,True)
    assert sum(rows[i].priority for i in buffered['selected'])<=sum(rows[i].priority for i in nominal['selected'])


def test_conflict_mask_matches_pairwise_reference():
    rng=np.random.default_rng(13)
    starts=rng.integers(0,60,size=(100,15)).astype(float)
    ends=starts+rng.integers(1,20,size=(100,15))
    actual=conflict_mask(starts,ends)
    expected=np.zeros_like(actual)
    for t in range(100):
        for i in range(15):
            expected[t,i]=any(i!=j and starts[t,i]<ends[t,j] and starts[t,j]<ends[t,i] for j in range(15))
    assert np.array_equal(actual,expected)


def test_deterministic_feasible_schedule_no_conflicts():
    rows=[row('a',0,30,arrival_mean=0,arrival_std=0,departure_mean=0,departure_std=0),row('b',30,60,arrival_mean=0,arrival_std=0,departure_mean=0,departure_std=0)]
    result=run_experiment(ExperimentRequest(reservations=rows,config=ExperimentConfig(slots=1,trials=50)))
    assert all(p['conflict_rate']==0 for p in result['policies'].values())
    assert all(p['accepted']==2 for p in result['policies'].values())


def test_reproducible_seed():
    req=ExperimentRequest(reservations=sample_reservations(12),config=ExperimentConfig(trials=50))
    a,b=run_experiment(req),run_experiment(req)
    assert a['scenario_hash']==b['scenario_hash']
    assert a['scenario_hash']==run_experiment(ExperimentRequest.model_validate_json(req.model_dump_json()))['scenario_hash']
    for key in a['policies']:
        for metric in ['accepted_weight','conflict_rate','mc_95_bound','schedule']:
            assert a['policies'][key][metric]==b['policies'][key][metric]


def test_empty_acceptance_not_zero_risk():
    rows=[row()];config=ExperimentConfig(trials=50)
    result=evaluate(rows,config,{'selected':[],'assignments':{},'windows':[(0,30)],'status':'optimal','optimal':True,'gap':0,'runtime_ms':0},np.zeros((50,1)),np.ones((50,1)))
    assert result['conflict_rate'] is None and result['mc_95_bound'] is None
