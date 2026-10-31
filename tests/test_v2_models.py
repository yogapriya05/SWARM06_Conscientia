import math,json
import numpy as np
from fastapi.testclient import TestClient
from backend.app.engine import Engine
from backend.app.models import Config
from backend.app.api import create_app
from backend.app.orbits import (initial_state,acceleration,rk4,MU,J2,GRAVITY_RADIUS_KM,YEAR_S,
    sun_direction,earth_point,OMEGA_EARTH,is_eclipsed,update_positions)
from backend.app.antennas import evaluate,ray_hits_body
from backend.app.network import build_links,control_path,pair_key
from backend.app import coordination

def engine(**kwargs):return Engine(Config(auto_tasks=False,random_failures=False,random_revival=False,**kwargs),seed_tasks=False)
def until(e,predicate,limit=100):
    for _ in range(limit):
        if predicate():return
        e.step(emit_snapshot=False);e.validate()
    assert predicate()

def test_exact_fifty_kilometre_adjacent_initial_chords_and_common_plane():
    e=engine(satellites_per_swarm=20);sats=list(e.state.satellites.values())
    normals=[]
    for a,b in zip(sats,sats[1:]):assert abs(np.linalg.norm(np.array(a.position)-b.position)-50)<1e-8
    for s in sats:
        assert abs(np.linalg.norm(s.position)-6921)<1e-8
        normal=np.cross(s.position,s.velocity);normals.append(normal/np.linalg.norm(normal))
    assert np.max(np.linalg.norm(np.array(normals)-normals[0],axis=1))<1e-12

def test_j2_acceleration_matches_equatorial_formula_and_rk4_converges():
    p=np.array([7000.,0.,0.]);a=acceleration(p)
    expected=-MU/7000**2-1.5*J2*MU*GRAVITY_RADIUS_KM**2/7000**4
    assert abs(a[0]-expected)<1e-14 and np.allclose(a[1:],0)
    assert not np.allclose(a,acceleration(p,j2=0),rtol=1e-6)
    r,v=initial_state(0,1);r2,v2=r.copy(),v.copy()
    for _ in range(600):r,v=rk4(r,v,1.)
    for _ in range(1200):r2,v2=rk4(r2,v2,.5)
    assert np.linalg.norm(r-r2)<1e-6 and np.linalg.norm(v-v2)<1e-8

def test_annual_sun_earth_spin_and_fixed_far_field_flux():
    assert np.linalg.norm(sun_direction(0)-sun_direction(YEAR_S/4))>1
    assert np.allclose(sun_direction(0),sun_direction(YEAR_S),atol=1e-12)
    assert np.allclose(earth_point(0,0,2*math.pi/OMEGA_EARTH),earth_point(0,0,0),atol=1e-7)
    assert is_eclipsed(np.array([-6921.,0,0]),np.array([1.,0,0]))
    assert not is_eclipsed(np.array([6921.,0,0]),np.array([1.,0,0]))
    e=engine();sunlit=next(s for s in e.state.satellites.values() if not s.eclipse)
    assert sunlit.solar_flux_w_m2==1361 and sunlit.solar_heat_w>0
    e.state.time_s=3000;update_positions(e.state)
    for s in e.state.satellites.values():
        if s.eclipse:assert s.solar_w==0 and s.solar_heat_w==0
        else:assert s.solar_flux_w_m2==1361

def test_ray_body_shadow_and_pair_beam_gate():
    assert ray_hits_body((.055,0,0),(-1,0,0))
    assert not ray_hits_body((.055,0,0),(1,0,0))
    e=engine();s=e.state.satellites['SAT-01'];before=[l for l in build_links(e.state) if l.source==s.id and l.target!='GND']
    assert all(l.available and l.antenna_clear and l.tx_gain>0 for l in before)
    e.inject(s.id,'antenna');after=[l for l in build_links(e.state) if l.source==s.id and l.target!='GND']
    assert any(not l.available and not l.antenna_clear for l in after)
    assert any(abs(a.weight-b.weight)>.5 for a,b in zip(before,after))
    # A gimballed beam can point into its own body: no propagation through the box.
    normal=np.array([math.cos(math.radians(100)),0,-math.sin(math.radians(100))])
    target=np.array(s.position)+np.asarray(s.body_axes_eci)@normal*50
    result=evaluate(s,target)
    assert not result['clear'] and result['body_blocked']

def test_lowest_weight_leader_buffered_request_and_manifest_before_commit():
    e=engine();leader=e.state.coordinator['node_id']
    eligible=[s for s in e.state.satellites.values() if s.can_compute and s.can_relay]
    assert leader==min(eligible,key=lambda s:(s.node_weight,s.id)).id
    t=e.add_task();assert t.owner is None and t.coordination_status=='buffered'
    until(e,lambda:t.owner is not None)
    assert t.request_path[0]==t.request_source and t.request_path[-1]==leader
    assert t.owner in t.shared_with and e.state.counters['ownership_commits']==1
    assert e.state.commit_audit[-1]['result']=='accepted'

def test_disconnected_ingress_buffers_and_retries_after_reconnection():
    e=engine();source='SAT-01';leader=e.state.coordinator['node_id'];assert source!=leader
    e.inject(source,'radio');t=e.add_task(request_source=source);e.step(6,emit_snapshot=False)
    requests=[m for m in e.state.control_messages if m['task_id']==t.task_id and m['kind']=='request']
    assert t.owner is None and requests[0]['status']=='buffered' and requests[0]['holder']==source
    e.recover(source);until(e,lambda:t.owner is not None)
    assert t.task_id in e.state.tasks and t.request_path[0]==source

def test_conflicting_claim_rejected_without_changing_owner_or_buffers():
    e=engine();t=e.add_task();until(e,lambda:t.owner is not None)
    owner=t.owner;version=t.lease_version;cpu=e.state.satellites[owner].allocated_cpu
    assert not coordination.conflict_demo(e.state,t)
    assert t.owner==owner and t.lease_version==version and e.state.satellites[owner].allocated_cpu==cpu
    assert e.state.counters['conflicts_prevented']==1 and e.state.commit_audit[-1]['result']=='rejected'

def test_initial_graph_persists_and_reconstruction_snapshots_are_immutable():
    e=engine();first=json.dumps(e.snapshot()['graph_history'][0],sort_keys=True)
    for _ in range(18):e.reconstruct('test snapshot')
    snapshots=e.snapshot()['graph_history']
    assert snapshots[0]['epoch']==1 and len(snapshots)==16
    assert json.dumps(snapshots[0],sort_keys=True)==first
    assert snapshots[-1]['epoch']==e.state.graph_epoch
    assert len(snapshots[0]['backbone'])==len(e.state.satellites)-1

def test_rare_node_faults_remain_independent_of_packet_effect_switch():
    e=Engine(Config(auto_tasks=False,space_effects=False,random_failures=True,random_failure_rate_per_sat_s=.01),seed_tasks=False)
    e.step(120,emit_snapshot=False);e.validate()
    assert e.state.counters['random_failures']>0
    assert any(x['category']=='random_fault' for x in e.state.events)

def test_api_snapshots_are_json_safe_and_cache_status_is_normal():
    c=TestClient(create_app(Config(auto_tasks=False)))
    assert c.post('/api/tasks',json={'priority':5}).status_code==201
    result=c.post('/api/control',json={'action':'step','ticks':6});assert result.status_code==200
    assert c.post('/api/conflicts/demo').status_code==200
    assert c.get('/').headers['cache-control']=='no-cache'
    assert c.get('/api/state').json()['environment']['j2']>0

def test_new_coordinator_requires_manifest_transfer_when_copy_missing():
    e=engine();t=e.add_task();until(e,lambda:t.owner is not None)
    original=t.owner
    # Force the lowest-cost successor to have no manifest copy, reproducing a late-request election.
    leader=e.state.coordinator['node_id'];successor=min([s for s in e.state.satellites.values() if s.id!=leader],key=lambda s:(s.node_weight,s.id)).id
    t.shared_with=[leader];t.owner=None;t.status='pending';t.coordination_status='ready'
    e.inject(leader,'cpu')
    new=e.state.coordinator['node_id']
    assert new not in t.shared_with and t.owner is None and t.coordination_status=='buffered'
    assert any(m['kind']=='election_manifest' and m['target']==new for m in e.state.control_messages)
    until(e,lambda:new in t.shared_with)
    assert t.task_id in e.state.tasks
