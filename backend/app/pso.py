"""Bounded local-repair PSO reused from Swarm Lab; greedy is always an incumbent."""
import copy,time
from ..lab_core.pso import _search
from .resources import can_host

def repair_placements(state,tasks,rankings):
    tasks=tasks[:8]
    if not tasks:return {},{}
    # Freeze feasible candidates once; decode only resource ledgers inside 78 evaluations.
    feasible={t.task_id:[s for s in rankings[t.task_id] if can_host(state,s,t)[0]] for t in tasks}
    def evaluate(keys):
        led={s.id:[s.free_cpu,s.free_storage_mb,s.battery_wh-state.config.reserve_wh] for s in state.satellites.values()}
        proposal={};score=0.
        from .resources import task_energy_wh
        for j,t in enumerate(tasks):
            candidates=feasible[t.task_id]
            if not candidates:continue
            first=min(len(candidates)-1,int(keys[j]*len(candidates)))
            for sat in candidates[first:]+candidates[:first]:
                cpu,storage,energy=led[sat.id]; need=t.raw_data_mb+t.output_data_mb;wh=task_energy_wh(sat,t)
                if cpu>=t.cpu_demand and storage>=need and energy>=wh+.2:
                    led[sat.id]=[cpu-t.cpu_demand,storage-need,energy-wh]
                    proposal[t.task_id]=sat.id;score+=10*t.priority+state.allocator['fractions'][t.task_id][sat.id];break
        return score,proposal
    start=time.perf_counter()
    proposal,stats=_search(len(tasks),evaluate,state.config.seed+state.tick,state.config.pso_particles,state.config.pso_iterations)
    return proposal or {},stats|{'runtime_ms':(time.perf_counter()-start)*1000,'scope_tasks':len(tasks)}

def choose_route(state,candidates):
    if not candidates:return None
    def evaluate(keys):
        route=candidates[min(len(candidates)-1,int(keys[0]*len(candidates)))];return -(route['arrival_s']-state.time_s+2*route['cost']),route
    route,stats=_search(1,evaluate,state.config.seed+state.tick,state.config.pso_particles,state.config.pso_iterations)
    state.repair=stats|{'scope':'contact-route alternatives'}
    return route
