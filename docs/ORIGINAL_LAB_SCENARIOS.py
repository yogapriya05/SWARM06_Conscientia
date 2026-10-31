"""Deterministic integration evidence. Run from the extracted project directory."""
from __future__ import annotations

import json
import platform
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from swarm_sim.engine import Engine
from swarm_sim.models import Config, TaskStatus
from swarm_sim.network import pair_key


def run_case(name, engine, steps, inject=None, finish=None):
    start=perf_counter()
    plans=[]
    min_battery=100
    max_storage=0
    for k in range(steps):
        if inject:inject(k,engine)
        previous=engine.state.allocator_result
        engine.step()
        engine.validate()
        if previous is not engine.state.allocator_result:
            a=engine.state.allocator_result
            plans.append({'runtime_ms':a.runtime_ms,'rounds':a.iterations,
                          'converged':a.converged,'primal':a.primal_residual,'dual':a.dual_residual})
        min_battery=min(min_battery,*[s.battery_wh for s in engine.state.satellites.values()])
        max_storage=max(max_storage,*[s.storage_used_mb+s.storage_reserved_mb for s in engine.state.satellites.values()])
    if finish:finish(engine)
    metrics=engine.snapshot()['metrics']
    return dict(name=name,passed=True,nodes=len(engine.state.satellites),ticks=steps,
                simulated_s=engine.state.time_s,wall_s=perf_counter()-start,
                accounting_checks=steps,min_battery_wh=min_battery,
                max_storage_with_reservations_mb=max_storage,metrics=metrics,
                planner_calls=len(plans),plans=plans,
                events=[dict(time_s=e.time_s,category=e.category,node=e.node_id,message=e.message)
                        for e in engine.state.events if e.category in ('fault','repair','route','recovery')])


def require(condition,message):
    if not condition:raise AssertionError(message)


def main():
    results=[]
    for nodes in (6,20):
        e=Engine(Config(nodes=nodes,auto_tasks=False))
        results.append(run_case(f'nominal_{nodes}',e,80,finish=lambda e:require(
            e.snapshot()['metrics']['completed']==4,'initial products must all be delivered')))
        e=Engine(Config(nodes=nodes))
        def faults(k,e):
            if k==15:
                owner=next((t.owner for t in e.state.tasks.values() if t.status==TaskStatus.RUNNING),'S2')
                e.inject(owner,'offline',duration_s=20)
            if k==60:e.set_stress('S3',cpu_pct=100,cooling_scale=.2)
            if k==100:e.recover('S3')
            if k==160:e.inject('S5','stale',duration_s=12)
            if k==240:e.state.config.auto_tasks=False
        results.append(run_case(f'dynamic_faults_{nodes}',e,300,faults,finish=lambda e:require(
            e.snapshot()['metrics']['completed']==len(e.state.tasks),'all admitted campaigns must drain')))
    e=Engine(Config(auto_tasks=False),seed_tasks=False)
    t=e.add_task(processing_s=2,output_mb=20,allowed_satellites=['S2'])
    def relay(k,e):
        if k==2:
            require(t.route is not None,'route must exist before injection')
            h=t.route.hops[0]
            e.state.blocked_links.add(pair_key(h.source,h.target));e._reconcile()
    results.append(run_case('relay_link_loss',e,70,relay,finish=lambda e:require(
        t.status==TaskStatus.COMPLETED and t.attempts==1 and e.state.counters['reroutes']>0,
        'existing product must reroute without recapture')))
    e=Engine(Config(auto_tasks=False),seed_tasks=False)
    t=e.add_task(processing_s=2,allowed_satellites=['S2'])
    def holder(k,e):
        if k==1:e.inject('S2','offline')
        if k==10:
            require(t.holder=='S2' and t.attempts==1,'data must remain on failed holder')
            e.recover('S2')
    results.append(run_case('failed_holder_recovery',e,70,holder,finish=lambda e:require(
        t.status==TaskStatus.COMPLETED and t.attempts==1,'retained product must deliver after holder recovery')))
    e=Engine(Config(auto_tasks=False),seed_tasks=False)
    e.set_stress('S2',cpu_pct=100,cooling_scale=.2)
    results.append(run_case('cpu_to_thermal_failure',e,25,finish=lambda e:require(
        'thermal protection' in e.state.satellites['S2'].reasons,'CPU heat must trigger protection')))
    e=Engine(Config(auto_tasks=False),seed_tasks=False)
    e.set_stress('S2',heat_w=20)
    results.append(run_case('residual_cusum',e,5,finish=lambda e:require(
        'S2' in e.monitor.latched,'unmodelled heating must trip CUSUM')))
    e=Engine(Config(auto_tasks=False),seed_tasks=False)
    for node in e.state.satellites:e.inject(node,'offline')
    t=e.add_task(deadline_after_s=8)
    results.append(run_case('no_feasible_hosts',e,10,finish=lambda e:require(
        t.status==TaskStatus.MISSED and t.attempts==0,'infeasible task must expire without execution')))
    output=Path('evidence');output.mkdir(exist_ok=True)
    evidence={'python':platform.python_version(),'platform':platform.system(),
              'versions':{name:version(name) for name in ('numpy','fastapi','pydantic','uvicorn','pytest','httpx','scipy')},
              'seed':7,'cases':results,'all_passed':all(r['passed'] for r in results)}
    (output/'scenarios.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    for r in results:
        m=r['metrics']
        print(f"PASS {r['name']:26} nodes={r['nodes']:2} ticks={r['ticks']:3} "
              f"delivered={m['completed']:2} missed={m['missed']:2} "
              f"reassignments={m['reassignments']} reroutes={m['reroutes']}")
    print(f"All {len(results)} scenarios passed; {sum(r['accounting_checks'] for r in results)} tick-level invariant checks.")


if __name__=='__main__':main()
