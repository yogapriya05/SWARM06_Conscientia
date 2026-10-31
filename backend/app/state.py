from collections import deque
import random
from .models import Config, Satellite, TERMINAL
from .orbits import update_positions
class SimulationState:
    def __init__(self,config=None):
        self.config=config or Config(); self.rng=random.Random(self.config.seed)
        self.time_s=0.; self.tick=0; self.paused=True; self.version=0
        self.satellites={}; self.tasks={}; self.next_task=1; self.next_event=1
        for group in range(self.config.swarm_count):
            for slot in range(self.config.satellites_per_swarm):
                i=group*self.config.satellites_per_swarm+slot
                sat=Satellite(f'SAT-{i+1:02d}',i,f'SWARM-{group+1:02d}',slot,
                    battery_wh=self.rng.uniform(72,90),cycles_per_s=self.rng.uniform(1.6e6,2.4e6))
                sat.body_yaw_deg=self.rng.uniform(-6,6);sat.antenna_mount_deg=self.rng.uniform(-4,4)
                self.satellites[sat.id]=sat
        self.events=deque(maxlen=300); self.revived=deque(maxlen=30); self.history=deque(maxlen=240)
        self.recovery=deque(maxlen=60); self.transfers=deque(maxlen=500)
        self.blocked_links={}; self.effects={}; self.base_weights={}; self.regions={}
        self.next_arrival_s=self.rng.uniform(12,25); self.next_burst_s=70.; self.next_effect_s=15.
        self.coordinator=None;self.coordinator_epoch=0;self.control_messages=[];self.next_control=1
        self.graph_history=deque(maxlen=16);self.graph_epoch=0;self.graph_signature=None
        self.commit_audit=deque(maxlen=120);self.message_audit=deque(maxlen=120)
        self.next_random_failure_s=self.rng.expovariate(max(1e-12,self.config.random_failure_rate_per_sat_s*len(self.satellites)))
        self.next_severity_s=38.; self.next_plan_s=0.; self.allocator={}; self.repair={}
        self.counters=dict(reassignments=0,reroutes=0,detected_faults=0,recovered_nodes=0,
            packets_sent=0,packets_acked=0,retries=0,bit_flips=0,partial_packets=0,
            packets_lost=0,doppler_events=0,latency_events=0,delivered_mb=0.,energy_used_wh=0.,
            random_failures=0,conflicts_prevented=0,ownership_commits=0,control_delivered=0,control_retries=0,archived_delivered=0,archived_expired=0,archived_failed=0,archived_tasks=0)
        update_positions(self)
        self.log('system',f'{self.config.swarm_count} swarms · {len(self.satellites)} satellites · seed {self.config.seed}')
    def log(self,kind,message,node=None,task=None):
        self.events.append(dict(id=f'E{self.version}-{len(self.events)}-{self.tick}',time_s=self.time_s,
            category=kind,message=message,node_id=node,task_id=task)); self.version+=1
    def active_tasks(self):return [t for t in self.tasks.values() if t.status not in TERMINAL]
