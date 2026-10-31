# Swarm Lab

A local Python simulator for **dynamic GNSS-reflectometry and remote-sensing task allocation**, using actual ADMM updates, resource-aware integer reconstruction, bounded PSO repair and contact-graph data routing. A browser dashboard provides a scrolling sidebar for tasks, faults, resource stress and swarm configuration.

## Start

Use Python 3.10 or newer. Extract the ZIP, open a terminal **inside `swarm_lab`**, then run:

```bash
python -m pip install -r requirements.txt
python test.py
```

Open **http://127.0.0.1:8000**. The simulation starts paused. Click **Run**.

`test.py` is kept as the simple demonstration entry point. It supports the same arguments as `python -m swarm_sim.main`. There is no Node.js requirement for running the application, no external JavaScript CDN and no internet requirement after installing Python dependencies.

For 20 satellites:

```bash
python test.py --nodes 20
```

You can also change **Satellites** in the sidebar and click **Reset with settings**. Reset creates a new paused run and clears the current one. The supported range is 3–40 nodes. Change the port with `--port 8001` if needed. Stop the server with Ctrl+C.

Optional Windows setup:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python test.py --nodes 20
```

Optional macOS/Linux setup:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python test.py
```

## Try a fault

1. Press **Run** and watch the first survey pairs move through processing and delivery.
2. Click a busy satellite in the mesh. Its ID appears in the **Selected satellite** control.
3. Choose **Node offline** and click **Inject fault**. Unfinished work is requeued and repaired on another feasible node. The failed physical node stays visible in red and is excluded from active links.
4. Click **Recover node**. Faults/stress are cleared, demo resources are restored and the node rejoins after three fresh safe samples.
5. Try **Radio failure** or block a link. Products already acquired stay on the last confirmed holder while their route is repaired. If the holder itself is offline, its data waits for recovery rather than appearing on an arbitrary replacement node.
6. Try **Freeze sensor data**. Isolation occurs after the timestamp becomes stale, rather than immediately deleting the satellite.
7. Click **CPU + cooling fault demo**. External CPU load is held at 100% and cooling is reduced. CPU activity heats the node progressively until thermal protection isolates it. Advance several ticks or leave the simulation running.

You can add CPU load, battery drain and unmodelled heat independently. The unmodelled heater produces a prediction residual and exercises CUSUM. A large drain takes time to deplete a healthy 75 Wh battery; use **Battery reserve** for an immediate battery fault. A zero fault duration means it stays until recovery. A positive duration clears the flag later, but physical state must still recover.

## What the swarm coordinates

A **coastal survey pair** contains a GNSS-R correlation-map task and a remote-sensing image task for the same region. Jobs have different CPU, memory and data profiles. They can run on different spacecraft and relay data through peers. A campaign succeeds only when both products reach ground before their deadlines.

The pipeline is:

**Queued → Processing/acquisition → Buffered product → Contact hops → Delivered**

The telemetry is synthetic and noisy. GNSS-R does not mean these nodes broadcast navigation signals. Actual waveform processing, real imagery and orbital propagation are outside this reduced simulator.

## Dashboard

| View/control | Purpose |
|---|---|
| Overview | Live contact mesh, selected node, work in progress and recent activity |
| Tasks | Processing owner, confirmed data holder, attempts, progress and deadlines |
| Telemetry | Noisy measurements, physical temperature, sample age and reservations |
| Solver | ADMM residuals/fractions, convergence status, PSO effort and connection weights |
| Events | Task, fault, route, deadline and recovery events |
| Guide | Onscreen demonstration instructions and model boundaries |
| Export run | Download a JSON snapshot, recent history, events and configuration |
| Solver → Export CSV | Download current nodal connection weights |

The left sidebar scrolls independently. On small screens, use the top-left menu button. **Step +1** pauses the live loop and advances exactly one simulation interval. Default Δt=2 s, with one live interval every 0.5 wall-clock seconds before solver overhead.

## Algorithms

- **ADMM:** a two-block convex admission relaxation with explicit local resource projections, a shared exclusive-task projection and scaled dual updates. Default outer cap: 32. The UI reports a budget stop when residual tolerance is not reached.
- **Integer admission:** deterministic reconstruction followed by independent current feasibility checks. Existing running work is retained.
- **PSO repair:** up to 8 orphan tasks, 8 particles and 12 iterations. A feasible greedy incumbent is preserved. PSO also selects among a small set of physically available contact-route alternatives.
- **Routing:** time-dependent earliest-arrival search over a synthetic contact plan. Execution shares physical pair and per-radio capacity and reserves receiver memory.
- **FDIR:** component flags, stale telemetry, hard battery/thermal limits and a one-sided thermal-residual CUSUM, with controlled recovery and hysteresis.

Read **[docs/FORMULATION.md](docs/FORMULATION.md)** for equations, constraints, ADMM derivation, task semantics and precise implementation limits. Read **[docs/LITERATURE.md](docs/LITERATURE.md)** for the primary-source review and references.

One process emulates the optimization agents. Local ownership is atomic under one authoritative state lock. This is not a deployed distributed consensus system: quorum commits, Byzantine tolerance and partition-safe ownership leases are not implemented. All geometry, resource coefficients and accelerated environmental cycles are illustrative. ADMM's convex convergence theory does not establish global optimality or flight safety for the changing integer application.

## Verify

Run the complete Python checks:

```bash
python test.py --check
python run_scenarios.py
python -m compileall -q swarm_sim tests test.py run_scenarios.py
```

Run a headless 20-node simulation and export its snapshot:

```bash
python test.py --headless --nodes 20 --steps 300 --export run20.json
```

The invariant validator runs on every headless/scenario tick. It checks task ownership/CPU ledgers, data and reservation ledgers, buffer capacity, battery bounds, progress, actual transfer capacity and delivery deadlines. Tests include independent analytical and SciPy-reference checks of ADMM, fault recovery, routing, payload restrictions, API input validation and WebSocket updates.

**[evidence/VALIDATION.md](evidence/VALIDATION.md)** records this build's actual results. Machine-readable test and scenario evidence is included. Re-running `run_scenarios.py` updates its scenario evidence; runtimes depend on the computer.

SciPy is included in `requirements.txt` for the independent optimizer reference test; the running simulator itself uses NumPy rather than SciPy. The optional browser test is described in the validation report. A Python-only launch needs no browser automation package.

## Files

```text
swarm_lab/
  test.py                     # Simple UI/headless/test launcher
  run_scenarios.py             # Reproducible failure scenario evidence
  requirements.txt
  pyproject.toml
  swarm_sim/
    __init__.py
    main.py                   # Start API or headless simulation
    api.py                    # Controls, snapshots and WebSocket updates
    schemas.py                # Request validation
    models.py                 # Satellite, task, link, route and event types
    state.py                  # Authoritative ownership, events and state
    engine.py                 # Tick, processing, transfers and recovery workflow
    resources.py              # CPU, energy, heat, memory and noisy telemetry
    allocator.py              # ADMM relaxation and host ranking
    failures.py               # Manual faults, timestamps, CUSUM and isolation
    network.py                # Contact plan, feasibility and live capacities
    pso.py                    # Bounded placement and route repair
    metrics.py                # Delivery, recovery and resource metrics
    static/                   # Dashboard HTML, CSS and JavaScript
  tests/                      # Numerical, workflow, network and API tests
  docs/                       # Formulation and literature review
  evidence/                   # Actual validation outputs
```

## API examples

Interactive API documentation is at **http://127.0.0.1:8000/docs**. Use one server process/worker. The service binds to localhost by default and has no authentication; it is intended for a local demo.

```bash
curl -X POST http://127.0.0.1:8000/api/control -H "Content-Type: application/json" -d '{"action":"step","ticks":5}'
curl -X POST http://127.0.0.1:8000/api/faults -H "Content-Type: application/json" -d '{"node_id":"S2","kind":"offline","duration_s":20}'
curl -X POST http://127.0.0.1:8000/api/reset -H "Content-Type: application/json" -d '{"nodes":20,"auto_tasks":true}'
```

Available endpoints include `GET /api/state`, `GET /api/export`, `GET /api/health`, `POST /api/tasks`, `/api/campaigns`, `/api/faults`, `/api/recover`, `/api/stress`, `/api/links`, `/api/control`, `/api/reset`, and `WS /ws`. A reset request supplies a new configuration; omitted settings take their defaults. Task deadlines are relative to current simulation time. Unknown nodes return 404, invalid inputs 422, and a full/invalid task queue 409.

Closing the browser does not persist a run; use **Export run** to save a snapshot. The server does not automatically load exported state. The random seed makes physical noise and workload generation reproducible; wall-clock timing is not deterministic.
