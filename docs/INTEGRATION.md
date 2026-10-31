# Integration decisions

The production app is `backend.app`, served by `run.py`; the prebuilt React app
is `frontend/dist`. This avoids two unrelated simulators disagreeing about the
same displayed state. There is no browser-local simulator and no timer that
pretends a recovery stage completed.

| Swarm Lab component | Integration |
|---|---|
| ADMM proximal projections and two-block solve | Imported directly by `backend.app.allocator` |
| Random-key PSO with greedy incumbent | Imported directly by `backend.app.pso` |
| Lumped thermal forecast and dynamics | Imported directly by `backend.app.resources` |
| Residual CUSUM | Imported directly by `backend.app.failures` |
| Admission and integer reconstruction pattern | Extended with capture windows, raw/output buffers, complete delivery feasibility |
| Contact routing and radio budget principles | Extended into a symmetric complete logical graph with timed ground passes and per-packet accounting |
| Data-holder and receiver reservation logic | Extended for raw capture, processing checkpoints, valid products and atomic reliable hops |
| Background server and WebSocket | One service lock, no frontend tick-loop, streaming authoritative snapshots |
| Advanced manual stress and paired campaigns | Preserved in API, campaign button and optional original laboratory dashboard |
| Original implementation and tests | Complete `backend.lab_core`; original tests with redirected imports; unmodified input archive |

Satellite IDs are SAT-01..SAT-40; swarm IDs are SWARM-01/02. Interface strings
and exports use seconds, Wh, MB, Mbps, km, Celsius and CPU percentage consistently.
The raw observer remains the task owner after relay handoffs; `holder` tracks
where the valid data currently resides. These are different concepts.

All original standalone papers are retained. The original FORMULATION and
LITERATURE files describe the laboratory on which this extension is built;
README.md describes the new integrated mission's actual implementation and limits.
