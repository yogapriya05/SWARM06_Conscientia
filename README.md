# SWARM — J2 orbit, antenna-aware mesh and coordinated disaster tasks

This corrected build extends the integrated hackathon application. It has one
shared nominal orbit, 50 km initial adjacent satellite spacing, a seasonal solar
model, geometry-dependent communications, buffered coordination and a prominent
allocation command centre. The original Swarm Lab and original input archives
remain included.

## Run the packaged application

Python 3.10+ and a WebGL-capable browser are required. The built React/Three.js
frontend is included; Node.js is needed only when modifying frontend source.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

Open **http://127.0.0.1:8000**. `start.bat` and `start.sh` are convenience
launchers after dependencies are installed in your active environment.

```bash
python run.py --swarms 2 --satellites 20 --seed 7 --space-effects
python run.py --quiet-http
```

There can be exactly one or two swarms, with 1–20 satellites in each. Both swarms
are administrative groups within the same orbit. The simulator is single-process;
using multiple Uvicorn workers would create separate experiments.

## What changed in this revision

| Requested correction | Implementation |
|---|---|
| Earth spin, Earth revolution, satellite revolution, J2, eclipse and heating | Numerical central-Earth + J2 gravity; sidereal Earth rotation; circular annual Sun direction with obliquity; parallel sunlight, constant 1361 W/m²; cylindrical eclipse; projected solar power and absorbed solar heat |
| Rare random satellite failures remain | Separate seeded exponential event process, independent of packet-effect switch; default per-satellite rate 0.00008/s |
| Initial and reconstructed graph weights remain visible | Immutable initial graph plus recent reconstruction history; select an epoch in the 3D formation view; dark solid valid spanning forest; readable selected-edge weights; full edge table and CSV |
| Clear coordinated task allocation | Command centre above the globe: ingress buffer → lowest-cost coordinator → shared manifests → feasibility screening → atomic owner lease → execution |
| Visual conflict prevention | Owner lock badges; coordinator epochs; versioned leases; CPU/storage reservations; accepted/rejected claim audit; Test competing claim action |
| Antenna orientation and CubeSat self-blockage affect graph construction | Body-frame mounted fore/aft antennas and nadir downlink antenna; ray/box intersection, beam cone, paired gain and Earth LOS at both endpoints; invalid links excluded from routing |
| Smooth professional browser visualization | Three.js dual 3D viewports: orbital context and magnified real-position formation; requestAnimationFrame rendering; position/velocity Hermite interpolation; quaternion SLERP; reusable geometry |

“J2M” in the request is interpreted as an **Earth J2 gravity model**. This build
implements central Earth gravity plus the J2 acceleration term. It does not claim
a particular external product named J2M.

## Quick demonstration

1. Start paused. The **Task allocation command centre** shows two incoming
   requests and the elected coordinator. They are initially buffered and unowned.
2. Step forward about six seconds. Requests travel from their ingress satellite
   to the coordinator. Task manifests are shared through feasible links. Feasible
   observing nodes receive versioned ownership leases.
3. Select **Test competing claim**. The competing/stale claim is rejected and
   shown in the audit without changing the real owner or resource reservations.
4. Select an owner in Failure target and inject a **CPU failure** or **Temperature
   spike** before it finishes acquisition. Previously shared work is reallocated
   immediately in the reconstruction update when an eligible reachable node exists.
5. Inject a radio failure on an ingress satellite, then create a request through
   that source using the API. The request stays in that node's buffer. Restore
   the node and watch the same request travel and receive an owner.
6. Select **Initial graph** and subsequent **Reconstruction** entries in the
   formation viewport. The selected epoch's weights and positions are frozen;
   the separate Earth/orbit viewport continues showing the live mission.
7. Enable Random space effects and run at 10× or 100×. Rare random satellite
   failures are a separate switch and remain enabled by default. Watch packet
   retries, fault isolation, node revival, buffered requests and task deadlines.

Tasks acquired before a recoverable fault retain their data/checkpoint on the
named holder. They are not silently reobserved. Processing stays on the observer
in this version. Inaccessible storage with the sole data copy produces Failed;
an impossible delivery deadline produces Expired. There is no guaranteed success
percentage under outages or insufficient contacts.

## Reading the visualization

The **left viewport** is Earth and the real J2-propagated formation on its shared
orbit. The Earth rotates; the Sun direction evolves through the model year; night
and eclipse depend on geometry. The formation is physically compact relative to
Earth, so its individual nodes would be hard to distinguish at globe scale.

The **right viewport** therefore shows the same spacecraft positions translated
about their centroid, at **one formation unit = 50 km**. It is a 3D magnified
view, not a topology layout that moves satellites to invented positions. CubeSat
icons and their labels are enlarged for legibility. Dragging or zooming changes
the camera in both views; clicking a formation spacecraft selects it.

| Cue | Meaning |
|---|---|
| Dark solid edges | Valid minimum-cost spanning forest for the displayed graph epoch |
| Faint dotted edges | Other candidate intersatellite links |
| Red/pink edges | Unavailable links, including body/beam/LOS/radio restrictions |
| Weight labels / selected-edge readout | Initial or current symmetric numerical edge costs |
| Amber dashed lines | Coordinator-to-owner allocation relationships |
| Blue dashed lines | Control messages in transit |
| Green lines | Product relay routes |
| COORDINATOR label | Elected node for the displayed epoch |
| LOCK badge / owner cell | Existing task ownership and lease version |
| Translucent cones / boresight lines | Selected node's fore/aft antenna field of regard |
| Rejected claim card | A competing or stale ownership attempt was blocked |

Snapshot history retains the initial graph permanently and the latest 15 graph
snapshots. A cumulative graph epoch still counts all reconstructions. The graph
selection controls only the diagnostic formation display; it does not roll back
the simulation. Healthy topology and numerical link costs can evolve between
reconstructions; the live graph uses live weights, while the dark spanning forest
is the latest committed reconstruction backbone.

## Orbit and Sun model

All nodes start on the same 550 km, 51.6° nominal orbit. Their initial common
orbital plane is chosen so the formation is near the Pune ground station, which
makes the first demonstration contact accessible. Adjacent nodes, including the
boundary between the two swarms, have an exact initial **50 km Euclidean chord**.
The angular increment is `2*asin(50/(2*a))`, where `a = 6371 + 550 km`.

The propagator integrates `r_dot = v` and `v_dot = a_central + a_J2` using RK4
with substeps of at most one simulated second during normal engine operation.
Its constants are `mu = 398600.4418 km^3/s^2`, `J2 = 1.08262668e-3` and J2 reference
radius `6378.137 km`. The displayed/occulting Earth sphere uses mean radius 6371 km.

The application uses an Earth-centred equatorial frame with **Y as the north
pole**, matching Three.js. It is a permutation of conventional Z-pole ECI, not a
different physical model. The J2 polar coordinate is therefore Y. The relevant
component factors are `(5*y²/r² - 1, 5*y²/r² - 3, 5*y²/r² - 1)`.

Initial 50 km spacing is not held by a formation controller. J2 causes small
relative/osculating variations over time; no stationkeeping or collision-avoidance
controller is included. “Common orbit” describes the shared initial orbital
family, rather than a claim of perfectly rigid spacing under perturbations.

The Earth spins once per 86164.0905 seconds. Earth revolution is a circular model
year of 365.256363004 days. The Earth-to-Sun unit vector changes with annual phase
and 23.43928° obliquity. The zero epoch is a **chosen vernal-equinox reference**;
it is not a precise ephemeris for the user's calendar date.

The Sun is treated as very distant: rays are parallel, irradiance outside eclipse
is fixed at **1361 W/m²**, and solar gravitational acceleration is omitted. There
is no annual inverse-square irradiance modulation. The eclipse test requires a
satellite to be behind Earth along the Sun direction and inside the cylindrical
Earth shadow. It produces full light or full eclipse; penumbra is omitted.

Solar generation uses projected two-sided panel area, 0.14 m² area and 28%
efficiency. Absorbed direct solar heat uses a basic projected body area with
0.018 m² effective area and 0.6 absorptivity. Eclipse zeros both contributions.
The existing lumped thermal model uses internal dissipation, conduction and a
linearized radiative rejection term. Its small 20 J/K thermal capacity deliberately
makes a demonstration respond quickly. There is no convection in space. Earth
albedo/IR, detailed multi-node thermal conduction and real material coatings are
outside this basic model. Solar heating is included in both the admission thermal
forecast and the nominal residual predictor, avoiding a false CUSUM solar alarm.

## Antenna and CubeSat geometry

Each satellite has a local LVLH-style frame: forward along velocity projected
perpendicular to radius, cross-track, and radial outward. Its body has seeded
small yaw bias and a small time-varying roll. Attitude faults rotate the body and
all mounted antennas together. An antenna pointing fault additionally rotates
the antenna boresights relative to the body.

The body is a **10 × 10 × 30 cm box**. Fore/aft patch antennas are mounted just
outside the ±body-X faces. A nadir patch is available for the ground downlink.
For every endpoint-target pair, the model:

1. transforms the target ray into the body's local frame;
2. traces that ray from each antenna mount against the box using slab intersection;
3. rejects a ray that re-enters the CubeSat body;
4. checks the selected antenna half cone, default 72°;
5. applies a basic `cos(angle)^4` gain pattern inside the cone;
6. chooses a clear usable antenna, if one exists.

Both ends must have a usable antenna and a clear Earth LOS. A radio or isolated
node cannot provide a contact. Antenna faults need not isolate the entire node:
the graph decides which specific endpoint pairs remain usable. Ground contacts
also require at least 5° station elevation. The request-source and product route
searches use these gates; a displayed unavailable edge is never silently used.

This is a coarse body-shadow/beam model, not an electromagnetic diffraction,
multipath, polarization, CAD ray tracing or modem acquisition model. Distortion
is represented through reduced gain, service rate and disturbance losses.

### How graph weights are constructed

Every satellite pair has a candidate cost; usability is separate from cost. The
same physical pair cost is used in both directions. Components are exported as
`weight_components` in JSON and are shown through the edge diagnostics:

- stable seeded hardware/calibration variation;
- separation-dependent cost;
- paired antenna gain/pointing penalty;
- body obstruction penalty;
- endpoint energy penalty;
- Doppler penalty.

The base carrier is an illustrative 2.2 GHz. First-order Doppler uses relative
radial velocity. Propagation delay is range divided by 299792.458 km/s plus a
3 ms electronics allowance. Weights do not make an invalid contact valid.
Reconstruction recomputes the valid spanning forest and coordinator from current
geometry, resource state and faults.

Ground-contact forecasts use a short-horizon circular prediction and actual
Earth rotation. Execution always rechecks the numerically J2-propagated current
state. This is a conservative demonstration forecast, not a precision contact
scheduler. Target observation windows remain explicit simulated windows; they
are separate from radio connectivity and are not a complete camera/FOV model.

## Coordination and conflict prevention

The coordinator is the healthy compute/relay-capable node with minimum mean
incident edge cost, with a penalty of 30 per missing peer contact. Ties use node
ID. Election is renewed at reconstruction, so the coordinator may change after
a fault or geometric topology change. It is not simply the highest-battery node.

A new task starts without an owner. Its request exists at a named `request_source`
satellite, normally the first available ingress node. A routed control message
must reach the coordinator before its manifest is shared with other satellites.
A disconnected message remains in its holder's buffer; it is not teleported.
Control hops include acknowledgements/retries and a bounded control service of
eight 2 KB messages per endpoint per simulated second. Control bandwidth is an
illustrative reserved side channel, separate from the 24 Mbps product radio
budget. In this version the control hop is quantized to at least one second.

The manifest is disseminated through valid paths. Only nodes that have received
it can be selected. The existing ADMM relaxation ranks full-chain feasible hosts,
then an independent integer admission check verifies resources and delivery
feasibility. Orphan-placement and route repair retain the 6-particle, 12-iteration
PSO with a feasible greedy incumbent.

Before an owner is committed, an atomic compare-and-swap style guard checks:

- current coordinator epoch;
- expected task lease version;
- absence of another existing owner;
- acknowledgement of the task manifest by the candidate;
- a currently valid coordinator-to-candidate communication path;
- independent CPU, storage, battery, thermal, visibility and delivery feasibility.

The task's lease version increments on assignment. Existing healthy captures and
data holders remain locked; an unavailable uncaptured owner is released before
reassignment. Previously shared copies can support immediate reconstruction-time
repair without an artificial extra wait. If a coordinator or manifest cannot be
reached, buffering/resharing is necessary; the UI shows that delay honestly.

**Test competing claim** submits an intentionally stale/competing ownership
attempt through the real guard. Rejection increments the counter and writes an
audit record; it does not create another owner or reserve more resources.

This is a **single-authority simulator emulating agents**, serialized by one
backend lock. It is not a deployed distributed quorum, Raft implementation, or
partition-safe leader election protocol. Lease and epoch cues demonstrate the
implemented simulator rules, rather than claiming network consensus guarantees.

## Missions, failures and recovery

The mission lifecycle remains:

**Pending → Assigned → Captured → Processed → Delivered**

Deferred, Expired and Failed remain real outcomes. The allocation console also
shows the independent coordination phases: buffered, received, sharing, ready and
committed. A manifest arriving is not equivalent to an observation completing.

Each task includes an event ID, geographic target, capture window, priority,
delivery deadline, capture duration, raw/output sizes, processing cycles and
quality threshold. Normal requests arrive randomly; urgent bursts, event severity
updates and 125-second repeat monitoring remain. New monitoring instances get new
task IDs; priority changes preserve the ID of unfinished work.

Full-chain allocation checks pointing, explicit visibility, safe 12 Wh reserve,
CPU headroom, raw plus output storage, solar-aware thermal forecast and a valid
predicted ground delivery route. Processing duration uses the selected node's
cycle rate and assigned CPU fraction. Product transfers retain per-packet CRC32,
acknowledgements, retries and complete ordered SHA-256 manifest verification.
Sender data is retained until the next hop has committed a complete valid copy.

There are two independent stochastic controls:

| Control | What it does |
|---|---|
| Rare random satellite failures | Small-probability CPU, radio, thermal, node, attitude or antenna faults; default 0.00008 events/s/satellite |
| Random space effects | Frequent illustrative latency, Doppler, packet truncation/bit flip/contact interruption and transient pointing/telemetry problems |

For N healthy/faultable satellites, the independent rare process has nominal mean
spacing `1/(N*rate)` seconds. At 12 nodes that is about 1042 simulated seconds;
at 40 nodes about 313 seconds. Its exponential event schedule is seeded. Not every
short demonstration will contain a rare failure. Packet-effect exaggeration does
not secretly increase this rare hardware rate. The API can set a different rate
for experiments, but the UI default stays small.

Random revival gives a faulted satellite a seeded return opportunity. Recovery
of an isolated node still requires three fresh safe telemetry samples. CPU,
radio and pointing faults preserve unaffected capabilities. Storage failure is
deliberately treated as inaccessible sole data rather than fictional recovery.

With one real ground station and one orbit, there are substantial ground-contact
gaps. Later requests may be buffered, deferred or expire even when the swarm mesh
is intact. This is expected. The implementation does not invent frequent global
contacts to keep a success metric at 100%.

## Continuous animation and clock

The backend preserves one-second physics/event substeps at every speed. The time
slider requests 1×–100× progress per update; actual wall-clock speed depends on
node count, tasks and hardware. A dense 40-node graph costs more than 12 nodes.

The browser renders continuously with `requestAnimationFrame`. It interpolates
between timestamped position/velocity samples using cubic Hermite curves and
uses quaternion SLERP for body orientation. This avoids stepping the satellites
to each WebSocket snapshot. Display interpolation can lag the authoritative clock
by one sample interval; a tightly bounded velocity/central-gravity extrapolation
bridges minor packet jitter (at most 0.3 sample-time seconds per second of
measured simulation rate, capped at 5 simulated seconds); task decisions and deadlines always use backend time.
The 3D context and formation views share that interpolated time. Historical graph
formation snapshots are intentionally frozen for comparison.

## Why Three.js rather than Cosmographia

The following primary documentation was reviewed:

- [NASA/JPL SPICE-enhanced Cosmographia](https://naif.jpl.nasa.gov/naif/cosmographia.html)
- [Cosmographia ephemerides and requirements](https://naif.jpl.nasa.gov/naif/cosmographia_details.html)
- [Cesium SampledPositionProperty](https://cesium.com/learn/cesiumjs/ref-doc/SampledPositionProperty.html)
- [Three.js quaternion SLERP interpolant](https://threejs.org/docs/pages/QuaternionLinearInterpolant.html)
- [NASA solar irradiance reference](https://earth.gsfc.nasa.gov/climate/projects/solar-irradiance/science)

Cosmographia is a standalone SPICE application that requires kernels/catalogs.
It is useful for mission geometry, but is not an embeddable React/WebGL control
surface for this local application. This release retains the existing Three.js
runtime and adds interpolation and explicit scene separation. It does not claim
to bundle or use Cosmographia, Cesium, SPICE kernels or NASA-grade ephemerides.

## HTTP 304 messages are normal

A log such as `GET /assets/three-....js 304 Not Modified` means the browser asked
whether a cached file changed and the server confirmed that the cached copy is
still valid. **304 is not an application error.** Hashed asset names change when
the bundle changes, so the new build gets new URLs automatically. The HTML entry
point is served with `Cache-Control: no-cache` so it can discover those new URLs.
A hard refresh can help if an older page remains open across replacing files.
Use `python run.py --quiet-http` if you prefer to hide routine access logs.

## API and exports

Swagger documentation is at **http://127.0.0.1:8000/docs**. Existing controls and
export routes remain available; the new routes are:

| Endpoint | Purpose |
|---|---|
| POST `/api/conflicts/demo` | Attempt a competing/stale claim against a real assigned task |
| POST `/api/reconstruct` | Rebuild current graph/coordinator and repair task placement/routes |
| GET `/api/state` / WS `/api/live` | Now include coordinator, control buffers, commit audit, solar environment and graph history |
| POST `/api/settings` | Also accepts `random_failures` and `random_failure_rate_per_sat_s` |
| POST `/api/tasks` | Also accepts `request_source` to demonstrate a disconnected ingress buffer |

```json
{
  "event_id": "FIRE_07",
  "request_source": "SAT-01",
  "target": {"lat": 18.52, "lon": 73.86},
  "priority": 5,
  "capture_duration_s": 5,
  "processing_cycles": 8000000,
  "raw_data_mb": 40,
  "output_data_mb": 10,
  "minimum_quality": 0.8
}
```

Omitted task windows are relative to the current clock; supplied windows and
delivery deadlines are absolute simulated seconds. Use POST `/api/control` with
`{"action":"run"}`, `{"action":"pause"}` or `{"action":"step","ticks":6}`.
Satellite fault, recovery, individual battery, advanced CPU/heat/drain stress,
link/partition controls, priority updates, paired GNSS/image campaigns, JSON
export and two-way CSV weights are retained.

## Build and test

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q tests backend/lab_tests
python run.py --headless --seconds 600 --space-effects --export snapshot.json
```

For frontend source development:

```bash
cd frontend
npm ci
npm run dev
# The Python server runs separately on port 8000.
npm run build
```

The Python server serves `frontend/dist`; runtime assets, textures and fonts are
local. Vite proxies API/WebSocket calls during development.

`tests/browser_smoke.cjs` runs a real browser against a server it starts. Install
Playwright in the frontend for that optional test. Existing browser executables
can be selected with `BROWSER_EXECUTABLE`, and `PLAYWRIGHT_MODULE` can point to an
installed Playwright module. Test results and limits are in `evidence/VALIDATION.md`.
Screenshots used for local visual QA are not included in the delivered package.

## Source layout and retained features

New or substantially revised files:

- `backend/app/orbits.py`: numerical J2, annual Sun direction, Earth spin, body frames, eclipse and solar input.
- `backend/app/antennas.py`: mount rays, body occlusion, beam cones and gain.
- `backend/app/network.py`: hard physical contact gates, symmetric component costs, temporal routes and cached control paths.
- `backend/app/coordination.py`: coordinator election, routed buffers, manifests and fenced ownership commits.
- `backend/app/graph_history.py`: initial/reconstructed graph snapshots and valid spanning forests.
- `backend/app/engine.py`: integrates coordination, rare faults, immediate repairs and retained-data workflow.
- `frontend/src/components/AllocationControl.tsx`: prominent coordination, owners, buffers and conflict audit.
- `frontend/src/components/MeshView.tsx`: continuous dual 3D scene and graph history.

The original ADMM, bounded PSO, CUSUM and lumped thermal primitives remain in
`backend/lab_core` and are reused. `python run_legacy_lab.py --nodes 20 --port 8001`
opens the retained original laboratory, with its original separate experiment
and advanced controls. `python run_legacy_scenarios.py` runs its scenario suite.
The exact source input archives remain in `references`. Earlier integrated
model notes are retained in `docs/INTEGRATED_V1_README.md`; this README governs
the corrected primary application's current behaviour.
