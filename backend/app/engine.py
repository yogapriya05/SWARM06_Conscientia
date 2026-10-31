"""Observe -> process on observer -> reliable store-and-forward -> ground delivery."""
from dataclasses import asdict
import hashlib, math, zlib
from .models import Config,Task,TERMINAL
from .state import SimulationState
from .resources import can_host,capture_start,processing_duration,ledgers,update_physics
from .allocator import allocate
from .pso import repair_placements,choose_route
from .failures import FailureMonitor,inject_fault,clear_faults,expire_faults
from .network import GROUND,PACKET_MB,pair_key,build_links,earliest_route,route_candidates,live_graph
from .orbits import update_positions,visibility_windows,earth_point,GROUND_LAT,GROUND_LON,SUN
from .metrics import summarize

REGIONS=[('FIRE_WEST',18.52,73.86),('FLOOD_DELTA',22.5,88.3),('FIRE_FOREST',11.5,76.5),('STORM_COAST',15.3,80.1)]

class Engine:
    def __init__(self,config=None,seed_tasks=True):
        self.state=SimulationState(config);self.monitor=FailureMonitor()
        if seed_tasks:
            self.add_task(event_id='FIRE_WEST',target={'lat':18.52,'lon':73.86},priority=5,name='Urgent · Western fire front')
            self.add_task(event_id='FLOOD_DELTA',target={'lat':22.5,'lon':88.3},priority=3,name='Flood extent mapping')
    def transition(self,t,status,note):
        if t.status!=status:t.transitions.append(dict(status=status,time_s=self.state.time_s));t.status=status
        t.note=note
    def add_task(self,**data):
        s=self.state
        if len(s.active_tasks())>=s.config.max_active_tasks:raise ValueError('Active task queue is full')
        tid=data.pop('task_id',None) or data.pop('id',None) or f'OBS_{s.next_task:05d}'
        if tid in s.tasks:raise ValueError('Task ID already exists')
        s.next_task+=1
        now=s.time_s;event=data.pop('event_id',f'EVENT_{s.next_event:03d}');s.next_event+=1
        target=data.pop('target',{'lat':18.52,'lon':73.86})
        window=data.pop('observation_window',[now+1,now+62]);deadline=data.pop('delivery_deadline',now+90)
        if window[1]<=window[0] or deadline<=now:raise ValueError('Invalid time window or deadline')
        if data.get('allowed_satellites') and not set(data['allowed_satellites'])<=set(s.satellites):raise ValueError('Unknown allowed satellite')
        t=Task(task_id=tid,event_id=event,target=target,created_at=now,observation_window=window,delivery_deadline=deadline,**data)
        t.visibility_windows=visibility_windows(s,window[0],window[1]);t.transitions=[dict(status='pending',time_s=now)]
        s.tasks[tid]=t
        s.regions.setdefault(event,dict(target=target,name=t.name,next_monitor_s=now+125,interval_s=125))
        s.log('task',f'{tid} · {event} · priority {t.priority} · deadline T+{deadline:.0f}s',task=tid)
        self._plan();return t
    def add_campaign(self):
        s=self.state;event=f'CAMPAIGN_{s.next_event:03d}';tasks=[]
        if len(s.active_tasks())+2>s.config.max_active_tasks:raise ValueError('Campaign requires two queue slots')
        for kind in ['gnss','remote_sensing']:
            tasks.append(self.add_task(event_id=event,kind=kind,name=f'{kind} paired disaster product',output_data_mb=4 if kind=='gnss' else 10,raw_data_mb=12 if kind=='gnss' else 40))
        return tasks
    def update_priority(self,event_id,priority):
        changed=[]
        for t in self.state.active_tasks():
            if t.event_id==event_id:t.priority=priority;changed.append(t.task_id)
        self.state.log('priority',f'{event_id} severity changed; preserved IDs: {", ".join(changed)}')
        self._plan();return changed
    def _plan(self):
        s=self.state;ledgers(s)
        queued=sorted([t for t in s.active_tasks() if t.status in {'pending','deferred'}],key=lambda t:(not t.needs_repair,-t.priority,t.delivery_deadline,t.task_id))[:16]
        if not queued:return
        ranks,result=allocate(s,queued)
        repaired,stats=repair_placements(s,[t for t in queued if t.needs_repair],ranks)
        if stats:s.repair=stats
        for t in queued:
            ranked=list(ranks[t.task_id])
            if t.task_id in repaired:ranked.sort(key=lambda sat:sat.id!=repaired[t.task_id])
            reason='No eligible complete task chain'
            for sat in ranked:
                ok,reason,plan=can_host(s,sat,t)
                if not ok:continue
                old_attempts=t.attempts;t.attempts+=1;t.owner=sat.id;t.assigned_at=s.time_s
                t.lease_version+=1;t.lease_until_s=t.delivery_deadline
                t.route=plan['route']['nodes'];t.route_hops=plan['route']['hops']
                self.transition(t,'assigned',f'Capture at T+{plan["capture_start_s"]:.1f}s; process locally; predicted ground arrival {plan["route"]["arrival_s"]:.1f}s')
                if old_attempts:
                    t.reassignments+=1;s.counters['reassignments']+=1
                    s.log('reallocation',f'{t.task_id} immediately reassigned to {sat.id}',sat.id,t.task_id)
                else:s.log('allocation',f'{t.task_id} assigned to {sat.id}',sat.id,t.task_id)
                t.needs_repair=False;ledgers(s);break
            else:self.transition(t,'deferred',reason)
        s.next_plan_s=s.time_s+5
    def _release_transfer(self,t):
        t.receiver=None;t.acked_packets.clear();t.pending_packets.clear();t.packet_attempts.clear();t.transfer_progress_mb=0.;t.hop_index=0
    def _reconcile(self):
        s=self.state
        for t in s.active_tasks():
            if t.status=='assigned' and t.owner:
                sat=s.satellites[t.owner]
                if not sat.can_observe or sat.attitude_error_deg>5:
                    old=t.owner;t.owner=None;t.progress_capture_s=0;t.route=[];t.route_hops=[];t.failure_at=s.time_s;t.needs_repair=True
                    self.transition(t,'pending',f'Unfinished acquisition released from {old}; no valid image exists')
                    s.log('repair',f'{t.task_id}: release unstarted/partial capture from {old}',old,t.task_id)
            elif t.status=='captured' and t.holder:
                sat=s.satellites[t.holder]
                if 'storage' in sat.faults:
                    self.transition(t,'failed','Captured data inaccessible after storage fault');s.log('failure',t.note,sat.id,t.task_id)
                elif not sat.can_compute:
                    t.note=f'Raw image retained on {t.holder}; processing checkpoint {t.progress_cycles:.0f} cycles; waiting for local recovery'
                else:t.note=f'Processing retained image on {t.holder}'
            elif t.status=='processed' and t.holder:
                if 'storage' in s.satellites[t.holder].faults:
                    self._release_transfer(t);self.transition(t,'failed','Only product copy inaccessible after storage fault');continue
                if t.route_hops:
                    hop=t.route_hops[0];key=pair_key(hop['source'],hop['target'])
                    link=next((l for l in build_links(s) if l.key==key),None)
                    if link is None or (not link.available and link.reason!='outside simulated ground pass'):
                        self._release_transfer(t);t.route=[];t.route_hops=[];t.needs_repair=True
                        s.log('repair',f'{t.task_id}: sender copy retained on {t.holder}; rebuilding contact path',t.holder,t.task_id)
        ledgers(s)
        for sat in s.satellites.values():
            if sat.control_cpu+sat.stress_cpu+sat.allocated_cpu<=100+1e-8:continue
            adjustable=sorted([t for t in s.active_tasks() if t.status=='assigned' and t.owner==sat.id],key=lambda t:(t.priority,-t.delivery_deadline))
            for t in adjustable:
                t.owner=None;t.progress_capture_s=0.;t.route=[];t.route_hops=[];t.needs_repair=True
                self.transition(t,'pending',f'CPU stress on {sat.id}; uncaptured work released')
                s.log('repair',t.note,sat.id,t.task_id);ledgers(s)
                if sat.control_cpu+sat.stress_cpu+sat.allocated_cpu<=100+1e-8:break
        ledgers(s)
    def _repair_routes(self):
        s=self.state
        for t in sorted(s.active_tasks(),key=lambda x:(-x.priority,x.delivery_deadline)):
            if t.status!='processed' or t.route_hops:continue
            if not s.satellites[t.holder].can_relay:
                t.note=f'Valid product retained on {t.holder}; waiting for radio/node recovery';continue
            candidates=route_candidates(s,t.holder,t.output_data_mb,s.time_s,t.delivery_deadline)
            route=choose_route(s,candidates) if t.needs_repair else (candidates[0] if candidates else None)
            if route:
                self._release_transfer(t);t.route=route['nodes'];t.route_hops=route['hops'];t.packet_count=math.ceil(t.output_data_mb/PACKET_MB)
                if t.needs_repair:s.counters['reroutes']+=1;s.log('reroute',f'{t.task_id}: '+ ' → '.join(t.route),t.holder,t.task_id)
                t.needs_repair=False;t.note='Reliable transfer: '+ ' → '.join(t.route)
            else:t.note='Valid product buffered; no feasible ground contact yet'
        ledgers(s)
    def reconstruct(self,description='reconstruction'):
        s=self.state;start=s.time_s
        record=dict(time_s=start,description=description,stages=[])
        for stage in ['Fault detected','Capabilities isolated','Mesh reconstructed']:
            record['stages'].append(dict(name=stage,time_s=s.time_s))
        self._reconcile();self._plan();self._repair_routes()
        self.validate()
        record['stages'] += [dict(name='Task ownership repaired',time_s=s.time_s),dict(name='Resource ledgers validated',time_s=s.time_s)]
        record['available_nodes']=sum(x.health!='isolated' for x in s.satellites.values());s.recovery.append(record)
        s.log('mesh',f'{description}: mesh and task repair committed in the same simulator update')
        s.version+=1
    def inject(self,node,kind,duration_s=None):
        inject_fault(self.state,node,kind,duration_s);self.monitor.evaluate(self.state,self.state.satellites[node]);self.reconstruct(f'{node} · {kind}')
    def recover(self,node,restore_resources=True):
        clear_faults(self.state,self.monitor,node,restore_resources)
        self.monitor.evaluate(self.state,self.state.satellites[node]);self.reconstruct(f'{node} recovery requested')
    def set_battery(self,node,percent):
        sat=self.state.satellites[node];sat.battery_wh=percent
        if percent>self.state.config.reserve_wh:sat.faults.pop('battery',None)
        self.monitor.evaluate(self.state,sat);self.reconstruct(f'{node} battery set to {percent:.0f}%')
    def set_stress(self,node,cpu_pct=0,heat_w=0,drain_w=0,cooling_scale=1):
        sat=self.state.satellites[node];sat.stress_cpu=cpu_pct;sat.extra_heat_w=heat_w;sat.extra_drain_w=drain_w;sat.cooling_scale=cooling_scale
        self.state.log('stress',f'{node}: CPU {cpu_pct}%, heat {heat_w} W, drain {drain_w} W');self.reconstruct('Resource stress changed')
    def block_link(self,source,target,blocked=True,duration_s=None):
        key=pair_key(source,target)
        if blocked:self.state.blocked_links[key]=self.state.time_s+duration_s if duration_s else None
        else:self.state.blocked_links.pop(key,None)
        self.state.log('link',f'{key} '+('blocked' if blocked else 'restored'));self.reconstruct('Link topology changed')
    def _work(self,dt):
        s=self.state
        for t in sorted(s.active_tasks(),key=lambda t:(-t.priority,t.delivery_deadline)):
            if t.status=='assigned' and t.owner:
                sat=s.satellites[t.owner]
                if not sat.can_observe:continue
                # Only integrate the portion of this tick inside the explicit access window.
                duration=t.capture_duration_s*t.required_captures
                active=sum(max(0,min(s.time_s,b,t.observation_window[1])-max(s.time_s-dt,a,t.observation_window[0])) for a,b in t.visibility_windows.get(sat.id,[]))
                if active<=0:continue
                t.progress_capture_s=min(duration,t.progress_capture_s+active)
                sat.battery_wh=max(0,sat.battery_wh-12*active/3600);s.counters['energy_used_wh']+=12*active/3600
                if t.progress_capture_s>=duration-1e-8:
                    t.holder=sat.id;t.captured_at=s.time_s;t.captures=t.required_captures;t.quality=.96
                    self.transition(t,'captured','Valid raw image retained; processing on observer');s.log('capture',f'{t.task_id}: captured on {sat.id}',sat.id,t.task_id)
            elif t.status=='captured' and t.holder:
                sat=s.satellites[t.holder]
                if not sat.can_compute:continue
                t.progress_cycles=min(t.processing_cycles,t.progress_cycles+sat.cycles_per_s*t.cpu_demand/100*dt*min(1.,max(0.,100-sat.control_cpu-sat.stress_cpu)/max(1.,sat.allocated_cpu)))
                if t.progress_cycles>=t.processing_cycles-1e-8:
                    t.processed_at=s.time_s;t.valid_product=t.quality>=t.minimum_quality;t.product_hash=hashlib.sha256(f'{t.task_id}:{t.captured_at}:{t.quality}'.encode()).hexdigest()
                    t.route=[];t.route_hops=[]
                    self.transition(t,'processed','Output checksum created; raw buffer released');s.log('process',f'{t.task_id}: processed; {t.output_data_mb} MB product',sat.id,t.task_id)
        ledgers(s)
    @staticmethod
    def packet_payload(t,seq):
        # Compact surrogate bytes represent each logical .5 MB packet; byte-level CRC is real.
        return hashlib.sha256(f'{t.product_hash}:{seq}'.encode()).digest()*4
    def _transfer(self,dt):
        s=self.state;links={l.key:l for l in build_links(s) if l.available}
        edge_budget={key:l.rate_mbps*dt/8 for key,l in links.items()}
        radios={node:24*dt/8 for node in s.satellites};radios[GROUND]=48*dt/8
        for t in sorted(s.active_tasks(),key=lambda t:(-t.priority,t.delivery_deadline,t.task_id)):
            if t.status!='processed' or not t.route_hops:continue
            hop=t.route_hops[0];a,b=hop['source'],hop['target'];key=pair_key(a,b);link=links.get(key)
            # Acks mature independently; invalid/partial/lost packets remain unacknowledged.
            waiting=[]
            for packet in t.pending_packets:
                if packet['ack_s']>s.time_s:waiting.append(packet);continue
                if packet['valid'] and link and s.time_s<=t.delivery_deadline:
                    if packet['seq'] not in t.acked_packets:s.counters['packets_acked']+=1
                    t.acked_packets.add(packet['seq'])
            t.pending_packets=waiting
            t.transfer_progress_mb=min(t.output_data_mb,len(t.acked_packets)*PACKET_MB)
            if len(t.acked_packets)>=t.packet_count:
                # Atomic hop commit: reconstruct ordered manifest and independently verify checksum.
                received=b''.join(hashlib.sha256(self.packet_payload(t,k)).digest() for k in sorted(t.acked_packets))
                expected=b''.join(hashlib.sha256(self.packet_payload(t,k)).digest() for k in range(t.packet_count))
                if hashlib.sha256(received).digest()!=hashlib.sha256(expected).digest():raise AssertionError('Product manifest corruption')
                if b==GROUND:
                    if not t.valid_product:raise AssertionError('Invalid quality delivered')
                    t.delivered_at=s.time_s;t.holder=None;self._release_transfer(t);t.route_hops=[]
                    self.transition(t,'delivered','Ground acknowledged complete valid result by deadline');s.counters['delivered_mb']+=t.output_data_mb
                    s.log('delivery',f'{t.task_id}: ground delivery confirmed at T+{s.time_s:.0f}s',task=t.task_id)
                else:
                    t.holder=b;remaining=t.route_hops[1:];self._release_transfer(t);t.route_hops=remaining;t.route=[b]+[h['target'] for h in remaining]
                    s.log('relay',f'{t.task_id}: complete product acknowledged by {b}; sender buffer released',b,t.task_id)
                ledgers(s);continue
            if not link or s.time_s<hop['start_s']:continue
            if b!=GROUND and t.receiver!=b:
                if s.satellites[b].free_storage_mb+1e-8<t.output_data_mb:
                    t.route=[];t.route_hops=[];t.needs_repair=True;continue
            t.receiver=b;ledgers(s)
            pending={p['seq'] for p in t.pending_packets}
            budget=min(edge_budget[key],radios[a],radios[b]);sent=0.
            for seq in range(t.packet_count):
                if seq in pending or seq in t.acked_packets:continue
                size=min(PACKET_MB,t.output_data_mb-seq*PACKET_MB)
                if size>budget-sent+1e-8:break
                payload=self.packet_payload(t,seq);crc=zlib.crc32(payload);mode=None
                effect=s.effects.get(key) if s.config.space_effects else None
                if effect and effect['until_s']>s.time_s and effect['kind'] in {'bit_flip','partial_packet'}:mode=effect['kind']
                elif s.config.space_effects:
                    roll=s.rng.random();scale=3 if s.config.exaggerated_effects else 1
                    if roll<.015*scale:mode='bit_flip'
                    elif roll<.03*scale:mode='partial_packet'
                    elif roll<.03*scale+link.loss:mode='lost'
                rx=payload
                if mode=='bit_flip':rx=bytes([payload[0]^1])+payload[1:];s.counters['bit_flips']+=1
                elif mode=='partial_packet':rx=payload[:len(payload)//2];s.counters['partial_packets']+=1
                elif mode=='lost':rx=b'';s.counters['packets_lost']+=1
                valid=len(rx)==len(payload) and zlib.crc32(rx)==crc
                attempts=t.packet_attempts.get(seq,0)
                if attempts:s.counters['retries']+=1
                t.packet_attempts[seq]=attempts+1
                t.pending_packets.append(dict(seq=seq,ack_s=s.time_s+max(.2,2*link.latency_s),valid=bool(valid)))
                s.counters['packets_sent']+=1;sent+=size
                energy=size*.002
                s.satellites[a].battery_wh=max(0,s.satellites[a].battery_wh-energy);s.counters['energy_used_wh']+=energy
            edge_budget[key]-=sent;radios[a]-=sent;radios[b]-=sent
            if sent:s.transfers.append(dict(time_s=s.time_s,key=key,sent_mb=sent,capacity_mb=budget))
    def _space_effects(self):
        s=self.state
        if not s.config.space_effects or s.time_s<s.next_effect_s:return
        s.next_effect_s=s.time_s+s.rng.uniform(8,18)
        links=[l for l in build_links(s) if l.available]
        if not links:return
        # Favor a busy contact so the demo actually exhibits packet-level effects.
        busy={pair_key(t.route_hops[0]['source'],t.route_hops[0]['target']) for t in s.active_tasks() if t.status=='processed' and t.route_hops}
        link=s.rng.choice([l for l in links if l.key in busy] or links)
        kind=s.rng.choice(['latency','doppler','partial_packet','bit_flip','link_dropout','attitude','antenna','stale'])
        if kind in {'attitude','antenna','stale'}:
            sat=s.rng.choice(list(s.satellites.values()))
            if not sat.faults:self.inject(sat.id,kind,duration_s=s.rng.uniform(10,18))
        else:
            s.effects[link.key]=dict(kind=kind,until_s=s.time_s+s.rng.uniform(4,9),source=link.source,target=link.target)
            if kind=='latency':s.counters['latency_events']+=1
            if kind=='doppler':s.counters['doppler_events']+=1
            s.log('space',f'{kind.replace("_"," ")} on {link.key}; reliable transport / repair active')
            s.version+=1
            if kind=='link_dropout':self.reconstruct('Random contact dropout')
    def _workload(self):
        s=self.state
        if not s.config.auto_tasks:return
        def spawn(urgent=False):
            if len(s.active_tasks())>=s.config.max_active_tasks:return
            event,lat,lon=s.rng.choice(REGIONS)
            self.add_task(event_id=event,target={'lat':lat,'lon':lon},priority=5 if urgent else s.rng.randint(1,4),name=('URGENT · ' if urgent else '')+event.replace('_',' ').title())
        if s.time_s>=s.next_arrival_s:spawn();s.next_arrival_s=s.time_s+s.rng.uniform(15,30)
        if s.time_s>=s.next_burst_s:
            for _ in range(3):spawn(True)
            s.log('burst','Three urgent disaster requests appeared');s.next_burst_s=s.time_s+s.rng.uniform(100,160)
        if s.time_s>=s.next_severity_s:
            active=s.active_tasks()
            if active:self.update_priority(s.rng.choice(active).event_id,5)
            s.next_severity_s=s.time_s+s.rng.uniform(40,75)
        for event,region in list(s.regions.items()):
            if s.time_s>=region['next_monitor_s'] and len(s.active_tasks())<s.config.max_active_tasks:
                self.add_task(event_id=event,target=region['target'],name='Repeat · '+region['name'],priority=3)
                region['next_monitor_s']=s.time_s+region['interval_s']
    def _expire(self):
        s=self.state
        for t in s.active_tasks():
            if s.time_s>t.delivery_deadline:
                self._release_transfer(t);self.transition(t,'expired','No valid ground acknowledgement by delivery deadline');s.log('deadline',f'{t.task_id} expired',task=t.task_id)
            elif t.status in {'pending','deferred','assigned'} and s.time_s>t.observation_window[1]:
                self._release_transfer(t);self.transition(t,'expired','Observation window ended before complete acquisition');s.log('deadline',f'{t.task_id}: observation window expired',task=t.task_id)
        ledgers(s)
    def step(self,seconds=1,emit_snapshot=True):
        # Fixed <=1-second integration retains all events at 100x. No giant dt shortcuts.
        remaining=float(seconds)
        while remaining>1e-9:
            dt=min(1.,remaining);remaining-=dt;s=self.state;s.time_s=round(s.time_s+dt,9);s.tick+=1
            expire_faults(s,self.monitor);update_positions(s);ledgers(s);update_physics(s,dt)
            changed=False
            for sat in s.satellites.values():changed=self.monitor.evaluate(s,sat,sample=True) or changed
            self._expire()
            if changed:self.reconstruct('Detected health / revival transition')
            self._space_effects();self._reconcile();self._workload()
            if s.time_s>=s.next_plan_s:self._plan()
            self._work(dt);self._repair_routes();self._transfer(dt);ledgers(s)
            if s.tick%5==0:s.history.append(dict(time_s=s.time_s,delivered=summarize(s)['delivered'],battery_pct=sum(x.battery_wh for x in s.satellites.values())/len(s.satellites)))
            if s.tick%120==0:self._trim()
        return self.snapshot() if emit_snapshot else None
    def _trim(self):
        s=self.state;terminal=[t for t in s.tasks.values() if t.status in TERMINAL]
        for t in terminal[:-300]:s.counters['archived_'+t.status]+=1;s.counters['archived_tasks']+=1;s.tasks.pop(t.task_id)
    def snapshot(self):
        s=self.state; sats=[]
        for sat in s.satellites.values():
            row=asdict(sat);row.update(battery=sat.battery_wh,status='isolated' if sat.health=='isolated' else 'online' if sat.health=='healthy' else 'degraded',
                free_cpu=sat.free_cpu,free_storage_mb=sat.free_storage_mb,can_compute=sat.can_compute,can_relay=sat.can_relay,
                telemetry_age_s=s.time_s-sat.last_telemetry_s,owner_task_ids=[t.task_id for t in s.active_tasks() if t.owner==sat.id])
            sats.append(row)
        tasks=[]
        for t in s.tasks.values():
            row=asdict(t);row['acked_packets']=sorted(t.acked_packets)
            row.pop('packet_attempts',None);row.pop('pending_packets',None)
            row.update(id=t.task_id,owner_id=t.owner,progress_pct=100 if t.status=='delivered' else 75+20*len(t.acked_packets)/max(1,t.packet_count) if t.status=='processed' else 25+45*t.progress_cycles/max(1,t.processing_cycles) if t.status=='captured' else 20*t.progress_capture_s/max(1,t.capture_duration_s*t.required_captures) if t.status=='assigned' else 0)
            tasks.append(row)
        return dict(version=s.version,time_s=s.time_s,tick=s.tick,paused=s.paused,config=asdict(s.config),satellites=sats,tasks=tasks,
            links=live_graph(s),events=list(s.events)[-120:],metrics=summarize(s),allocator=s.allocator,repair=s.repair,
            recovery=list(s.recovery),revived=list(s.revived),effects=list(s.effects.values()),history=list(s.history),
            ground=dict(id=GROUND,lat=GROUND_LAT,lon=GROUND_LON,position=earth_point(GROUND_LAT,GROUND_LON,s.time_s).tolist()),sun=SUN.tolist(),
            model=dict(orbits='circular two-body',mesh='complete logical bidirectional mesh; Earth LOS reported separately',visibility='explicit simulated windows',transport='CRC32 + sequenced packets + retries + atomic per-hop product commit'))
    def validate(self):
        s=self.state
        for sat in s.satellites.values():
            assert sat.allocated_cpu+sat.control_cpu+sat.stress_cpu<=100+1e-6 or sat.stress_cpu>0
            assert sat.storage_used_mb+sat.storage_reserved_mb<=sat.storage_capacity_mb+1e-6,(sat.id,'storage overflow')
            assert 0<=sat.battery_wh<=100 and math.isfinite(sat.temperature_c)
        for t in s.tasks.values():
            assert t.progress_cycles<=t.processing_cycles+1e-6
            if t.status=='delivered':assert t.valid_product and t.delivered_at<=t.delivery_deadline and t.holder is None
            if t.status=='assigned':assert t.owner and s.satellites[t.owner].can_observe
            if t.status in {'captured','processed'}:assert t.holder in s.satellites
        for row in s.transfers:assert row['sent_mb']<=row['capacity_mb']+1e-8
        return True
SimulationEngine=Engine
