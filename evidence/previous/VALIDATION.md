# Validation — integrated hackathon build

Validation date: 31 October 2026. Software versions are recorded in
`environment.json`. Runtime measurements depend on the test host and are not
spacecraft performance claims.

| Check | Result | Evidence |
|---|---|---|
| Integrated behavioral/API tests | 20 passed | `all_tests.txt`, `all_tests.xml` |
| Retained Swarm Lab regression tests | 48 passed | `all_tests.txt`, `all_tests.xml` |
| Combined Python suite | **68 passed** | `all_tests.txt` |
| Original deterministic lab scenarios | 9 passed; 940 tick-level invariant checks | `scenarios.json` |
| Frontend | TypeScript checking and Vite production build passed | `frontend_build.txt` |
| Real Chromium / WebGL smoke test | 11 workflow checks passed, no browser JavaScript errors | `browser_results.json`, `browser_run.txt` |
| Seed 7, 12 satellites, 600 simulated seconds with space effects | 52 delivered, 2 still active, no expired/failed tasks | `headless_run.txt`, `headless_snapshot.json` |
| Seed 7, 40 satellites, 600 simulated seconds with space effects | 56 delivered, 2 active, 4 route repairs | `forty_nodes_benchmark.json` |
| Seed 7, 12 satellites, 6,000 simulated seconds with space effects | 588 delivered, 3 active, 13 reassignments, 40 route repairs | `long_run_fast.txt` |
| Long-run reliable transport | 1,380 bit flips and 1,460 partial packets detected; 3,044 retries; 5,880 MB delivered | `long_run_fast.txt` |
| Extracted release ZIP | Built assets served without Node dependencies; immediate reallocation and 20-node CLI run passed | `package_smoke.txt` |
| Bounded history | Long run archived 288 delivered tasks while keeping cumulative totals | `long_run_fast.txt` |

The browser test exercises the actual interface: creating a request, injecting
its owner's CPU fault, observing immediate reassignment without advancing the
clock, enabling space effects, using 100× speed, observing changing orbital
positions and real deliveries, opening solver diagnostics, exporting weights,
editing an individual battery, configuring 2×20 and 1×20 satellites, and checking
390-pixel mobile layout. Screenshots were inspected as local QA and are not
included as deliverables.

The Python suite also checks retained images and CPU checkpoints during faults,
capability-specific radio/CPU behaviour, failed-holder revival, contact rerouting,
stale telemetry, visibility independent of the mesh, unsafe battery/storage
rejection, ID-preserving priority updates, storage loss, CRC rejection and retries,
symmetric complete 40-node topology, circular radii, eclipse, seeded replay,
speed-independent one-second server substeps, API input validation and safe
response to external CPU stress.

Successful seeded examples do not imply all workloads can meet their deadlines.
The tests deliberately include deferred, expired and failed outcomes. The complete
mesh and access/ground-pass windows are explicit demo abstractions, documented in
the main README. A single backend emulates agents and owns commits; this is not
a distributed flight deployment or a real radio/protocol conformance test.

The installed Starlette/httpx combination emitted one test-client deprecation
warning. No test failed because of it. All required assertions passed.
