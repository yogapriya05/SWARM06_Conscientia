"""Single-authority engine; lock serializes ticks and operator actions."""
import asyncio,csv,io
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from threading import RLock
from fastapi import FastAPI,HTTPException,WebSocket,WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse,JSONResponse,Response
from fastapi.exceptions import RequestValidationError
from .engine import Engine
from .models import Config
from .schemas import ConfigRequest,Settings,TaskRequest,Fault,Recovery,Battery,Stress,Control,Step,LinkRequest,Priority

class Service:
    def __init__(self,config=None):self.lock=RLock();self.engine=Engine(config);self.run_epoch=0;self.sim_budget_s=0.
    def snapshot(self):
        with self.lock:return self.engine.snapshot()|{'run_epoch':self.run_epoch}
    def tick(self):
        with self.lock:
            if not self.engine.state.paused:
                self.sim_budget_s+=.5*self.engine.state.config.speed
                whole=int(self.sim_budget_s)
                if whole:self.engine.step(whole,emit_snapshot=False);self.sim_budget_s-=whole

def create_app(config=None):
    service=Service(config)
    @asynccontextmanager
    async def lifespan(app):
        async def loop():
            while True:
                start=asyncio.get_running_loop().time()
                await asyncio.to_thread(service.tick)
                await asyncio.sleep(max(.01,.5-(asyncio.get_running_loop().time()-start)))
        task=asyncio.create_task(loop())
        yield
        task.cancel()
        try:await task
        except asyncio.CancelledError:pass
    app=FastAPI(title='SWARM / Disaster Operations',version='3.0.0',lifespan=lifespan)
    app.state.service=service
    app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_methods=['*'],allow_headers=['*'])
    @app.exception_handler(RequestValidationError)
    async def invalid(request,exc):return JSONResponse(status_code=422,content={'detail':[{'loc':list(e['loc']),'msg':e['msg']} for e in exc.errors()]})
    @app.exception_handler(ValueError)
    async def value_error(request,exc):return JSONResponse(status_code=400,content={'detail':str(exc)})
    def node(n):
        if n not in service.engine.state.satellites:raise HTTPException(404,'Unknown satellite')
    @app.get('/health')
    @app.get('/api/health')
    def health():return {'status':'ok','version':'3.0.0'}
    @app.get('/api/state')
    @app.get('/state')
    def state():return service.snapshot()
    @app.post('/api/control')
    def control(body:Control):
        with service.lock:
            s=service.engine.state
            if body.action=='step':s.paused=True;service.engine.step(body.ticks,emit_snapshot=False)
            else:s.paused=body.action=='pause'
            s.version+=1;return service.snapshot()
    @app.post('/api/tick')
    @app.post('/api/step')
    @app.post('/step')
    def step(body:Step=Step()):
        with service.lock:service.engine.step(body.seconds or body.ticks,emit_snapshot=False);return service.snapshot()
    @app.post('/api/settings')
    def settings(body:Settings):
        with service.lock:
            s=service.engine.state
            for k,v in body.model_dump(exclude_none=True).items():setattr(s.config,k,v)
            if body.space_effects is False:s.effects.clear()
            if body.random_failures is True or body.random_failure_rate_per_sat_s is not None:s.next_random_failure_s=s.time_s+s.rng.expovariate(max(1e-12,s.config.random_failure_rate_per_sat_s*len(s.satellites)))
            if body.random_revival is True:
                for sat in s.satellites.values():
                    if sat.faults and sat.revival_at_s is None:sat.revival_at_s=s.time_s+s.rng.uniform(35,105)
            s.log('settings','Simulation controls updated');service.engine.reconstruct('Settings updated');return service.snapshot()
    @app.post('/api/config/swarms')
    @app.post('/api/reset')
    def reset(body:ConfigRequest|None=None):
        with service.lock:
            cfg=Config(**(asdict(service.engine.state.config)|body.model_dump(exclude_unset=True))) if body else service.engine.state.config
            service.engine=Engine(cfg);service.sim_budget_s=0.;service.run_epoch+=1;return service.snapshot()
    @app.post('/api/tasks',status_code=201)
    @app.post('/tasks',status_code=201)
    def tasks(body:TaskRequest):
        with service.lock:
            service.engine.add_task(**body.model_dump(exclude_none=True));return service.snapshot()
    @app.post('/api/campaigns',status_code=201)
    def campaign():
        with service.lock:service.engine.add_campaign();return service.snapshot()
    @app.post('/api/priority')
    def priority(body:Priority):
        with service.lock:service.engine.update_priority(body.event_id,body.priority);return service.snapshot()
    @app.post('/api/faults')
    @app.post('/api/failures')
    @app.post('/failures')
    def fault(body:Fault):
        with service.lock:
            s=service.engine.state;n=body.node_id or body.satellite_id
            kind=body.failure_mode or body.kind
            aliases={'complete_outage':'offline','radio_failure':'radio','battery_depletion':'battery','temperature':'thermal','attitude_not_oriented':'attitude','antenna_not_oriented':'antenna'}
            kind=aliases.get(kind,kind);duration=body.duration_s or body.duration_ticks
            targets=[sat.id for sat in s.satellites.values() if sat.swarm==body.swarm_id] if body.swarm_id else [n]
            if not targets or targets==[None]:raise HTTPException(422,'Choose a satellite or swarm')
            for target in targets:node(target)
            if kind=='network_partition':
                selected=set(targets)
                for a in selected:
                    for b in set(s.satellites)-selected:service.engine.block_link(a,b,True,duration)
            elif kind=='single_link_failure':
                others=[x for x in s.satellites if x!=targets[0]]
                if not others:raise HTTPException(400,'Need two satellites')
                service.engine.block_link(targets[0],others[0],True,duration)
            else:
                for target in targets:service.engine.inject(target,kind,duration)
            return service.snapshot()
    @app.post('/api/recover')
    def recover(body:Recovery):
        with service.lock:node(body.node_id);service.engine.recover(body.node_id,body.restore_resources);return service.snapshot()
    @app.post('/api/recover/{swarm_id}')
    def recover_swarm(swarm_id:str):
        with service.lock:
            targets=[sat.id for sat in service.engine.state.satellites.values() if sat.swarm==swarm_id]
            if not targets:raise HTTPException(404,'Unknown swarm')
            for n in targets:service.engine.recover(n)
            return service.snapshot()
    @app.post('/api/battery')
    def battery(body:Battery):
        with service.lock:node(body.node_id);service.engine.set_battery(body.node_id,body.percent);return service.snapshot()
    @app.post('/api/stress')
    def stress(body:Stress):
        with service.lock:node(body.node_id);service.engine.set_stress(body.node_id,body.cpu_pct,body.heat_w,body.drain_w,body.cooling_scale);return service.snapshot()
    @app.post('/api/links')
    def link(body:LinkRequest):
        with service.lock:
            valid=set(service.engine.state.satellites)|{'GND'}
            if body.source not in valid or body.target not in valid or body.source==body.target:raise HTTPException(422,'Invalid link endpoints')
            service.engine.block_link(body.source,body.target,body.blocked,body.duration_s);return service.snapshot()
    @app.get('/network/path/{source}/{target}')
    def path(source:str,target:str):
        with service.lock:
            from .network import earliest_route
            if target!='GND':raise HTTPException(400,'Delivery routes terminate at GND')
            route=earliest_route(service.engine.state,source,10,service.engine.state.time_s,service.engine.state.time_s+180)
            return {'path':route['nodes'] if route else []}
    @app.post('/api/conflicts/demo')
    def conflict_demo():
        from .coordination import conflict_demo
        with service.lock:
            task=next((t for t in service.engine.state.active_tasks() if t.owner),None)
            if task is None:raise HTTPException(409,'An assigned task is needed to demonstrate a competing claim')
            conflict_demo(service.engine.state,task);return service.snapshot()
    @app.post('/api/reconstruct')
    def reconstruct():
        with service.lock:service.engine.reconstruct('Operator requested antenna-aware reconstruction');return service.snapshot()
    @app.get('/api/export')
    def export():return JSONResponse(service.snapshot(),headers={'Content-Disposition':'attachment; filename="swarm_snapshot.json"'})
    @app.get('/api/weights.csv')
    def weights():
        with service.lock:
            out=io.StringIO();writer=csv.writer(out);writer.writerow(['source','target','weight','available','latency_s','rate_mbps','doppler_hz','tx_gain','rx_gain','tx_angle_deg','rx_angle_deg','body_blocked','antenna_clear'])
            for link in service.engine.snapshot()['links']:
                for reverse,(a,b) in enumerate([(link['source'],link['target']),(link['target'],link['source'])]):
                    tx,rx=('rx','tx') if reverse else ('tx','rx')
                    writer.writerow([a,b,link['weight'],link['available'],link['latency_s'],link['rate_mbps'],link['doppler_hz'],link[tx+'_gain'],link[rx+'_gain'],link[tx+'_angle_deg'],link[rx+'_angle_deg'],link['tx_body_blocked'] or link['rx_body_blocked'],link['antenna_clear']])
            return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="connection_weights.csv"'})
    @app.websocket('/api/live')
    @app.websocket('/ws')
    async def updates(ws:WebSocket):
        await ws.accept()
        try:
            while True:await ws.send_json(await asyncio.to_thread(service.snapshot));await asyncio.sleep(.5)
        except (WebSocketDisconnect,RuntimeError,OSError):pass
    dist=Path(__file__).resolve().parents[2]/'frontend'/'dist'
    @app.get('/')
    def index():
        if not (dist/'index.html').exists():return JSONResponse({'detail':'Build frontend: cd frontend && npm ci && npm run build'},status_code=503)
        return FileResponse(dist/'index.html',headers={'Cache-Control':'no-cache'})
    if (dist/'assets').exists():app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    return app
