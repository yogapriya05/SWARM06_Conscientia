# SWARM — 3D disaster observation and self-healing delivery

This is the integrated `test_hackathon1` application, using the stronger ADMM,
resource validation and bounded PSO implementation from `Swarm_Lab_ADMM`.
It simulates **one or two swarms, with 1–20 CubeSats per swarm**, orbiting a
3D Earth. Requests appear, are observed and processed, and count as successful
only after a complete, valid result reaches the ground before its deadline.

## Start here

Requires **Python 3.10 or newer**, a browser with WebGL, and an internet connection
for the initial Python dependency installation. A built frontend is included;
**Node.js is not needed to run the delivered application**.

### Windows

Open a terminal inside the extracted `hackathon` directory:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python run.py
```

Open **http://127.0.0.1:8000**. After dependencies are installed, `start.bat`
also launches the application from the activated environment.

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

Use `./start.sh` after setup. The server starts paused and uses one process.
Do not use multiple Uvicorn workers: each worker would own a separate simulation.

### Configure from the command line

```bash
python run.py --swarms 2 --satellites 20 --seed 7 --space-effects
python run.py --swarms 1 --satellites 6 --port 8080
```

`--satellites` is the number **per swarm**, so two swarms of 20 means 40 nodes.
The interface can apply the same configuration. Applying a constellation restarts
the experiment and clears its task and event history. Reset restarts the current
configuration and seed. Changing the speed or environment switches does not reset.

## Five-minute demonstration

1. Start the server and open the dashboard. Both orbital swarms use the same
   interactive globe. Drag to orbit the camera; scroll to zoom; click a CubeSat
   to inspect its resources. No external map, texture or font downloads are needed.
2. Click **+ Urgent fire**. Its task row shows its owner and remaining deadline.
   Select the row to see target coordinates, access windows, raw/output size,
   processing progress, data holder, route and actual stage timestamps.
3. Before capture begins, choose that owner in **Failure target**, choose
   **Temperature spike** or **CPU failure**, and click **Inject failure**.
   The task moves to another eligible owner in the same engine update when one
   exists. The Mission clock does not have to advance first. Ineligible work is
   deferred with a reason rather than assigned to an unsafe node.
4. Add another request and advance until it says **Captured**. Fail its CPU or
   radio. Its original image stays on its data holder. CPU work pauses and resumes
   on local recovery; a radio fault still allows processing. The simulator does
   not claim to move inaccessible raw data or silently acquire another image.
5. Enable **Random space effects**, keep **Revived randomly in between** enabled,
   choose **100×**, then Run. Inspect packet rejects/retries, actual deliveries,
   priority updates, repeated observations, urgent bursts and recovered node names.
   Pause to inspect details. Try **Solver & weights**, then export the weights CSV.

A **complete outage** after capture retains the stored image/product but makes
it inaccessible until that node recovers. A **storage failure** makes its sole
copy inaccessible and marks the task Failed. Restoration uses three fresh safe
samples for an isolated node. Step advances exactly one simulated second.

## Dashboard controls

| Control | Meaning |
|---|---|
| Mission / Failures / Solver & weights | Task operations; recovery audit; ADMM diagnostics and weighted edges |
| Swarms | Exactly 1 or 2 |
| Satellites per swarm | 1–20, independently from the number of swarms |
| Failure target | A satellite or an entire swarm |
| Failure mode | Offline, thermal, CPU, radio, battery, stale telemetry, storage, camera attitude, antenna pointing, single link or network partition |
| Satellite batteries | One independently editable slider per satellite, including all 40 nodes |
| Random space effects | Seeded transient link/pointing/telemetry disturbances |
| Exaggerate link effects | Adds larger demo delays and raises packet disturbance rates |
| Revived randomly in between | Faulted nodes receive a seeded return opportunity 35–105 simulated seconds after injection |
| Dynamic requests | Random normal arrivals, urgent bursts, event escalation and repeat monitoring |
| Time scale | 1–100× slider, with 1×, 2×, 10× and 100× presets |
| + Request / + Urgent fire | Immediate ordinary / P5 observation request |
| + GNSS pair | Retained two-product GNSS-R / image campaign workflow |
| Raise event to P5 | Changes unfinished tasks for that event while preserving their task IDs |
| Restore target | Clears injected faults and restores demo resources, then validates safe telemetry |
| Export JSON / Weights CSV | Download the actual state or both directed entries of every symmetric edge |

Failure duration and severity dropdowns from the old mock-up have been removed
from the main UI. Failures and batteries are direct operator interventions;
other resource quantities are calculated. Duration-limited faults and advanced
CPU/heat/drain stress controls remain available through the API and the retained
Swarm Lab dashboard.

The globe uses real 3D meshes, two inclined orbital rings, solar panels, target
markers, an Earth day/night boundary, eclipse-dependent satellite state, ground
station marker and dotted graph edges. A bright green path identifies an active
product route. Broken contacts remain visible in red. Hover a line for its
symmetric weight, throughput and delay. Satellite labels and target labels live
inside the 3D scene; the camera can expose the far side of the Earth.

## What a mission task means

The default example is: **observe a fire, process its image on the observer,
and deliver a 10 MB result within 90 seconds**. Values are configurable simulator
inputs, not spacecraft qualification values.

```python
task = {
    "task_id": "OBS_0042",                 # optional; generated uniquely if omitted
    "event_id": "FIRE_07",
    "target": {"lat": 18.52, "lon": 73.86},
    "observation_window": [105.0, 145.0],  # absolute simulation seconds
    "delivery_deadline": 190.0,           # absolute simulation seconds
    "priority": 4,                        # 1 (low) to 5 (urgent)
    "capture_duration_s": 5.0,
    "processing_cycles": 8_000_000,
    "raw_data_mb": 40.0,
    "output_data_mb": 10.0,
    "minimum_quality": 0.8,
    "required_captures": 1
}
```

Creation time, status, owner and data holder are controlled by the engine. If
windows/deadlines are omitted, they are generated relative to the current clock:
access window `[now+1, now+62]`, delivery deadline `now+90`.

| Job | Resources and checks | Persistent result |
|---|---|---|
| Observe | Explicit target access window, attitude, capture duration, raw buffer, energy, payload health | Raw image on the observer |
| Process | Observer CPU rate, assigned CPU fraction, energy, thermal headroom, output buffer | Quality-checked, checksummed output |
| Relay | Available contact, shared endpoint radios, pair bandwidth, receiver storage, packet acknowledgements | Complete product on next holder |
| Deliver | Ground pass, valid full-product manifest, quality threshold, hard deadline | Ground acknowledgement |

The lifecycle is **Pending → Assigned → Captured → Processed → Delivered**.
Processing takes place while the status is Captured; relay/downlink progress is
shown while it is Processed. Deferred, Expired and Failed describe real inability
to proceed. A status transition alone does not manufacture a delivery.

## Dynamic workload

All randomness belongs to a seeded generator; time speed does not change its
sequence when the same controls are applied at the same simulated times.

- Normal arrivals occur every 15–30 simulated seconds after the first arrival.
- The first urgent burst is at 70 seconds; subsequent bursts occur after 100–160
  seconds and contain up to three P5 requests, subject to the queue limit.
- Event escalation updates the priority of unfinished work every 40–75 seconds.
- Each region has a 125-second repeat-monitoring interval. A new observation gets
  a **new task ID**, retaining its event ID and target.
- Faults and contact interruptions repair existing work; they do not generate a
  replacement mission request unless a new monitoring interval expires.

At most 80 active tasks are admitted to the queue. Completed history retains the
latest 300 terminal tasks and cumulative counters. Events, telemetry history,
recovery history and transfer logs are bounded for longer demonstrations.

## Allocation and self-healing

### Full-chain eligibility

For each candidate, the engine checks health and telemetry freshness, allowed
host restrictions, explicit visibility, camera pointing, achievable quality,
CPU, simultaneous raw/output storage, battery reserve, thermal forecast, and a
predicted route to ground before the delivery deadline. The default battery
reserve is 12 Wh. High battery alone cannot make a node eligible.

Processing duration is satellite-specific:

`duration_s = remaining_cycles / (cycles_per_second × cpu_demand / 100)`

CPU capacity is shared with avionics and already admitted jobs. Raw plus output
storage is reserved before acquisition; the raw image becomes used storage after
capture; raw storage is released when the output is produced. The next relay's
storage is reserved until the hop is committed or cancelled. These budgets are
independently reconstructed and validated.

### ADMM and bounded PSO

The original Swarm Lab scaled ADMM implementation is reused directly. It solves
a convex relaxation of a resource-limited admission problem with satellite-local
CPU, storage and energy constraints and per-task consensus `sum_i x_ij <= 1`.
It performs at most **20 outer iterations**, reports primal/dual residuals and
convergence, and ranks candidate hosts. The final integer decisions are checked
again against all hard constraints, including thermal and contact feasibility.
An unconverged relaxation is reported honestly; it is never a substitute for
integer admission validation.

For fault repair, the original random-key PSO search is reused with **6 particles
and 12 iterations** (78 evaluations), over at most eight orphaned tasks. Each
particle decodes against a separate resource ledger. The feasible ADMM-ranked
greedy plan is the incumbent, so a worse particle cannot replace it. Route repair
also searches a bounded set of valid contact-route alternatives.

Earliest-arrival routing in the FIFO contact graph is a polynomial graph search.
The combined discrete allocation/resource/scheduling problem motivates a bounded
heuristic search; this project does not label ordinary shortest-path routing an
NP-hard problem or claim a global optimum from 12 PSO iterations.

### Prefix preservation, ownership and isolation

Healthy work already executing stays with its owner. Uncaptured/partial captures
on unavailable payloads are released, their reservations are reconstructed, and
eligible owners are committed immediately after reconstruction. Captured data
and processing checkpoints stay with their holder. Processing offload is not
implemented in this first version. A valid output on a healthy relay can continue
even if the original observer later fails.

Each assignment has a monotonically increasing lease version and deadline-bound
lease. A single backend lock serializes the authoritative commit, configuration,
steps and operator actions. This is **a single-process emulation**, not an
implementation of distributed quorum consensus, partition-safe lease election,
Raft or flight networking.

Hard protection checks isolate offline, overheated, low-battery and inaccessible
storage nodes. A stale sensor sample isolates a node only after its timestamp
age exceeds eight seconds. A thermal residual CUSUM, reused from Swarm Lab,
detects unmodelled heating. CPU, radio, attitude and antenna failures remove the
affected capabilities instead of pretending all hardware always fails together.
After an isolated node recovers, three fresh safe samples are required before
it is offered for work again. Revival names and timestamps are recorded.

## Space effects and reliable delivery

### Modelled disturbances

When the space-effects switch is enabled, a transient effect is generated every
8–18 simulated seconds, favouring a busy contact when possible:

- extra link latency;
- Doppler-related rate degradation and increased loss;
- partially received packets;
- data bit flips;
- temporary link dropout;
- camera attitude error, antenna misorientation or stale telemetry.

Base propagation delay is `distance_km / 299792.458 + 0.003` seconds. First-order
Doppler uses radial relative velocity and an illustrative 2.2 GHz carrier:
`delta_f = -radial_velocity / c × carrier_frequency`. Exaggerated mode can add
2 seconds of link delay; the smaller demo setting adds 0.08 seconds. It also
raises random packet corruption probabilities. This is a service-quality model,
not a radio waveform, frequency acquisition or modem simulation.

### Packet reconstruction rules

1. Divide a product into sequenced **logical 0.5 MB packets**.
2. Generate deterministic representative payload bytes and a CRC32 per packet.
3. Charge the actual logical MB against the pair and shared radio budgets.
4. Reject truncated payloads, CRC mismatches and missing packets.
5. Retry only packets which have not been acknowledged; suppress duplicates.
6. Account for the round-trip acknowledgement delay and contact availability.
7. Reconstruct an ordered packet manifest and compare its SHA-256 checksum.
8. Commit a complete hop atomically, then release the sender's previous copy.
9. Mark Delivered only after the ground's complete valid result is acknowledged
   no later than the delivery deadline.

The representative packet bytes keep memory/compute low. The simulator does
**not** allocate 40 MB of image pixels per observation, compress real images,
or implement a production CCSDS/CFDP stack. Checksums detect corruption; they
do not correct bits themselves. A missing/corrupt packet is retransmitted.
A route change may discard an incomplete receiver buffer while retaining the
complete sender copy. Shared radios are 24 Mbps per satellite and 48 Mbps at
GND, with a shared per-pair budget. Opposite directions use the same pair budget.

Faults do not guarantee mission success under impossible resources or deadlines.
The engine can defer or expire work while retaining correct accounting. The
interface reports these outcomes rather than claiming 100% recovery by design.

## Orbital and contact modelling boundaries

- Satellites follow circular two-body trajectories about Earth, radius 6371 km.
  Swarm 01 is at 550 km altitude and 51.6° inclination; Swarm 02 is at 650 km
  and 74°, with a different orbital plane. Periods follow `2*pi*sqrt(a^3/mu)`.
- The Earth rotates with a sidereal-day period. The fixed short-experiment Sun
  direction drives a cylindrical Earth-shadow eclipse test and solar input.
- Thermal evolution uses the inherited lumped conduction/linearized radiative
  model; there is no convective cooling in the space model.
- Camera visibility is a published, satellite-specific **synthetic window**:
  72-second access intervals every 110 seconds, clipped to each task's allowed
  observation window. It is not derived from the target's physical FOV geometry.
- Ground passes are explicitly simulated 62-second windows every 90 seconds,
  staggered between nodes. The Pune ground marker is geographic; these synthetic
  passes are not a physical ground-station visibility solution.
- As requested, the dotted graph contains **every satellite pair** and symmetric,
  seeded weights. It is a **logical communication service**. Straight-line Earth
  occultation is calculated and displayed separately but does not disconnect
  the logical full mesh. Every graph edge should not be interpreted as a direct
  intersatellite radio path through Earth. A future physical-contact mode must
  enforce LOS/range/antenna geometry and accept frequent partitions at small N.
- Weights change on seeded 30-second epochs and include endpoint energy penalties;
  the exact same weight is exported in both directions. Actual endpoint faults
  and contact interruptions still remove the affected service from route searches.
- There is no J2/drag propagation, actual optical instrument, RF coding stack,
  ground scheduler or flight-certified fault protection in this demonstration.

The 100× control advances fixed substeps of at most one second and preserves
intermediate events. It changes the requested simulated-time budget per server
update; effective wall-clock acceleration depends on hardware, node/task count
and browser rendering. Dense 40-node graphs cost more to render and plan.

## API examples

The dashboard, REST API and WebSocket all share one authoritative engine.

```bash
curl http://127.0.0.1:8000/api/state

curl -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"event_id":"FIRE_07","target":{"lat":18.52,"lon":73.86},"priority":5}'

curl -X POST http://127.0.0.1:8000/api/faults \
  -H "Content-Type: application/json" \
  -d '{"node_id":"SAT-02","kind":"cpu","duration_s":15}'

curl -X POST http://127.0.0.1:8000/api/battery \
  -H "Content-Type: application/json" \
  -d '{"node_id":"SAT-03","percent":25}'

curl -X POST http://127.0.0.1:8000/api/settings \
  -H "Content-Type: application/json" \
  -d '{"space_effects":true,"random_revival":true,"speed":100}'

curl -X POST http://127.0.0.1:8000/api/control \
  -H "Content-Type: application/json" -d '{"action":"run"}'
```

| Endpoint | Purpose |
|---|---|
| GET `/api/health`, `/api/state` | Health and complete current state |
| WS `/api/live`, `/ws` | Snapshot stream, including remote controls and background ticks |
| POST `/api/control` | `action`: run, pause or step; `ticks` for step |
| POST `/api/tick`, `/api/step` | Deterministically advance `ticks` or `seconds`, max 300 per call |
| POST `/api/config/swarms`, `/api/reset` | Restart with validated configuration overrides |
| POST `/api/settings` | Change speed/environment/workload/revival switches in place |
| POST `/api/tasks`, `/api/campaigns` | Observation request or two-product campaign |
| POST `/api/priority` | `event_id`, `priority`; preserves existing task identities |
| POST `/api/faults`, `/api/failures` | `node_id` or `satellite_id`, or `swarm_id`, `kind`, optional duration |
| POST `/api/recover` | `node_id`, optional `restore_resources` |
| POST `/api/recover/{swarm_id}` | Recover all members of one swarm |
| POST `/api/battery` | `node_id`, `percent` |
| POST `/api/stress` | Retained `node_id`, `cpu_pct`, `heat_w`, `drain_w`, `cooling_scale` controls |
| POST `/api/links` | Block/restore `source`, `target`, optional duration |
| GET `/network/path/{source}/GND` | Predicted delivery path |
| GET `/api/export`, `/api/weights.csv` | State snapshot; two-way weighted edge export |

Swagger API documentation is at **http://127.0.0.1:8000/docs**. Bodies are validated;
unknown nodes, invalid configurations and impossible queue operations return
explicit errors. Snapshot and CSV exports reflect real simulator state.

## Rebuild the frontend

For frontend development only, install Node.js 18+ (20+ recommended):

```bash
cd frontend
npm ci
npm run dev
```

Run `python run.py` in another terminal. Vite proxies `/api` and the WebSocket
to the backend at port 8000. To build the packaged interface:

```bash
cd frontend
npm run build
```

The Python server serves `frontend/dist`. No CDN is needed at runtime. The
frontend uses React, TypeScript and Three.js; the Earth texture is generated
locally. All 3D resources are disposed on a scene/configuration change.

## Tests and reproducible runs

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q tests backend/lab_tests
python run.py --headless --seconds 600 --space-effects --export snapshot.json
python run.py --headless --swarms 2 --satellites 20 --seconds 120 --space-effects
```

`Engine.validate()` checks resource limits, task/data-holder invariants, valid
on-time deliveries, and actual shared transfer capacity. Behavioral tests cover
immediate reassignment, captured-data retention, CPU/radio/offline recovery,
route repair, stale detection, explicit visibility, independent battery/storage
checks, priorities and IDs, CRC failures/retries, seed replay, 40-node topology,
orbital radius, eclipse, speed equivalence and API validation.

The browser smoke test launches its own temporary server and verifies the real
UI. To run it using your own Playwright installation:

```bash
cd frontend
npm install --no-save playwright
npx playwright install chromium
cd ..
node tests/browser_smoke.cjs
```

If Node cannot resolve Playwright, set `PLAYWRIGHT_MODULE` to the absolute installed
module path. `BROWSER_EXECUTABLE` can select an existing Chromium executable.
Browser screenshots are optional local QA output via `QA_SCREENSHOT_DIR` and are
not part of the delivered evidence. See `evidence/VALIDATION.md` for this build's
recorded test outcomes and the accompanying machine-readable logs.

## Retained projects and source layout

```text
hackathon/
  run.py                    Integrated server / deterministic headless runner
  run_legacy_lab.py         Original Swarm Lab dashboard and advanced controls
  run_legacy_scenarios.py   Original deterministic laboratory scenario runner
  start.bat, start.sh       Convenience launchers
  requirements*.txt        Runtime and test dependencies
  backend/app/
    models.py, state.py     Mission records, resources, seeded experiment state
    orbits.py               Circular propagation, Earth rotation, eclipse, windows
    resources.py            Admission checks and independent resource ledgers
    allocator.py            Adapter around inherited ADMM solver
    pso.py                  Adapter around inherited bounded PSO search
    failures.py             Capability isolation, CUSUM, stale detection, revival
    network.py              Symmetric logical contacts and temporal delivery paths
    engine.py               Dynamic missions, reliable transport, repair workflow
    api.py, schemas.py      Validated controls, WebSocket, CSV/JSON, static serving
    metrics.py, main.py     Actual mission metrics and ASGI entry point
  backend/lab_core/         Complete retained Swarm Lab backend and original UI
  backend/lab_tests/        Original laboratory test suite, imports redirected only
  backend/original_app/     Original test_hackathon Python implementation
  frontend/src/            React/TypeScript/Three.js interface
  frontend/dist/           Ready-to-run production build
  frontend/reference/      Original React panel components for reference
  tests/                   New integrated behavioral/API/browser checks
  docs/                    Formulation, literature, original project notes and PDFs
  evidence/                Test results and deterministic run evidence
  references/              Unmodified input archives for exact provenance
```

To run the retained Swarm Lab interface, including its original CPU, heat,
battery-drain, cooling, solver and link controls:

```bash
python run_legacy_lab.py --nodes 20 --port 8001
```

Open **http://127.0.0.1:8001**. This mode deliberately retains the original lab's
mission and networking model and owns a separate experiment; it is not a second
visualization mode for the integrated mission. The original inputs are also
included unchanged in `references`. The main integrated interface keeps one 3D
view, while the legacy code remains available for regression and research.
