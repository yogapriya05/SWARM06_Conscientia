import pytest
from fastapi.testclient import TestClient
from backend.lab_core.api import create_app
from backend.lab_core.models import Config


@pytest.fixture
def client():
    with TestClient(create_app(Config(auto_tasks=False))) as c:
        yield c


def test_static_dashboard_and_health(client):
    assert client.get('/api/health').json()['status']=='ok'
    assert 'Swarm Lab' in client.get('/').text
    assert client.get('/static/app.js').status_code==200


def test_control_create_fault_recover_and_reset(client):
    r=client.post('/api/tasks',json={'kind':'gnss','region':'Coast'})
    assert r.status_code==201
    assert client.post('/api/control',json={'action':'step','ticks':2}).json()['time_s']==4
    assert client.post('/api/faults',json={'node_id':'S2','kind':'offline'}).status_code==200
    assert client.post('/api/recover',json={'node_id':'S2'}).status_code==200
    assert client.post('/api/stress',json={'node_id':'S2','cpu_pct':100,'cooling_scale':.2}).status_code==200
    s=client.post('/api/reset',json={'nodes':20,'auto_tasks':False}).json()
    assert len(s['satellites'])==20 and s['time_s']==0 and s['paused']


@pytest.mark.parametrize('body',[{'nodes':0},{'nodes':41},{'noise_scale':float('inf')},{'admm_iterations':0},{'unknown':1}])
def test_invalid_reset_is_rejected_atomically(client,body):
    if body.get('noise_scale')==float('inf'):
        # JSON non-finite number parsed by the server must be rejected, not normalized.
        r=client.post('/api/reset',content='{"noise_scale":Infinity}',headers={'Content-Type':'application/json'})
    else:r=client.post('/api/reset',json=body)
    assert r.status_code==422
    assert len(client.get('/api/state').json()['satellites'])==6


def test_invalid_task_and_unknown_node(client):
    assert client.post('/api/tasks',json={'cpu_demand':-1}).status_code==422
    assert client.post('/api/faults',json={'node_id':'S20','kind':'offline'}).status_code==404
    before=len(client.get('/api/state').json()['tasks'])
    assert client.post('/api/tasks',json={'allowed_satellites':['S99']}).status_code==409
    assert len(client.get('/api/state').json()['tasks'])==before


def test_link_controls_and_export(client):
    r=client.post('/api/links',json={'source':'S1','target':'S2'})
    assert r.status_code==200
    assert not any(l['key']=='S1|S2' for l in r.json()['links'])
    assert client.post('/api/links',json={'source':'S1','target':'S1'}).status_code==422
    r=client.get('/api/export')
    assert 'attachment' in r.headers['content-disposition']
    assert r.json()['config']['nodes']==6


def test_websocket_sends_live_snapshot(client):
    with client.websocket_connect('/ws') as ws:
        snapshot=ws.receive_json()
        assert snapshot['paused'] and len(snapshot['satellites'])==6


def test_running_loop_advances_and_pause_stops(client):
    import time
    assert client.post('/api/control',json={'action':'run'}).status_code==200
    time.sleep(1.2)
    paused=client.post('/api/control',json={'action':'pause'}).json()['time_s']
    assert paused>0
    time.sleep(.6)
    assert client.get('/api/state').json()['time_s']==paused


def test_reset_epoch_distinguishes_old_live_updates(client):
    initial=client.get('/api/state').json()
    client.post('/api/control',json={'action':'step','ticks':2})
    new=client.post('/api/reset',json={'nodes':6}).json()
    assert new['run_epoch']==initial['run_epoch']+1
    assert client.get('/api/state').json()['run_epoch']==new['run_epoch']
