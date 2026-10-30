from backend.app.allocator import allocate
from backend.app.engine import SimulationEngine
from backend.app.failures import apply_failure
from backend.app.models import Satellite, Task, TaskStatus
from backend.app.pso import repair_allocation


def test_six_satellites_and_allocation():
    engine = SimulationEngine()
    assert len(engine.state.satellites) == 6
    result = engine.submit_tasks([Task("t1", 10)])
    assert result[0].feasible and engine.state.tasks[0].assigned_satellite


def test_failure_isolates_and_requeues():
    sats = [Satellite("a", (0, 0, 0)), Satellite("b", (1, 0, 0))]
    task = Task("t", 5)
    allocate([task], sats)
    apply_failure(sats, [task], task.assigned_satellite)
    assert task.status == TaskStatus.PENDING


def test_pso_preserves_locked_prefix():
    sats = [Satellite("a", (0, 0, 0)), Satellite("b", (1, 0, 0))]
    tasks = [Task("a", 5, assigned_satellite="a"), Task("b", 5)]
    tasks[0].status = TaskStatus.ALLOCATED
    result = repair_allocation(tasks, sats, locked_prefix=1)
    assert result[0].satellite_id == "a"


def test_step_charges_in_sunlight():
    engine = SimulationEngine()
    before = engine.state.satellites[0].battery_wh
    engine.step()
    assert engine.state.satellites[0].battery_wh >= before
