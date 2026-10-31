# Corrected application integration

`backend.app` and the built React app share one authoritative engine. Task and
control progression happen on the backend, never through a scripted UI timeline.

| Component | Role in this release |
|---|---|
| `orbits.py` | RK4 central Earth + J2; shared nominal orbit with 50 km initial chords; Earth spin; annual Sun direction; eclipse and projected solar power/heat |
| `antennas.py` | Local body rays, 10x10x30 cm box occlusion, fore/aft/nadir patches, beam gate and cos^4 gain |
| `network.py` | Symmetric geometry-dependent costs; hard Earth/beam/body/health gates; geometric ground passes; product and cached control routing |
| `coordination.py` | Lowest mean-cost coordinator; source/holder message buffers; routed manifests; epoch and lease compare-and-swap guard |
| `graph_history.py` | Preserved initial and recent reconstruction snapshots; valid minimum spanning forest |
| `allocator.py` | Inherited ADMM with actual manifest recipients as candidate caps and independent full-chain admission |
| `pso.py` | Inherited 12-iteration local repair; feasible greedy incumbent |
| `engine.py` | Observation/data lifecycle, reliable product transport, rare independent faults, recovery and graph/ownership audit |
| `resources.py` | CPU/storage/energy ledgers; inherited thermal model now includes known absorbed solar heat |
| `AllocationControl.tsx` | Visible ingress/coordinator/sharing/owner flow, buffers, leases and rejected claims |
| `MeshView.tsx` | Continuous buffered interpolation/limited extrapolation; dual 3D context and formation view; antenna cones and archived graph selection |

The original `backend.lab_core` remains runnable and its 48 Python tests pass.
Its classic dashboard uses a separate original experiment; its older physical
assumptions do not describe the corrected application's J2/antenna model.

Control metadata uses a reserved low-rate side channel; it is bounded separately
from the product radio budget. This is a single-authority emulation, not a
quorum-based distributed system or a flight protocol implementation. Newly elected
leaders without a task manifest must receive it through a real simulated path.
Previously shared work may be repaired immediately when the successor already
has a valid copy and a resource-safe host is reachable.

Graph history stores compact immutable edge/position records. Full live edge
components and antenna diagnostics remain in `/api/state` and weight exports.
The initial snapshot survives the rolling recent history window.
