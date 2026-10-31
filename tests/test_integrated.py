"""Independent behavior checks for full-chain feasibility, data continuity and transport."""
import json, math, time
from dataclasses import asdict
import numpy as np
import pytest
from fastapi.testclient import TestClient
from backend.app.engine import Engine
from backend.app.models import Config
from backend.app.api import create_app
from backend.app.network import build_links,pair_key,PACKET_MB
from backend.app.resources import can_host,ledgers


def make(**kwargs):return Engine(Config(auto_tasks=False,random_revival=False,**kwargs),seed_tasks=False)
def run_until(e,predicate,limit=120):
    for _ in range(limit):
        if predicate():return
        e.step();e.validate()
    assert predicate(),e.snapshot()['tasks']

def test_dynamic_request_full_pipeline():
    e=make();t=e.add_task()
    run_until(e,lambda:t.status=='delivered')
    assert [x['status'] for x in t.transitions]==['pending','assigned','captured','processed','delivered']
    assert t.valid_product and t.delivered_at<=t.delivery_deadline and t.captures==1
    assert e.state.counters['delivered_mb']==t.output_data_mb
    assert t.product_hash and t.owner
    assert e.validate()

def test_immediate_reallocation_without_clock_advance():
    e=make();t=e.add_task();old=t.owner;now=e.state.time_s
    e.inject(old,'thermal')
    assert e.state.time_s==now
    assert t.status=='assigned' and t.owner!=old
    assert t.reassignments==1 and e.state.repair['iterations']==12
    assert all(x['time_s']==now for x in e.state.recovery[-1]['stages'])
    run_until(e,lambda:t.status=='delivered')

def test_captured_cpu_fault_retains_data_and_checkpoint():
    e=make();t=e.add_task();run_until(e,lambda:t.status=='captured')
    e.step(2);owner=t.owner;capture_at=t.captured_at;progress=t.progress_cycles
    e.inject(owner,'cpu',duration_s=6);e.step(4)
    assert t.status=='captured' and t.holder==owner and t.progress_cycles==progress
    run_until(e,lambda:t.status=='delivered')
    assert t.captures==1 and t.captured_at==capture_at and t.reassignments==0

def test_processed_offline_holder_is_buffered_then_resumes():
    e=make();t=e.add_task();run_until(e,lambda:t.status=='processed')
    owner=t.holder;capture_at=t.captured_at
    e.inject(owner,'offline',duration_s=5);e.step(3)
    assert t.status=='processed' and t.holder==owner
    run_until(e,lambda:t.status=='delivered')
    assert t.captured_at==capture_at and t.captures==1
    assert any(x['node_id']==owner for x in e.state.revived)

def test_radio_fault_after_capture_allows_local_processing():
    e=make();t=e.add_task();run_until(e,lambda:t.status=='captured');old=t.owner
    e.inject(old,'radio',duration_s=23)
    run_until(e,lambda:t.status=='processed')
    assert t.owner==old and t.holder==old and t.captures==1
    run_until(e,lambda:t.status=='delivered')

def test_link_failure_uses_alternative_contact_without_recapture():
    e=make();t=e.add_task();run_until(e,lambda:t.status=='processed')
    hop=t.route_hops[0];original=t.route[:];stamp=t.captured_at
    e.block_link(hop['source'],hop['target'])
    assert t.route and t.route!=original
    assert e.state.counters['reroutes']>=1
    run_until(e,lambda:t.status=='delivered')
    assert t.captures==1 and t.captured_at==stamp

def test_stale_sensor_requires_elapsed_simulation_time():
    e=make();node=next(iter(e.state.satellites));e.inject(node,'stale')
    assert e.state.satellites[node].health=='healthy'
    e.step(9);assert e.state.satellites[node].health=='isolated'
    e.validate()

def test_explicit_visibility_is_independent_of_mesh():
    e=make();t=e.add_task(allowed_satellites=['SAT-01']);t.visibility_windows={'SAT-01':[]}
    assert not can_host(e.state,e.state.satellites['SAT-01'],t)[0]
    assert all(l.available for l in build_links(e.state) if l.target!='GND')

def test_battery_alone_is_not_sufficient():
    e=make();sat=e.state.satellites['SAT-01'];sat.battery_wh=100;sat.attitude_error_deg=30
    t=e.add_task(allowed_satellites=['SAT-01'])
    assert t.status=='deferred' and t.owner is None

def test_safe_battery_and_storage_reservations():
    e=make();
    for sat in e.state.satellites.values():sat.storage_capacity_mb=45
    t=e.add_task();assert t.status=='deferred'
    e=make()
    for sat in e.state.satellites.values():sat.battery_wh=12.1
    t=e.add_task();assert t.status=='deferred'
    e.step(100);assert t.status=='delivered'  # Sunlight can restore a deferred node's reserve.
    e=make();t=e.add_task(minimum_quality=.99);e.step(100);assert t.status=='expired'

def test_priority_update_preserves_ids_repeat_uses_new_ids():
    e=make();a=e.add_task(event_id='FIRE_07');b=e.add_task(event_id='FIRE_07')
    ids=set(e.state.tasks);changed=e.update_priority('FIRE_07',5)
    assert ids==set(e.state.tasks)==set(changed) and a.task_id!=b.task_id
    assert a.priority==b.priority==5

def test_storage_failure_marks_inaccessible_data_failed():
    e=make();t=e.add_task();run_until(e,lambda:t.status=='captured');e.inject(t.owner,'storage')
    assert t.status=='failed';assert e.validate()

def test_crc_rejects_partial_and_bit_flipped_packets_then_retries():
    for mode,counter in [('bit_flip','bit_flips'),('partial_packet','partial_packets')]:
        e=make(space_effects=True);e.state.next_effect_s=1e9;t=e.add_task()
        run_until(e,lambda:t.status=='processed');hop=t.route_hops[0];key=pair_key(hop['source'],hop['target'])
        e.state.effects[key]={'kind':mode,'until_s':e.state.time_s+5,'source':hop['source'],'target':hop['target']};e.state.version+=1
        e.step(4)
        assert e.state.counters[counter]>0 and t.status!='delivered'
        run_until(e,lambda:t.status=='delivered')
        assert t.valid_product and e.state.counters['retries']>0
        assert e.state.counters['packets_acked']>=math.ceil(t.output_data_mb/PACKET_MB)

def test_forty_nodes_and_symmetric_weights():
    e=make(satellites_per_swarm=20)
    assert len(e.state.satellites)==40
    graph=build_links(e.state);sat_links=[l for l in graph if l.target!='GND']
    assert len(sat_links)==40*39//2
    e.add_task();e.step(40);e.validate()
    assert all(math.isfinite(l.doppler_hz) and l.weight>0 for l in graph)
    assert len({l.key for l in graph})==len(graph)

def test_true_circular_orbits_eclipse_and_seed_replay():
    e=make();first=e.state.satellites['SAT-01'].position[:];e.step(100)
    assert first!=e.state.satellites['SAT-01'].position
    for sat in e.state.satellites.values():
        radius=math.sqrt(sum(x*x for x in sat.position));assert abs(radius-(6921 if sat.swarm=='SWARM-01' else 7021))<1e-7
    assert any(s.eclipse for s in e.state.satellites.values())
    a=Engine(Config(space_effects=True));b=Engine(Config(space_effects=True))
    a.step(160);b.step(160)
    # Runtime measurements naturally differ. Mission state must agree.
    assert a.snapshot()['tasks']==b.snapshot()['tasks']
    assert a.snapshot()['events']==b.snapshot()['events']
    assert a.snapshot()['satellites']==b.snapshot()['satellites']

def test_high_speed_fixed_substeps_match_normal_steps():
    a=Engine(Config(space_effects=True));b=Engine(Config(space_effects=True))
    a.step(100)
    for _ in range(100):b.step()
    assert a.snapshot()['tasks']==b.snapshot()['tasks']
    assert a.snapshot()['metrics']==b.snapshot()['metrics']

def test_random_revival_has_fresh_telemetry_hysteresis():
    e=Engine(Config(auto_tasks=False,random_revival=True),seed_tasks=False);n='SAT-01';e.inject(n,'offline')
    at=e.state.satellites[n].revival_at_s
    e.step(math.ceil(at)+3)
    assert e.state.satellites[n].health=='healthy'
    assert any(r['node_id']==n for r in e.state.revived)

def test_api_validation_controls_weights_and_export():
    client=TestClient(create_app(Config(auto_tasks=False)))
    assert client.get('/api/health').status_code==200
    for body in [{'swarm_count':3},{'satellites_per_swarm':21},{'speed':101}]:assert client.post('/api/reset',json=body).status_code==422
    assert client.post('/api/battery',json={'node_id':'SAT-01','percent':101}).status_code==422
    assert client.post('/api/faults',json={'node_id':'BAD','kind':'cpu'}).status_code==404
    assert client.post('/api/links',json={'source':'SAT-01','target':'SAT-01'}).status_code==422
    assert client.post('/api/tasks',json={'observation_window':[10,1]}).status_code==422
    assert client.post('/api/tasks',json={'priority':6}).status_code==422
    assert client.post('/api/tasks',json={'priority':5,'event_id':'FIRE_TEST'}).status_code==201
    assert client.post('/api/control',json={'action':'step','ticks':100}).status_code==200
    csv=client.get('/api/weights.csv').text.strip().splitlines();assert len(csv)>3
    rows=[r.split(',') for r in csv[1:]]
    for i in range(0,len(rows),2):assert rows[i][0]==rows[i+1][1] and rows[i][2]==rows[i+1][2]
    assert client.get('/api/export').json()['tasks']
    assert client.post('/api/settings',json={'space_effects':True,'speed':100}).json()['config']['speed']==100


def test_server_speeds_preserve_fixed_step_random_sequence():
    from backend.app.api import Service
    slow=Service(Config(speed=1,space_effects=True));fast=Service(Config(speed=100,space_effects=True))
    slow.engine.state.paused=fast.engine.state.paused=False
    for _ in range(200):slow.tick()
    for _ in range(2):fast.tick()
    assert slow.engine.snapshot()['tasks']==fast.engine.snapshot()['tasks']
    assert slow.engine.snapshot()['events']==fast.engine.snapshot()['events']
    assert slow.engine.snapshot()['metrics']==fast.engine.snapshot()['metrics']


def test_external_cpu_stress_reallocates_uncaptured_work_and_throttles_images():
    e=make();t=e.add_task();old=t.owner;e.set_stress(old,cpu_pct=85)
    assert t.owner!=old and t.status=='assigned'
    run_until(e,lambda:t.status=='captured');owner=t.owner;before=t.progress_cycles
    e.set_stress(owner,cpu_pct=89);e.step(1)
    assert 0<t.progress_cycles-before<e.state.satellites[owner].cycles_per_s*t.cpu_demand/100
    assert t.holder==owner and t.captures==1
    assert e.validate()
