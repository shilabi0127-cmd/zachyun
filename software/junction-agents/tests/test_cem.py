from copy import copy
import numpy as np
import pytest
from junction_agents.environment import Network,Config
from junction_agents.cem import CEMConfig,CEMPlanner,rollout_batch


def scalar_reference(env,plan,discount=.95):
    simulation=copy(env);score=0;executed=[]
    for step,requested in enumerate(plan):
        actions=np.where(simulation.elapsed>=simulation.config.max_green,1,
                         np.where(simulation.elapsed<simulation.config.min_green,0,requested))
        queues,phase,elapsed,_,info=simulation.predict(actions)
        score+=(discount**step)*(np.square(queues.astype(float)).sum()/env.config.capacity
                    +.5*info['switches']+2*info['blocked']-.1*info['exited'])
        simulation.queues,simulation.phase,simulation.elapsed=queues,phase,elapsed
        executed.append(actions)
    return score,simulation.queues,np.array(executed)


def test_vectorized_rollouts_match_scalar_environment():
    rng=np.random.default_rng(5)
    env=Network(6)
    env.queues=rng.integers(0,env.config.capacity+1,size=(4,4))
    env.phase=rng.integers(0,2,size=4)
    env.elapsed=np.array([0,2,11,12])
    plans=rng.integers(0,2,size=(24,6,4))
    result=rollout_batch(env,plans)
    for i,plan in enumerate(plans):
        score,queues,executed=scalar_reference(env,plan)
        assert np.isclose(result['scores'][i],score)
        assert np.array_equal(result['queues'][i],queues)
        assert np.array_equal(result['executed'][i],executed)
    assert np.all(result['queues']>=0) and np.all(result['queues']<=env.config.capacity)


def test_sampling_keeps_incumbent_and_returns_feasible_action():
    env=Network(3);env.queues[:]=7;env.elapsed[:]=4
    planner=CEMPlanner(12,CEMConfig(population=8,elite=2,iterations=2))
    action=planner.actions(env)
    assert np.all(env.action_mask()[np.arange(4),action])
    assert planner.last_diagnostics['selected_plan_cost']<=planner.last_diagnostics['seed_plan_cost']+1e-10
    assert np.all(planner.probabilities>=.03) and np.all(planner.probabilities<=.97)


def test_planner_does_not_use_future_arrivals():
    env=Network(2);env.queues[:]=3;env.elapsed[:]=4
    a=CEMPlanner(10,CEMConfig(population=8,elite=2,iterations=2))
    action=a.actions(env)
    env._arrivals=np.full_like(env._arrivals,10000)
    b=CEMPlanner(10,CEMConfig(population=8,elite=2,iterations=2))
    assert np.array_equal(action,b.actions(env))
    assert a.last_diagnostics['selected_plan_cost']==b.last_diagnostics['selected_plan_cost']


def test_planning_preserves_current_queue_and_phase():
    env=Network(1);env.queues[:]=6;env.elapsed[:]=3
    before=(env.queues.copy(),env.phase.copy(),env.elapsed.copy())
    CEMPlanner(5,CEMConfig(population=8,elite=2,iterations=1)).actions(env)
    assert all(np.array_equal(a,b) for a,b in zip(before,(env.queues,env.phase,env.elapsed)))


def test_warm_started_episode_is_repeatable():
    def episode():
        env=Network(4,Config(horizon=15))
        planner=CEMPlanner(2,CEMConfig(population=8,elite=2,iterations=1))
        actions=[]
        for _ in range(15):
            action=planner.actions(env);actions.append(action);env.step(action)
        return actions,env.metrics()
    a,am=episode();b,bm=episode()
    assert np.array_equal(a,b) and am==bm


@pytest.mark.parametrize('kwargs',[{'population':0},{'elite':99},{'horizon':1},{'smoothing':0},{'iterations':0}])
def test_invalid_budget_is_rejected(kwargs):
    with pytest.raises(ValueError):CEMConfig(**kwargs)


def test_rollout_input_shape_and_type():
    env=Network(0)
    with pytest.raises(ValueError):rollout_batch(env,np.zeros((5,4),dtype=int))
    with pytest.raises(ValueError):rollout_batch(env,np.ones((5,4,4))*.5)
