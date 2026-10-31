"""Numerical checks for the actual ADMM relaxation, not just output shape."""
import numpy as np
import pytest

from backend.lab_core.allocator import (GAMMA, project_capped_simplex, project_local,
                                 solve_relaxation)
from backend.lab_core.models import Config
from backend.lab_core.engine import Engine


def test_simplex_kkt():
    v = np.array([2., -.2, 1.4, .8])
    z = project_capped_simplex(v)
    assert z.min() >= 0
    assert z.sum() == pytest.approx(1)
    active = z > 1e-9
    assert np.ptp((v-z)[active]) < 1e-9
    assert np.all(v[~active] <= (v-z)[active][0])


def test_simplex_leaves_unused_demand():
    np.testing.assert_allclose(project_capped_simplex(np.array([.2, -.3, .1])), [.2, 0, .1])


def test_local_projection_on_known_triangle():
    A, b = np.array([[1., 1.]]), np.array([1.])
    x = project_local(np.array([1., 1.]), A, b, np.ones(2))
    np.testing.assert_allclose(x, [.5, .5], atol=1e-7)


def test_admm_matches_analytic_symmetric_optimum():
    # Two hosts, one task. Strict convexity gives x1=x2=0.5 exactly.
    costs = np.array([[-2.], [-2.]])
    A = [np.ones((1, 1)), np.ones((1, 1))]
    b = [np.ones(1), np.ones(1)]
    x, z, history, converged = solve_relaxation(costs, A, b, np.ones((2,1)), 200, 2, 1e-7)
    assert converged
    np.testing.assert_allclose(x, [[.5],[.5]], atol=1e-6)
    np.testing.assert_allclose(z, x, atol=1e-6)
    assert history[-1]['primal'] < 1e-7


def test_admm_active_resource_constraint_and_capability():
    costs = -np.ones((2, 2))
    A = [np.array([[1., 1.]]), np.array([[1., 1.]])]
    b = [np.array([.5]), np.array([.25])]
    caps = np.array([[1., 0.], [1., 1.]])
    x, z, history, converged = solve_relaxation(costs,A,b,caps,300,2,1e-6)
    assert converged
    assert x[0,1] < 1e-7
    assert x[0].sum() == pytest.approx(.5,abs=1e-6)
    assert x[1].sum() == pytest.approx(.25,abs=1e-6)
    assert np.max(z.sum(axis=0)) <= 1+1e-8


def test_positive_cost_is_deferred():
    x, z, h, converged = solve_relaxation(np.ones((2,2)),[np.ones((1,2))]*2,
                [np.ones(1)]*2,np.ones((2,2)),50,2,1e-7)
    assert converged
    assert np.max(x) == 0


def test_independent_rounding_validates_budget_limited_solver():
    e = Engine(Config(auto_tasks=False, admm_iterations=4))
    for _ in range(12):
        e.add_task(cpu_demand=40, processing_s=20, output_mb=25)
    e.step()
    assert e.validate()
    for sat in e.state.satellites.values():
        assert sat.allocated_cpu <= sat.cpu_capacity-sat.control_cpu+1e-7
    assert e.state.allocator_result.iterations <= 4


def test_random_qps_against_independent_scipy_reference():
    scipy = pytest.importorskip('scipy.optimize')
    rng = np.random.default_rng(42)
    for _ in range(3):
        n,m = 3,4
        costs = -rng.uniform(.2,2,(n,m))
        matrices = [rng.uniform(.1,1,(2,m)) for _ in range(n)]
        budgets = [np.array([.8,.9]) for _ in range(n)]
        caps = np.ones((n,m))
        x,z,h,ok = solve_relaxation(costs,matrices,budgets,caps,600,2,2e-6)
        def objective(flat):
            a=flat.reshape(n,m)
            return np.sum(costs*a)+GAMMA/2*np.sum(a*a)
        def constraint(flat):
            a=flat.reshape(n,m)
            return np.concatenate([1-a.sum(axis=0),*[b-A@a[i] for i,(A,b) in enumerate(zip(matrices,budgets))]])
        ref=scipy.minimize(objective,np.zeros(n*m),method='SLSQP',bounds=[(0,1)]*(n*m),
              constraints=[{'type':'ineq','fun':constraint}],options={'ftol':1e-11,'maxiter':500})
        assert ref.success
        assert ok
        assert abs(objective(x.ravel())-ref.fun)<2e-4
