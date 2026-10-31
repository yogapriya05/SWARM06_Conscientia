"""Capability-specific isolation, stale timestamps, CUSUM and fresh-sample recovery."""
from ..lab_core.failures import CUSUM
FAULT_KINDS={'offline','cpu','radio','thermal','battery','stale','storage','attitude','antenna'}
class FailureMonitor:
    def __init__(self):self.detectors={};self.latched=set()
    def reset_node(self,node):self.detectors.pop(node,None);self.latched.discard(node)
    def evaluate(self,state,sat,sample=False):
        before=sat.health; reasons=[];full=False
        for kind,label in [('offline','node offline'),('thermal','thermal protection'),('battery','battery reserve'),('storage','storage unavailable')]:
            if kind in sat.faults:reasons.append(label);full=True
        if sat.temperature_c>=state.config.thermal_limit_c:reasons.append('temperature limit');full=True
        if sat.battery_wh<=state.config.reserve_wh:reasons.append('safe battery reserve');full=True
        if state.time_s-sat.last_telemetry_s>state.config.stale_after_s:reasons.append('sensor telemetry stale');full=True
        if sample and state.time_s==sat.last_telemetry_s:
            if self.detectors.setdefault(sat.id,CUSUM(k=.6,h=12)).update(sat.telemetry_residual_c/.15):self.latched.add(sat.id)
        if sat.id in self.latched:reasons.append('CUSUM unexpected heating');full=True
        for kind,label in [('cpu','processor unavailable; relay capable'),('radio','radio unavailable; local compute retained'),('attitude','camera not oriented'),('antenna','antenna not oriented')]:
            if kind in sat.faults:reasons.append(label)
        target='isolated' if full else 'degraded' if reasons else 'healthy'
        if target=='healthy' and before=='isolated':
            if sample and state.time_s==sat.last_telemetry_s and sat.temperature_c<state.config.thermal_limit_c-6:
                sat.recovery_samples+=1
            if sat.recovery_samples<3:target='isolated';reasons=['waiting for three fresh safe samples']
        elif target!='healthy':sat.recovery_samples=0
        sat.health=target;sat.reasons=reasons
        if target!=before:
            if target=='healthy':
                state.counters['recovered_nodes']+=1
                state.revived.append(dict(node_id=sat.id,time_s=state.time_s))
                state.log('revival',f'{sat.id} revived and rejoined the mesh',sat.id)
            else:
                state.counters['detected_faults']+=1;state.log('detection','; '.join(reasons),sat.id)
        return before!=target

def inject_fault(state,node,kind,duration_s=None):
    if node not in state.satellites or kind not in FAULT_KINDS:raise ValueError('Unknown satellite or failure')
    sat=state.satellites[node];sat.faults[kind]=state.time_s+duration_s if duration_s else None
    if kind=='thermal':sat.temperature_c=state.config.thermal_limit_c+5
    if kind=='battery':sat.battery_wh=state.config.reserve_wh-1
    if kind=='attitude':sat.attitude_error_deg=35.
    if kind=='antenna':sat.antenna_error_deg=100.
    if state.config.random_revival:sat.revival_at_s=state.time_s+state.rng.uniform(35,105)
    state.log('injection',f'Injected {kind} fault',node)

def clear_faults(state,monitor,node,restore_resources=True):
    sat=state.satellites[node];sat.faults.clear();sat.revival_at_s=None
    sat.attitude_error_deg=sat.antenna_error_deg=0.
    sat.stress_cpu=sat.extra_heat_w=sat.extra_drain_w=0.;sat.cooling_scale=1.
    if restore_resources:sat.battery_wh=max(65,sat.battery_wh);sat.temperature_c=min(34,sat.temperature_c)
    sat.last_telemetry_s=state.time_s;monitor.reset_node(node)
    state.log('recovery',f'{node}: faults cleared; verifying fresh telemetry',node)

def expire_faults(state,monitor):
    for sat in state.satellites.values():
        expired=[k for k,v in sat.faults.items() if v is not None and state.time_s>=v]
        if state.config.random_revival and sat.revival_at_s is not None and state.time_s>=sat.revival_at_s:
            clear_faults(state,monitor,sat.id);continue
        for kind in expired:
            sat.faults.pop(kind);monitor.reset_node(sat.id)
            if kind=='attitude':sat.attitude_error_deg=0.
            if kind=='antenna':sat.antenna_error_deg=0.
            state.log('recovery',f'Transient {kind} fault ended',sat.id)
    for key,end in list(state.blocked_links.items()):
        if end is not None and state.time_s>=end:state.blocked_links.pop(key);state.log('recovery',f'Link restored: {key}')
    for key,effect in list(state.effects.items()):
        if state.time_s>=effect['until_s']:state.effects.pop(key);state.log('space',f"{effect['kind']} effect ended on {key}")
