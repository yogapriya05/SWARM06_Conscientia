"""Symmetric weighted logical mesh, timed ground contacts and earliest-arrival routes.

Every pair is drawn. The complete graph is an abstract communication service;
physical Earth LOS is reported separately, never confused with observation access.
"""
import hashlib, heapq, math
import numpy as np
from dataclasses import asdict
from .models import Link
from .orbits import earth_point,GROUND_LAT,GROUND_LON,line_of_sight,predicted_position,OMEGA_EARTH
from .antennas import evaluate as antenna_evaluate
GROUND='GND'
C_KM_S=299792.458
PACKET_MB=.5

def pair_key(a,b):return '|'.join(sorted((a,b)))
def _unit(seed,key):return int(hashlib.sha256(f'{seed}:{key}'.encode()).hexdigest()[:12],16)/float(16**12)
def ground_window(sat,t):
    # Explicit synthetic pass schedule: staggered 62-second passes every 90 s.
    phase=(sat.slot*19+(21 if sat.swarm=='SWARM-02' else 0))%90
    start=math.floor((t-phase)/90)*90+phase
    return (t,start+62) if t<start+62 else (start+90,start+152)

def build_links(state):
    signature=(state.time_s,state.version,state.config.space_effects)
    cached=getattr(state,'_link_cache',None)
    if cached and cached[0]==signature:return cached[1]
    sats=list(state.satellites.values());result=[];now=state.time_s
    ground=earth_point(GROUND_LAT,GROUND_LON,now)
    for i,a in enumerate(sats):
        for b in sats[i+1:]+[None]:
            target=b.id if b else GROUND;key=pair_key(a.id,target)
            p=np.asarray(a.position);q=np.asarray(b.position) if b else ground;d=q-p
            distance=float(np.linalg.norm(d));unit=d/max(distance,1e-9)
            v=np.asarray(b.velocity) if b else np.array([-OMEGA_EARTH*q[2],0.,OMEGA_EARTH*q[0]])
            radial=float((v-np.asarray(a.velocity))@unit);doppler=-radial/C_KM_S*2.2e9
            tx=antenna_evaluate(a,q,ground=b is None)
            rx=antenna_evaluate(b,p) if b else dict(gain=1.,angle_deg=0.,body_blocked=False,clear=True)
            los=line_of_sight(p,q);clear=tx['clear'] and rx['clear'];pair_gain=max(.015,math.sqrt(tx['gain']*rx['gain']))
            if key not in state.base_weights:state.base_weights[key]=_unit(state.config.seed,key)
            calibration=.4+1.2*state.base_weights[key]
            components=dict(seeded_calibration=calibration,distance=.4*distance/1000,
                pointing=1.3*(1/pair_gain-1),energy=.3*(1-a.battery_wh/100)+(.3*(1-b.battery_wh/100) if b else 0),
                doppler=.2*abs(doppler)/100000,body_blockage=25.*(tx['body_blocked']+rx['body_blocked']))
            weight=sum(components.values());rate=(18.+10*state.base_weights[key])*max(.12,pair_gain)
            latency=distance/C_KM_S+.003;loss=.008 if state.config.space_effects else 0.
            available=a.can_relay and (b.can_relay if b else True);reason='' if available else 'endpoint isolated / radio unavailable'
            if available and not los:available=False;reason='Earth occultation'
            if available and not clear:available=False;reason='CubeSat body blockage' if tx['body_blocked'] or rx['body_blocked'] else 'outside antenna beam'
            if b is None:
                # Geometric elevation gate; future openings are predicted in contacts().
                elevation=float(np.dot(unit,-q/np.linalg.norm(q)))
                if available and elevation<math.sin(math.radians(5)):available=False;reason='outside geometric ground pass'
            if key in state.blocked_links and (state.blocked_links[key] is None or now<state.blocked_links[key]):available=False;reason='link outage / partition'
            effect=state.effects.get(key)
            if state.config.space_effects and effect and effect['until_s']>now:
                mode=effect['kind'];loss+=.08
                if mode=='latency':latency+=2. if state.config.exaggerated_effects else .08
                elif mode=='doppler':rate*=.3;loss+=.12
                elif mode=='link_dropout':available=False;reason='random contact interruption'
            result.append(Link(a.id,target,round(weight,5),rate,latency,distance,doppler,bool(available),los,reason,loss,
                tx['gain'],rx['gain'],tx['angle_deg'],rx['angle_deg'],tx['body_blocked'],rx['body_blocked'],bool(clear),components))
    state._link_cache=(signature,result);return result


def geometric_ground_windows(state,sat,ready,deadline):
    # Circular short-horizon prediction is used for admission only. Actual links use J2 states.
    cache=getattr(state,'_ground_cache',None)
    if cache is None or cache[0]!=state.time_s:state._ground_cache=(state.time_s,{})
    key=(sat.id,math.ceil(deadline/5)*5)
    stored=state._ground_cache[1]
    if key in stored:return [(max(ready,a),min(deadline,b)) for a,b in stored[key] if b>ready and a<deadline]
    intervals=[];opened=None;step=5.;t=state.time_s
    while t<=deadline+1e-8:
        p=predicted_position(sat,t-state.time_s);q=earth_point(GROUND_LAT,GROUND_LON,t)
        d=p-q;distance=float(np.linalg.norm(d));elevation=float(np.dot(d/max(distance,1e-9),q/np.linalg.norm(q)))
        visible=line_of_sight(p,q) and elevation>=math.sin(math.radians(5))
        if visible and opened is None:opened=t
        if not visible and opened is not None:intervals.append((opened,t-step));opened=None
        t+=step
    if opened is not None:intervals.append((opened,deadline))
    stored[key]=[(a,b) for a,b in intervals if b>a]
    return [(max(ready,a),min(deadline,b)) for a,b in stored[key] if b>ready and a<deadline]

def contacts(state,ready_s,deadline_s):
    graph={}
    for link in build_links(state):
        if link.target==GROUND:
            sat=state.satellites[link.source]
            if not sat.can_relay or not link.antenna_clear or link.key in state.blocked_links:continue
            for start,end in geometric_ground_windows(state,sat,ready_s,deadline_s):
                graph.setdefault(link.source,[]).append((GROUND,link,start,end))
        elif link.available:
            graph.setdefault(link.source,[]).append((link.target,link,ready_s,deadline_s))
            graph.setdefault(link.target,[]).append((link.source,link,ready_s,deadline_s))
    return graph

def control_path(state,source,target):
    if source==target:return [source],0.
    if source not in state.satellites or target not in state.satellites:return None
    signature=(state.time_s,state.version)
    cache=getattr(state,'_control_route_cache',None)
    if cache is None or cache[0]!=signature:
        graph={}
        for link in build_links(state):
            if link.available and link.target!='GND':
                graph.setdefault(link.source,[]).append((link.target,link.weight));graph.setdefault(link.target,[]).append((link.source,link.weight))
        state._control_route_cache=(signature,graph,{})
    _,graph,trees=state._control_route_cache
    if source not in trees:
        queue=[(0.,source,[source])];paths={}
        while queue:
            cost,node,path=heapq.heappop(queue)
            if node in paths:continue
            paths[node]=(path,cost)
            for dst,weight in graph.get(node,[]):
                if dst not in paths:heapq.heappush(queue,(cost+weight,dst,path+[dst]))
        trees[source]=paths
    return trees[source].get(target)

def earliest_route(state,source,size_mb,ready_s,deadline_s,banned=None):
    if source==GROUND:return dict(nodes=[GROUND],hops=[],arrival_s=ready_s,cost=0.)
    if source not in state.satellites or not state.satellites[source].can_relay:return None
    graph=contacts(state,ready_s,deadline_s); banned=banned or set()
    queue=[(ready_s,0.,source,[source],[])]; best={source:ready_s}
    while queue:
        arrival,cost,node,path,hops=heapq.heappop(queue)
        if arrival>best.get(node,math.inf)+1e-8:continue
        if node==GROUND:return dict(nodes=path,hops=hops,arrival_s=arrival,cost=cost)
        for target,link,start,end in graph.get(node,[]):
            if target in path or link.key in banned:continue
            if target!=GROUND and state.satellites[target].free_storage_mb+1e-8<size_mb:continue
            begin=max(arrival,start)
            # Conservative expected retry/radio sharing allowance; runtime enforces actual budgets.
            finish=begin+size_mb*8/(min(24,link.rate_mbps)*.48*max(.25,1-link.loss))+2*link.latency_s+1
            if finish>min(end,deadline_s) or finish>=best.get(target,math.inf):continue
            best[target]=finish
            hop=dict(source=node,target=target,start_s=begin,end_s=end,rate_mbps=link.rate_mbps,weight=link.weight)
            heapq.heappush(queue,(finish,cost+link.weight,target,path+[target],hops+[hop]))
    return None

def route_candidates(state,source,size,ready,deadline,limit=3):
    first=earliest_route(state,source,size,ready,deadline)
    if first is None:return []
    choices=[first]; seen={tuple(first['nodes'])}
    for hop in first['hops']:
        candidate=earliest_route(state,source,size,ready,deadline,{pair_key(hop['source'],hop['target'])})
        if candidate and tuple(candidate['nodes']) not in seen:choices.append(candidate);seen.add(tuple(candidate['nodes']))
        if len(choices)>=limit:break
    return sorted(choices,key=lambda x:x['arrival_s'])

def live_graph(state):return [asdict(x)|{'key':x.key,'capacity_mbps':x.rate_mbps,'two_way':True} for x in build_links(state)]
