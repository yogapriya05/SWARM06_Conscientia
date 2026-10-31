"""Routed request/manifest buffers, lowest weighted-degree coordinator and CAS leases.

All agents are emulated by one process. Buffers are on named satellites; no claim
of true distributed consensus or replicated durable storage is made.
"""
from .network import build_links,control_path,pair_key
from .models import TERMINAL


def elect(state,force=False):
    candidates=[s for s in state.satellites.values() if s.can_compute and s.can_relay]
    edges=build_links(state);n=max(1,len(state.satellites)-1)
    for sat in state.satellites.values():
        incident=[l for l in edges if l.target!='GND' and sat.id in (l.source,l.target) and l.available]
        sat.node_weight=(sum(l.weight for l in incident)+30*(n-len(incident)))/n
    winner=min(candidates,key=lambda s:(s.node_weight,s.id)) if candidates else None
    old=state.coordinator['node_id'] if state.coordinator else None
    # Stable epoch during an intact planning period; re-elect on reconstruction or a lost leader.
    if not force and old and any(s.id==old for s in candidates):return
    if winner and (old!=winner.id or force):
        state.coordinator_epoch+=1
        state.coordinator=dict(node_id=winner.id,epoch=state.coordinator_epoch,weight=winner.node_weight,elected_at_s=state.time_s)
        state.log('coordinator',f'Coordinator {winner.id}: lowest mean link cost {winner.node_weight:.3f}, epoch {state.coordinator_epoch}',winner.id)
        for t in state.active_tasks():
            t.coordinator_id=winner.id;t.coordinator_epoch=state.coordinator_epoch
            if t.coordination_status in {'received','sharing','ready'}:
                # Previously shared manifests remain on their holders; reshare to reachable members.
                share(state,t)
    elif winner is None:state.coordinator=None


def enqueue(state,task,kind,source,target):
    if any(m['task_id']==task.task_id and m['kind']==kind and m['target']==target and m['status'] not in {'delivered','expired','superseded'} for m in state.control_messages):return
    message=dict(id=f'MSG_{state.next_control:06d}',task_id=task.task_id,kind=kind,source=source,
        holder=source,target=target,epoch=state.coordinator_epoch,created_at_s=state.time_s,
        next_hop_s=state.time_s+1,status='buffered',path=[source],attempts=0,bytes=2048,reason='Waiting for a feasible contact')
    state.next_control+=1;state.control_messages.append(message)


def submit(state,task):
    if task.request_source is None:
        eligible=[s.id for s in state.satellites.values() if s.can_relay]
        task.request_source=(eligible or list(state.satellites))[0]
    task.coordinator_id=state.coordinator['node_id'] if state.coordinator else None
    task.coordinator_epoch=state.coordinator_epoch
    task.coordination_status='buffered'
    enqueue(state,task,'request',task.request_source,task.coordinator_id)


def share(state,task):
    if not state.coordinator:return
    coordinator=state.coordinator['node_id'];task.coordinator_id=coordinator;task.coordinator_epoch=state.coordinator_epoch
    if coordinator not in task.shared_with and task.coordination_status in {'ready','sharing','committed'}:
        holders=[n for n in task.shared_with if state.satellites[n].can_relay]
        source=(holders or task.shared_with or [task.request_source])[0]
        enqueue(state,task,'election_manifest',source,coordinator)
        if not task.owner:task.coordination_status='buffered'
        return
    previous=task.coordination_status
    task.coordination_status='committed' if task.owner else ('ready' if previous in {'ready','committed'} and coordinator in task.shared_with else 'sharing')
    task.control_ready_s=state.time_s+2
    if coordinator not in task.shared_with:task.shared_with.append(coordinator)
    for sat in state.satellites.values():
        if sat.id!=coordinator:enqueue(state,task,'manifest',coordinator,sat.id)
    state.log('manifest',f'{task.task_id}: {coordinator} sharing request and requesting feasible bids',coordinator,task.task_id)


def advance(state):
    elect(state)
    links={l.key:l for l in build_links(state) if l.available}
    used={}  # Bounded control channel: eight 2KB messages per radio per second.
    for m in state.control_messages:
        if m['status'] in {'delivered','expired','superseded'}:continue
        t=state.tasks.get(m['task_id'])
        if t is None or t.status in TERMINAL or state.time_s>t.delivery_deadline:m['status']='expired';continue
        if not state.coordinator:m['status']='buffered';m['reason']='No healthy coordinator';continue
        leader=state.coordinator['node_id']
        if m['kind']=='request':m['target']=leader;m['epoch']=state.coordinator_epoch
        elif m['epoch']!=state.coordinator_epoch:m['status']='superseded';continue
        if m['holder']==m['target']:
            m['status']='delivered';m['delivered_at_s']=state.time_s;state.counters['control_delivered']+=1
            if m['kind']=='request':
                t.request_path=m['path'][:];t.coordination_status='received';share(state,t)
            elif m['kind']=='election_manifest':
                if m['target'] not in t.shared_with:t.shared_with.append(m['target'])
                t.coordination_status='received' if not t.owner else 'committed';share(state,t)
            elif m['target'] not in t.shared_with:t.shared_with.append(m['target'])
            state.message_audit.append(dict(time_s=state.time_s,message_id=m['id'],task_id=t.task_id,kind=m['kind'],target=m['target'],path=m['path'][:]))
            continue
        route=control_path(state,m['holder'],m['target'])
        if not route:m['status']='buffered';m['reason']='No antenna/LOS/radio path; retained in holder buffer';continue
        if state.time_s<m['next_hop_s']:continue
        path,cost=route;a,b=path[:2];key=pair_key(a,b);link=links.get(key)
        if not link:continue
        if used.get(a,0)>=8 or used.get(b,0)>=8:m['status']='buffered';m['reason']='Control radio queue';continue
        used[a]=used.get(a,0)+1;used[b]=used.get(b,0)+1;m['attempts']+=1
        if state.config.space_effects and state.rng.random()<link.loss:
            state.counters['control_retries']+=1;m['reason']='Control ACK lost; retrying';m['next_hop_s']=state.time_s+1;continue
        m['holder']=b;m['path'].append(b);m['status']='in_flight';m['reason']='Routed control message'
        m['next_hop_s']=state.time_s+max(1.,2*link.latency_s)
    for t in state.active_tasks():
        if t.coordination_status=='sharing' and state.time_s>=t.control_ready_s:t.coordination_status='ready'
    # Keep every undelivered buffer; bound the terminal message history.
    done=[m for m in state.control_messages if m['status'] in {'delivered','expired','superseded'}]
    discard={m['id'] for m in done[:-160]}
    state.control_messages[:]=[m for m in state.control_messages if m['id'] not in discard]


def guard_commit(state,task,node_id,expected_version,epoch,demonstration=False):
    reason=None
    if not state.coordinator or epoch!=state.coordinator_epoch:reason='Stale coordinator epoch'
    elif expected_version!=task.lease_version:reason='Stale ownership version'
    elif task.owner is not None:reason='Existing owner lease is locked'
    elif node_id not in task.shared_with:reason='Node has not acknowledged the task manifest'
    elif not control_path(state,state.coordinator['node_id'],node_id):reason='Allocation command has no communication path'
    accepted=reason is None
    record=dict(time_s=state.time_s,task_id=task.task_id,candidate=node_id,expected_version=expected_version,
        current_version=task.lease_version,epoch=epoch,result='accepted' if accepted else 'rejected',reason=reason or 'Single-owner CAS + resource admission')
    state.commit_audit.append(record)
    if not accepted:
        state.counters['conflicts_prevented']+=1
        state.log('conflict',f'{task.task_id}: rejected competing/stale claim by {node_id} — {reason}',node_id,task.task_id)
    elif not demonstration:state.counters['ownership_commits']+=1
    return accepted


def conflict_demo(state,task):
    candidates=[s.id for s in state.satellites.values() if s.id!=task.owner]
    return guard_commit(state,task,(candidates or [task.owner])[0],max(0,task.lease_version-1),state.coordinator_epoch,True)
