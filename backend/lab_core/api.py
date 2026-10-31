"""HTTP controls and WebSocket snapshots. One process owns one simulator."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from threading import RLock

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .engine import Engine
from .models import Config
from .network import GROUND, pair_key
from .schemas import (ControlRequest, FaultRequest, LinkRequest, RecoveryRequest,
                      SimulationConfig, StressRequest, TaskRequest)


class SimulationService:
    def __init__(self, config=None):
        self.lock = RLock()
        self.engine = Engine(config)
        self.run_epoch = 0

    def snapshot(self):
        with self.lock:
            result = self.engine.snapshot()
            result["run_epoch"] = self.run_epoch
            return result

    def tick_if_running(self):
        with self.lock:
            if not self.engine.state.paused:
                self.engine.step()


def create_app(config: Config | None = None):
    service = SimulationService(config)

    @asynccontextmanager
    async def lifespan(app):
        async def loop():
            while True:
                await asyncio.sleep(service.engine.state.config.wall_interval_s)
                await asyncio.to_thread(service.tick_if_running)
        runner = asyncio.create_task(loop())
        yield
        runner.cancel()
        try:
            await runner
        except asyncio.CancelledError:
            pass

    app = FastAPI(title="Swarm Lab", version="1.0.0", lifespan=lifespan)
    app.state.service = service

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Keep non-finite rejected inputs out of the strict JSON error response.
        detail = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                  for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": detail})
    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    def ensure_node(node):
        if node not in service.engine.state.satellites:
            raise HTTPException(404, "Unknown satellite")

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/api/state")
    def state():
        return service.snapshot()

    @app.post("/api/tasks", status_code=201)
    def task(body: TaskRequest):
        with service.lock:
            try:
                return asdict(service.engine.add_task(**body.model_dump()))
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.post("/api/campaigns", status_code=201)
    def campaign():
        with service.lock:
            try:
                return [asdict(t) for t in service.engine.add_campaign()]
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.post("/api/faults")
    def fault(body: FaultRequest):
        with service.lock:
            ensure_node(body.node_id)
            service.engine.inject(body.node_id, body.kind, body.duration_s)
            return service.snapshot()

    @app.post("/api/recover")
    def recover(body: RecoveryRequest):
        with service.lock:
            ensure_node(body.node_id)
            service.engine.recover(body.node_id, body.restore_resources)
            return service.snapshot()

    @app.post("/api/stress")
    def stress(body: StressRequest):
        with service.lock:
            ensure_node(body.node_id)
            service.engine.set_stress(body.node_id, body.cpu_pct, body.heat_w,
                                      body.drain_w, body.cooling_scale)
            return service.snapshot()

    @app.post("/api/control")
    def control(body: ControlRequest):
        with service.lock:
            s = service.engine.state
            if body.action == "run":
                s.paused = False
            elif body.action == "pause":
                s.paused = True
            else:
                s.paused = True
                service.engine.step(body.ticks)
            s.version += 1
            return service.snapshot()

    @app.post("/api/reset")
    def reset(body: SimulationConfig):
        with service.lock:
            service.engine.reset(Config(**body.model_dump()))
            service.run_epoch += 1
            return service.snapshot()

    @app.post("/api/links")
    def link(body: LinkRequest):
        with service.lock:
            valid = set(service.engine.state.satellites) | {GROUND}
            if body.source not in valid or body.target not in valid:
                raise HTTPException(404, "Unknown link endpoint")
            key = pair_key(body.source, body.target)
            blocked = service.engine.state.blocked_links
            blocked.add(key) if body.blocked else blocked.discard(key)
            service.engine._reconcile()
            service.engine.state.log("injection", f"Link {key} {'blocked' if body.blocked else 'restored'}")
            service.engine.state.version += 1
            return service.snapshot()

    @app.get("/api/export")
    def export():
        return JSONResponse(service.snapshot(), headers={"Content-Disposition": 'attachment; filename="swarm_snapshot.json"'})

    @app.websocket("/ws")
    async def updates(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                snapshot = await asyncio.to_thread(service.snapshot)
                await ws.send_json(snapshot)
                await asyncio.sleep(.5)
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass

    return app
