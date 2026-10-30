from __future__ import annotations

from typing import Any
from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .engine import SimulationEngine
from .schemas import FailureRequest, StepRequest, SwarmConfigRequest, TaskRequest
from .models import Task


def create_app(engine: SimulationEngine | None = None) -> FastAPI:
    app = FastAPI(title="Edge Swarm Simulator")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    sim = engine or SimulationEngine()
    app.state.engine = sim

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/state")
    @app.get("/api/state")
    def state():
        return sim.state.snapshot(sim.graph)

    @app.post("/tasks")
    @app.post("/api/tasks")
    def tasks(requests: Any = Body(...)):
        is_single = isinstance(requests, dict)
        values = [requests] if is_single else requests
        models = [TaskRequest.model_validate(value) for value in values]
        normalized = []
        for request in models:
            data = request.model_dump()
            normalized.append(Task(
                id=data.get("id") or data.get("name") or f"task-{len(sim.state.tasks)+len(normalized)+1}",
                cpu_demand=data.get("cpu_demand") or data.get("cpu_required") or 1,
                storage_demand_gb=data.get("storage_demand_gb") or data.get("storage_required") or 0,
                energy_demand_wh=data.get("power_required") if data.get("power_required") is not None else data.get("energy_demand_wh", 1),
                duration_s=data.get("duration_s") if data.get("duration_s") != 60 else (data.get("duration_ticks") or 1) * 60,
                priority=data.get("priority", 1),
                name=data.get("name"),
                kind=data.get("kind", "compute"),
            ))
        result = [a.__dict__ for a in sim.submit_tasks(normalized)]
        return sim.state.snapshot(sim.graph) if is_single else result

    @app.post("/failures")
    @app.post("/api/failures")
    def failure(request: FailureRequest):
        if request.swarm_id:
            return sim.fail_swarm(request.swarm_id, request.failure_mode, request.duration_ticks, request.reason)
        if not request.satellite_id:
            raise ValueError("satellite_id or swarm_id is required")
        sim.fail(request.satellite_id, f"{request.failure_mode}: {request.reason}")
        return sim.state.snapshot(sim.graph)

    @app.post("/api/recover/{swarm_id}")
    def recover(swarm_id: str):
        return sim.recover_swarm(swarm_id)

    @app.post("/api/config/swarms")
    def configure_swarms(request: SwarmConfigRequest):
        nonlocal sim
        sim = SimulationEngine({"simulation": {
            "swarm_count": request.swarm_count,
            "satellites_per_swarm": request.satellites_per_swarm,
            "timestep_seconds": 60,
            "orbit_period_seconds": 5400,
        }})
        app.state.engine = sim
        return sim.state.snapshot(sim.graph)

    @app.post("/step")
    @app.post("/api/step")
    def step(request: StepRequest = StepRequest()):
        return sim.step(request.seconds)

    @app.post("/api/tick")
    def tick(request: dict[str, Any] | None = None):
        count = int((request or {}).get("ticks", 1))
        snapshot = sim.state.snapshot(sim.graph)
        for _ in range(max(1, count)):
            snapshot = sim.step()
        return snapshot

    @app.post("/api/reset")
    def reset():
        nonlocal sim
        sim = SimulationEngine()
        app.state.engine = sim
        return sim.state.snapshot(sim.graph)

    @app.get("/network/path/{source}/{target}")
    def network_path(source: str, target: str):
        from .network import shortest_path
        return {"path": shortest_path(sim.graph, source, target)}

    @app.websocket("/ws")
    @app.websocket("/api/live")
    async def websocket(socket: WebSocket):
        await socket.accept()
        try:
            while True:
                await socket.send_json(sim.state.snapshot(sim.graph))
                message = await socket.receive_json()
                if message.get("action") == "step":
                    sim.step(message.get("seconds"))
        except WebSocketDisconnect:
            return
    return app


app = create_app()
