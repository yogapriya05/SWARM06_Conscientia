"""Immutable initial and reconstruction graph snapshots; minimum-cost spanning forest."""
from dataclasses import asdict
from .network import build_links

def record(state,reason):
    links=build_links(state);parent={n:n for n in state.satellites}
    def root(n):
        while parent[n]!=n:parent[n]=parent[parent[n]];n=parent[n]
        return n
    backbone=[]
    for link in sorted([l for l in links if l.available and l.target!='GND'],key=lambda l:l.weight):
        a,b=root(link.source),root(link.target)
        if a!=b:parent[a]=b;backbone.append(link.key)
    state.graph_signature=tuple(l.key for l in links if l.available and l.target!='GND')
    state.graph_epoch+=1
    snapshot=dict(epoch=state.graph_epoch,time_s=state.time_s,reason=reason,
        coordinator=state.coordinator.copy() if state.coordinator else None,
        nodes=[dict(id=s.id,position=s.position[:],node_weight=s.node_weight,health=s.health) for s in state.satellites.values()],
        edges=[dict(source=l.source,target=l.target,key=l.key,weight=l.weight,available=l.available,reason=l.reason) for l in links if l.target!='GND'],backbone=backbone)
    if state.graph_epoch==1:state.initial_graph=snapshot
    state.graph_history.append(snapshot)
