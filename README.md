# Edge Swarm Simulator

An interactive six-satellite mesh simulator for resource-aware task allocation and self-healing local repair. The implementation combines:

- resource feasibility checks for battery, thermal headroom, CPU and storage;
- a solar/eclipsing battery model inspired by the IAC energy-management paper;
- contact-aware multi-hop routing across a configurable satellite mesh;
- event-triggered failure isolation and bounded PSO-style repair of only the free schedule suffix.

## Run the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`. Interactive API documentation is at `/docs`.

## Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL (normally `http://localhost:5173`). Set `VITE_API_URL` if the backend is not on `http://localhost:8000`.

## Demo workflow

1. Start both services.
2. Create a sensing or processing task from **Tasks**.
3. Use **Fail node** on the selected satellite.
4. Observe owner reassignment, route changes and recovery metrics in the event stream.
5. Advance the simulation with **Tick** or enable the live loop.
6. Set **Number of swarms** and **Satellites per swarm**, apply the constellation,
   then choose a target swarm and failure mode. The selected swarm is isolated
   for the configured duration and automatically reconnects; **Re-establish
   connection** can recover it immediately.

See [`docs/workflow.md`](docs/workflow.md) for the model assumptions, API examples and demonstration script.
