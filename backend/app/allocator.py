"""Swarm Lab ADMM relaxation, then independent integer feasibility reconstruction."""
import time
import numpy as np
from ..lab_core.allocator import solve_relaxation
from .resources import can_host,resource_rows

def allocate(state,tasks):
    started=time.perf_counter(); sats=list(state.satellites.values()); n,m=len(sats),len(tasks)
    costs=np.zeros((n,m)); caps=np.zeros((n,m)); matrices=[];budgets=[]; feasible={}
    for i,sat in enumerate(sats):
        A,b=resource_rows(state,sat,tasks);matrices.append(A);budgets.append(b)
        for j,task in enumerate(tasks):
            ok,reason,plan=can_host(state,sat,task);feasible[(task.task_id,sat.id)]=(ok,reason,plan)
            caps[i,j]=float(ok and sat.id in task.shared_with)
            cost=.5*(1-sat.battery_wh/100)+.35*(sat.allocated_cpu+sat.stress_cpu)/100+.2*max(0,sat.temperature_c-40)/30
            if plan:cost+=.04*plan['route']['cost']+.2*plan['energy_wh']+.15*(plan['route']['arrival_s']-state.time_s)/max(1,task.delivery_deadline-state.time_s)
            costs[i,j]=cost-(1.2+.5*task.priority)
    x,z,h,converged=solve_relaxation(costs,matrices,budgets,caps,iterations=20,rho=2,tolerance=.01)
    result=dict(iterations=len(h),converged=bool(converged),history=h,
        primal_residual=h[-1]['primal'] if h else 0,dual_residual=h[-1]['dual'] if h else 0,
        runtime_ms=(time.perf_counter()-started)*1000,
        local_constraint_violation=max([max(0,float(np.max(A@row-b,initial=0))) for A,b,row in zip(matrices,budgets,x)] or [0.]),
        fractions={t.task_id:{s.id:float(z[i,j]) for i,s in enumerate(sats)} for j,t in enumerate(tasks)},
        costs={t.task_id:{s.id:float(costs[i,j]) for i,s in enumerate(sats)} for j,t in enumerate(tasks)},
        message_scalars=3*n*m*len(h))
    state.allocator=result
    rankings={t.task_id:sorted(sats,key=lambda s:(-result['fractions'][t.task_id][s.id],result['costs'][t.task_id][s.id],s.id)) for t in tasks}
    return rankings,result
