"""Symmetric weighted logical mesh, timed ground contacts and earliest-arrival routes.

Every pair is drawn. The complete graph is an abstract communication service;
physical Earth LOS is reported separately, never confused with observation access.
"""
import hashlib, heapq, math
from dataclasses import asdict
from .models import Link
from .orbits import earth_point,GROUND_LAT,GROUND_LON
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
    cache=getattr(state,'_link_cache',None)
    signature=(state.time_s,state.version,state.config.space_effects)
    if cache and cache[0]==signature:return cache[1]
    sats=list(state.satellites.values()); result=[]
    now=state.time_s; ground=earth_point(GROUND_LAT,GROUND_LON,now).tolist()
    for i,a in enumerate(sats):
        p=a.position
        for b in sats[i+1:]+[None]:
            target=b.id if b else GROUND; key=pair_key(a.id,target)
            q=b.position if b else ground
            dx,dy,dz=q[0]-p[0],q[1]-p[1],q[2]-p[2]
            d2=dx*dx+dy*dy+dz*dz;distance=math.sqrt(d2)
            v=b.velocity if b else (0.,0.,0.)
            radial=((v[0]-a.velocity[0])*dx+(v[1]-a.velocity[1])*dy+(v[2]-a.velocity[2])*dz)/max(distance,1e-9)
            doppler=-radial/C_KM_S*2.2e9
            cachekey=(key,int(now//30))
            if cachekey not in state.base_weights:state.base_weights[cachekey]=_unit(state.config.seed,key+':'+str(int(now//30)))
            if key not in state.base_weights:state.base_weights[key]=18.+10*_unit(state.config.seed,key)
            noise=state.base_weights[cachekey]
            weight=.6+3.4*noise+.2*(1-a.battery_wh/100)+(.2*(1-b.battery_wh/100) if b else 0)
            rate=state.base_weights[key];latency=distance/C_KM_S+.003
            loss=.008 if state.config.space_effects else 0.
            available=a.can_relay and (b.can_relay if b else True)
            reason='' if available else 'endpoint isolated / antenna or radio unavailable'
            until=state.blocked_links.get(key)
            if key in state.blocked_links and (until is None or now<until):available=False;reason='link outage / partition'
            if b is None:
                start,end=ground_window(a,now)
                if start>now:available=False;reason='outside simulated ground pass'
            effect=state.effects.get(key)
            if state.config.space_effects:
                rate*=max(.4,1-min(abs(doppler)/200_000,.6))
                if effect and effect['until_s']>now:
                    mode=effect['kind'];loss+=.08
                    if mode=='latency':latency+=2. if state.config.exaggerated_effects else .08
                    elif mode=='doppler':rate*=.3;loss+=.12
                    elif mode=='link_dropout':available=False;reason='random contact interruption'
            k=max(0.,min(1.,-(p[0]*dx+p[1]*dy+p[2]*dz)/max(d2,1e-12)))
            los=(p[0]+k*dx)**2+(p[1]+k*dy)**2+(p[2]+k*dz)**2>=(6371.-1)**2
            result.append(Link(a.id,target,round(weight,5),rate,latency,distance,doppler,bool(available),los,reason,loss))
    # Keep only the current/previous deterministic weight epochs in long runs.
    if len(state.base_weights)>3*(len(result)+1):
        state.base_weights={k:v for k,v in state.base_weights.items() if isinstance(k,str) or k[1]>=int(now//30)-1}
    state._link_cache=(signature,result)
    return result

def contacts(state,ready_s,deadline_s):
    graph={}; now=state.time_s
    for link in build_links(state):
        # An unavailable current ground pass may open later; hard faults do not.
        if not link.available and link.reason!='outside simulated ground pass':continue
        if link.target==GROUND:
            sat=state.satellites[link.source]; cursor=ready_s
            for _ in range(23):
                start,end=ground_window(sat,cursor)
                if start>deadline_s:break
                graph.setdefault(link.source,[]).append((GROUND,link,max(ready_s,start),end))
                cursor=end+1e-5
        else:
            graph.setdefault(link.source,[]).append((link.target,link,ready_s,deadline_s))
            graph.setdefault(link.target,[]).append((link.source,link,ready_s,deadline_s))
    return graph

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
