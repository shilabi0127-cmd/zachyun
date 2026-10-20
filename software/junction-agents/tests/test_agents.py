import copy
import numpy as np
import pytest
from junction_agents.environment import Config,Network,NEIGHBORS,EXTERNAL
from junction_agents.policies import IndependentQ,fixed_time,max_pressure,coordinated
from junction_agents.experiment import train,evaluate


def test_seeded_arrivals_are_shared_and_immutable():
    a,b=Network(12),Network(12)
    assert np.array_equal(a._arrivals,b._arrivals)
    assert not a._arrivals.flags.writeable


def test_flow_conservation_and_capacity_across_random_actions():
    env=Network(13,Config(horizon=100,demand=2.))
    rng=np.random.default_rng(4)
    for _ in range(100):
        before=int(env.queues.sum())
        actions=np.array([rng.choice(np.flatnonzero(m)) for m in env.action_mask()])
        _,_,info=env.step(actions)
        assert before+info['external_demand']==int(env.queues.sum())+info['exited']+info['overflow']
        assert np.all(env.queues>=0) and np.all(env.queues<=env.config.capacity)


def test_phase_change_has_one_all_red_step_and_minimum_green():
    env=Network(0,Config(demand=0,horizon=10));env.queues[:]=8
    with pytest.raises(ValueError,match='minimum green'):env.step(np.ones(4,dtype=int))
    env.step(np.zeros(4,dtype=int));env.step(np.zeros(4,dtype=int))
    before=env.queues.copy()
    _,_,info=env.step(np.ones(4,dtype=int))
    assert np.array_equal(before,env.queues) and info['exited']==0
    assert np.all(env.phase==1) and not env.action_mask()[:,1].any()


def test_maximum_green_forces_a_service_opportunity_for_other_phase():
    env=Network(0,Config(demand=0,max_green=3))
    for _ in range(3):env.step(np.zeros(4,dtype=int))
    assert not env.action_mask()[:,0].any() and env.action_mask()[:,1].all()
    assert max_pressure(env).all()


def test_downstream_capacity_blocks_internal_transfer():
    env=Network(0,Config(demand=0))
    env.queues[0,0]=5
    destination=NEIGHBORS[0,0];env.queues[destination,0]=env.config.capacity
    predicted,_,_,_,info=env.predict(np.zeros(4,dtype=int))
    assert predicted[0,0]==5 and info['blocked']>=2


def test_lookahead_does_not_mutate_environment_or_consult_future():
    env=Network(1);env.elapsed[:]=3;env.queues[:]=4
    before=(env.queues.copy(),env.phase.copy(),env.elapsed.copy(),copy.deepcopy(env.totals))
    agent=IndependentQ()
    action=coordinated(env,agent)
    env._arrivals=np.full_like(env._arrivals,999)  # Future stream must not affect the action.
    assert np.array_equal(action,coordinated(env,agent))
    assert np.array_equal(before[0],env.queues) and np.array_equal(before[1],env.phase)
    assert np.array_equal(before[2],env.elapsed) and before[3]==env.totals


@pytest.mark.parametrize('policy',[fixed_time,max_pressure])
def test_baselines_respect_action_masks(policy):
    env=Network(5,Config(horizon=35,min_green=8))
    while env.t<env.config.horizon:
        action=policy(env)
        assert np.all(env.action_mask()[np.arange(4),action])
        env.step(action)


def test_q_learning_terminal_target_does_not_bootstrap():
    agent=IndependentQ();agent.q[:]=100
    state=np.zeros(4,dtype=int);actions=np.zeros(4,dtype=int)
    agent.update(state,actions,-2,state,np.ones((4,2),dtype=bool),True,alpha=1.)
    assert np.all(agent.q[np.arange(4),state,actions]==-2)


def test_q_learning_masks_invalid_future_action():
    agent=IndependentQ();state=np.zeros(4,dtype=int);nxt=np.ones(4,dtype=int)
    agent.q[:,1,0]=2;agent.q[:,1,1]=999
    mask=np.column_stack([np.ones(4,dtype=bool),np.zeros(4,dtype=bool)])
    agent.update(state,np.zeros(4,dtype=int),1,nxt,mask,False,alpha=1.,gamma=.5)
    assert np.all(agent.q[:,0,0]==2)


def test_training_repeatability_and_seed_split():
    a,b=train(3),train(3)
    assert a['q']==b['q'] and a['history']==b['history']
    with pytest.raises(ValueError,match='overlap'):evaluate(a,episodes=2,seed_start=1)


def test_episode_end_is_explicit():
    env=Network(0,Config(horizon=1))
    assert env.step(np.zeros(4,dtype=int))[1]
    with pytest.raises(RuntimeError):env.step(np.zeros(4,dtype=int))


def test_cli_does_not_replace_zero_episodes_with_default(monkeypatch):
    from junction_agents.__main__ import main
    monkeypatch.setattr('sys.argv',['junction-agents','train','--episodes','0'])
    with pytest.raises(ValueError,match='episodes'):main()
