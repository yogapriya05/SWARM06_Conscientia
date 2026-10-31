"""Independent admission checks and authoritative CPU/storage/energy ledgers."""
import math
import numpy as np
from ..lab_core.resources import thermal_step
from .models import TERMINAL

def processing_duration(sat,task):return max(0,task.processing_cycles-task.progress_cycles)/(sat.cycles_per_s*task.cpu_demand/100)
def capture_start(sat,task,now):
    duration=task.capture_duration_s*task.required_captures
    for a,b in task.visibility_windows.get(sat.id,[]):
        start=max(now,a,task.observation_window[0])
        if start+duration<=min(b,task.observation_window[1])+1e-8:return start
    return None

def task_energy_wh(sat,task):
    capture=task.capture_duration_s*task.required_captures
    duration=processing_duration(sat,task)
    # No solar credit. Baseline through predicted delivery plus payload and radio.
    horizon=capture+duration+20
    return ((8+.45*(sat.control_cpu+sat.stress_cpu+sat.allocated_cpu))*horizon+12*capture+.45*task.cpu_demand*duration)/3600+task.output_data_mb*.006

def can_host(state,sat,task):
    c=state.config
    if not sat.can_observe:return False,'payload/processor/health unavailable',None
    if state.time_s-sat.last_telemetry_s>c.stale_after_s:return False,'stale sensor telemetry',None
    if task.allowed_satellites and sat.id not in task.allowed_satellites:return False,'host restriction',None
    if sat.attitude_error_deg>5:return False,'attitude not oriented',None
    start=capture_start(sat,task,state.time_s)
    if start is None:return False,'no explicit target visibility window',None
    if task.minimum_quality>.96:return False,'minimum quality unavailable',None
    if sat.free_cpu+1e-8<task.cpu_demand:return False,'CPU reservation',None
    size=task.raw_data_mb+task.output_data_mb
    if sat.free_storage_mb+1e-8<size:return False,'raw + output storage reservation',None
    if sat.battery_wh-task_energy_wh(sat,task)<c.reserve_wh+.2:return False,'safe energy reserve',None
    horizon=max(1,start-state.time_s+task.capture_duration_s*task.required_captures+processing_duration(sat,task))
    temp=thermal_step(sat.temperature_c,sat.control_cpu+sat.stress_cpu+sat.allocated_cpu+task.cpu_demand,True,horizon,sat.cooling_scale,sat.extra_heat_w+sat.solar_heat_w)
    if temp>c.thermal_limit_c-2:return False,'thermal forecast',None
    ready=start+task.capture_duration_s*task.required_captures+processing_duration(sat,task)+2
    from .network import earliest_route
    route=earliest_route(state,sat.id,task.output_data_mb,ready,task.delivery_deadline)
    if route is None:return False,'no predicted contact path by deadline',None
    baseline=(8+.45*(sat.control_cpu+sat.stress_cpu+sat.allocated_cpu))*max(0,route['arrival_s']-state.time_s)/3600
    if sat.battery_wh-task_energy_wh(sat,task)-baseline<c.reserve_wh+.2:return False,'delivery horizon energy reserve',None
    return True,'complete chain feasible',dict(capture_start_s=start,ready_s=ready,route=route,energy_wh=task_energy_wh(sat,task))

def ledgers(state):
    for sat in state.satellites.values():
        sat.allocated_cpu=sat.storage_used_mb=sat.storage_reserved_mb=0.
    for task in state.active_tasks():
        if task.status=='assigned' and task.owner:
            sat=state.satellites[task.owner]
            sat.allocated_cpu+=task.cpu_demand
            sat.storage_reserved_mb+=task.raw_data_mb+task.output_data_mb
        elif task.status=='captured' and task.holder:
            sat=state.satellites[task.holder];sat.storage_used_mb+=task.raw_data_mb
            sat.storage_reserved_mb+=task.output_data_mb
            if sat.can_compute:sat.allocated_cpu+=task.cpu_demand
        elif task.status=='processed' and task.holder:
            state.satellites[task.holder].storage_used_mb+=task.output_data_mb
        if task.receiver and task.receiver!='GND':state.satellites[task.receiver].storage_reserved_mb+=task.output_data_mb

def resource_rows(state,sat,tasks):
    cpu=np.array([t.cpu_demand/100 for t in tasks]); storage=np.array([(t.raw_data_mb+t.output_data_mb)/sat.storage_capacity_mb for t in tasks])
    energy=np.array([task_energy_wh(sat,t)/sat.battery_capacity_wh for t in tasks])
    return np.array([cpu,storage,energy]),np.array([sat.free_cpu/100,sat.free_storage_mb/sat.storage_capacity_mb,max(0,sat.battery_wh-state.config.reserve_wh)/100])

def update_physics(state,dt):
    for sat in state.satellites.values():
        sat.actual_cpu=min(100,sat.control_cpu+sat.stress_cpu+sat.allocated_cpu) if 'offline' not in sat.faults else 2.
        sat.power_w=8+.45*sat.actual_cpu+sat.extra_drain_w
        # Payload acquisition and radio operations are charged by engine as additional energy.
        before=sat.battery_wh
        delta=(.9*sat.solar_w-sat.power_w)*dt/3600
        sat.battery_wh=max(0,min(100,before+delta))
        predicted=thermal_step(sat.temperature_c,sat.actual_cpu,False,dt,sat.cooling_scale,sat.solar_heat_w)
        actual=thermal_step(sat.temperature_c,sat.actual_cpu,False,dt,sat.cooling_scale,sat.extra_heat_w+sat.solar_heat_w)
        sat.telemetry_residual_c=actual-predicted+state.rng.gauss(0,.02)
        sat.temperature_c=actual
        state.counters['energy_used_wh']+=sat.power_w*dt/3600
        if not {'offline','stale'} & sat.faults.keys():sat.last_telemetry_s=state.time_s
