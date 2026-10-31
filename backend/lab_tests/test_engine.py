import json
import pytest

from backend.lab_core.engine import Engine
from backend.lab_core.models import Config, TaskStatus


def tick(e,n=1):
    for _ in range(n):
        e.step()
        e.validate()


def bare(nodes=6, **kwargs):
    return Engine(Config(nodes=nodes,auto_tasks=False,**kwargs),seed_tasks=False)


def test_nominal_campaigns_are_delivered():
    e=Engine(Config(auto_tasks=False))
    tick(e,60)
    m=e.snapshot()['metrics']
    assert m['completed']==4 and m['missed']==0
    assert m['delivered_mb']==36
    assert m['paired_campaigns']==2
    assert m['faults_detected']==0


@pytest.mark.parametrize('nodes',[3,6,20,40])
def test_dynamic_swarm_sizes(nodes):
    e=Engine(Config(nodes=nodes,auto_tasks=True))
    tick(e,100)
    assert len(e.state.satellites)==nodes
    assert e.snapshot()['metrics']['completed']>=4
    assert e.snapshot()['metrics']['faults_detected']==0


def test_compute_failure_retries_without_duplicate_owner():
    e=Engine(Config(auto_tasks=False))
    tick(e)
    task=next(t for t in e.state.tasks.values() if t.status==TaskStatus.RUNNING)
    old=task.owner
    assert task.progress_cpu_s>0
    e.inject(old,'offline')
    assert task.owner is None and task.status==TaskStatus.QUEUED
    assert task.lost_work_cpu_s>0 and task.progress_cpu_s==0
    tick(e,60)
    assert task.status==TaskStatus.COMPLETED
    assert task.owner!=old
    assert task.reassignments>=1
    assert all(old not in (l['source'],l['target']) for l in e.snapshot()['links'])


def test_failed_data_holder_does_not_invent_data_copy():
    e=bare()
    task=e.add_task(processing_s=2,allowed_satellites=['S2'],deadline_after_s=200)
    tick(e)
    assert task.status==TaskStatus.DOWNLINK and task.holder=='S2'
    e.inject('S2','offline')
    tick(e,6)
    assert task.status==TaskStatus.DOWNLINK and task.holder=='S2'
    assert task.attempts==1
    e.recover('S2')
    tick(e,50)
    assert task.status==TaskStatus.COMPLETED
    assert e.state.counters['recovered_nodes']>=1


def test_relay_link_failure_repairs_existing_product():
    e=bare()
    task=e.add_task(processing_s=2,output_mb=20,allowed_satellites=['S2'],deadline_after_s=180)
    tick(e,2)
    assert task.route and task.route.hops
    hop=task.route.hops[0]
    from backend.lab_core.network import pair_key
    e.state.blocked_links.add(pair_key(hop.source,hop.target))
    e._reconcile()
    assert task.route is None
    assert task.holder=='S2'
    tick(e,60)
    assert task.status==TaskStatus.COMPLETED
    assert e.state.counters['reroutes']>=1
    assert task.attempts==1


def test_transient_node_returns_after_fresh_samples():
    e=bare()
    e.inject('S3','offline',duration_s=6)
    tick(e,8)
    assert not e.state.satellites['S3'].faults
    assert e.state.satellites['S3'].health=='healthy'


def test_frozen_telemetry_becomes_stale():
    e=bare()
    e.inject('S2','stale')
    frozen=e.state.satellites['S2'].telemetry.time_s
    tick(e,6)
    sat=e.state.satellites['S2']
    assert sat.telemetry.time_s==frozen
    assert sat.health=='isolated'
    assert 'sensor data stale' in sat.reasons


def test_cpu_failure_keeps_radio_capability():
    e=bare()
    e.inject('S2','cpu')
    sat=e.state.satellites['S2']
    assert not sat.can_compute and sat.can_relay
    assert any(l['source']=='S2' or l['target']=='S2' for l in e.snapshot()['links'])


def test_radio_failure_preserves_running_processing():
    e=bare()
    t=e.add_task(processing_s=12,allowed_satellites=['S2'])
    tick(e)
    e.inject('S2','radio')
    tick(e,8)
    assert t.status==TaskStatus.DOWNLINK
    assert t.holder=='S2' and t.attempts==1
    assert not e.state.satellites['S2'].can_relay


def test_cpu_cooling_fault_causes_gradual_thermal_isolation():
    e=bare()
    initial=e.state.satellites['S2'].temperature_c
    e.set_stress('S2',cpu_pct=100,cooling_scale=.2)
    tick(e)
    assert e.state.satellites['S2'].temperature_c>initial
    assert e.state.satellites['S2'].health=='healthy'
    tick(e,20)
    sat=e.state.satellites['S2']
    assert sat.health=='isolated'
    assert 'thermal protection' in sat.reasons


def test_unmodelled_heating_trips_residual_cusum():
    e=bare()
    e.set_stress('S2',heat_w=20)
    tick(e,3)
    assert 'S2' in e.monitor.latched
    assert 'CUSUM: unexpected heating' in e.state.satellites['S2'].reasons


def test_battery_drain_crosses_reserve():
    e=bare()
    sat=e.state.satellites['S2']
    sat.battery_wh=12.7
    sat.telemetry.battery_wh=12.7
    e.set_stress('S2',drain_w=500)
    tick(e,5)
    assert sat.battery_wh<=e.state.config.reserve_wh
    assert sat.health=='isolated'


def test_all_nodes_unavailable_defers_then_expires():
    e=bare()
    for sat in e.state.satellites:
        e.inject(sat,'offline')
    t=e.add_task(deadline_after_s=8)
    tick(e,5)
    assert t.status==TaskStatus.MISSED and t.attempts==0


def test_non_tick_deadline_never_counts_late_delivery():
    e=bare()
    t=e.add_task(processing_s=1,output_mb=1,deadline_after_s=3.5,allowed_satellites=['S1'])
    tick(e,3)
    assert t.status==TaskStatus.MISSED


def test_transfer_contention_respects_pair_and_storage_budgets():
    e=bare()
    for _ in range(12):
        e.add_task(processing_s=2,output_mb=20,cpu_demand=10,
                   allowed_satellites=['S2'],deadline_after_s=300)
    tick(e,120)
    assert e.state.counters['delivered_mb']>0
    assert all(x['sent_mb']<=x['capacity_mb']+1e-8 for x in e.state.transfer_log)
    assert all(s.storage_used_mb+s.storage_reserved_mb<=s.storage_capacity_mb+1e-7 for s in e.state.satellites.values())


def test_payload_and_visibility_limits():
    e=bare()
    t=e.add_task(kind='remote_sensing',allowed_satellites=['S4'],deadline_after_s=20)
    tick(e,12)
    assert t.status==TaskStatus.MISSED and t.attempts==0


def test_seed_reproducibility():
    a,b=Engine(Config()),Engine(Config())
    tick(a,30);tick(b,30)
    sa,sb=a.snapshot(),b.snapshot()
    for snap in (sa,sb):
        snap['allocator'].pop('runtime_ms')
    assert sa==sb


def test_noise_is_measurement_noise_not_hidden_energy_creation():
    a,b=bare(noise_scale=0),bare(noise_scale=3)
    tick(a,10);tick(b,10)
    for node in a.state.satellites:
        x,y=a.state.satellites[node],b.state.satellites[node]
        assert x.battery_wh==y.battery_wh
        assert x.temperature_c==y.temperature_c
    assert a.state.satellites['S1'].telemetry.temperature_c!=b.state.satellites['S1'].telemetry.temperature_c


def test_task_queue_is_bounded_and_campaign_atomic():
    e=bare()
    e.state.config.max_active_tasks=3
    e.add_campaign()
    before=len(e.state.tasks)
    with pytest.raises(ValueError):e.add_campaign()
    assert len(e.state.tasks)==before


def test_external_cpu_throttles_work_without_over_service():
    e=bare()
    t=e.add_task(cpu_demand=50,processing_s=30,allowed_satellites=['S2'])
    tick(e)
    initial=t.progress_cpu_s
    e.set_stress('S2',cpu_pct=70)
    tick(e)
    assert t.progress_cpu_s-initial<=15*e.state.config.dt_s+1e-7


def test_snapshot_is_strict_json():
    e=Engine(Config())
    tick(e,5)
    json.dumps(e.snapshot(),allow_nan=False)
