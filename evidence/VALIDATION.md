# Corrected build validation — 31 October 2026

This report describes the corrected J2/antenna/coordinator application. Files in
`previous/` describe the earlier integrated release. Intermediate migration logs
are not evidence of the final build.

| Check | Result | Evidence |
|---|---|---|
| Integrated mission, API and new physics/coordination tests | 31 passed | `all_tests.txt`, `all_tests.xml` |
| Retained original Swarm Lab tests | 48 passed | `all_tests.txt`, `all_tests.xml` |
| Combined Python suite | **79 passed** | `all_tests.txt` |
| Final integrated suite after rate-setting cleanup | 31 passed | `final_integrated_tests.txt` |
| TypeScript and production build | Passed | `frontend_build.txt` |
| Chromium/WebGL workflow checks | **16 passed; no JavaScript errors** | `browser_results.json`, `browser_run.txt` |
| 40-satellite configuration | Created and rendered successfully through the real UI | `browser_results.json` |
| Continuous animation | Multiple intermediate render positions sampled between backend ticks, without a large snapshot jump | `browser_results.json` |
| Fresh ZIP extraction | Built UI assets work without Node dependencies; manifest/claim/reassignment checks passed; conditional asset responses are correctly 304 | `package_smoke.txt` |
| Full orbit with solar/eclipses, stochastic failures and packet disturbances | 6,000 seconds, 1,934 ticks with at least one eclipsed satellite; four rare satellite failures; 34 route repairs | `full_orbit_final.json` |
| Honest deadline accounting | Full-orbit run: 40 delivered, 542 expired, eight active | `full_orbit_final.json` |
| Reliable transport | Full-orbit run: 163 bit flips, 76 partial packets, 254 retries, 400 MB acknowledged at ground | `full_orbit_final.json` |

The browser test starts its own server and checks the prominent allocation
console, buffered requests before ownership, receipt of manifests before commits,
visible conflict rejection, immediate repair of previously shared work without
advancing time, initial/reconstructed 3D graph selection, continuous rendering,
separate rare-fault and link-effect switches, accelerated deliveries, antenna/gain
diagnostics, battery edits, 40-node configuration and mobile overflow.

The new independent numerical checks cover:

- exact 50 km initial adjacent Euclidean spacing, with a common plane and radius;
- the analytic equatorial J2 acceleration component;
- RK4 convergence between one-second and half-second integration;
- annual Sun geometry, sidereal Earth rotation, constant far-field irradiance,
  cylindrical eclipse and eclipse removal of solar power/heating;
- mount ray/body-box shadowing, usable antenna cones and graph-weight changes;
- lowest-weight coordinator selection and actual routed request/manifest phases;
- retention/retry of disconnected ingress buffers;
- stale/competing claim rejection without another owner or extra reservation;
- immutable initial graph retention across more than 16 reconstructions;
- rare hardware faults independent from the packet-effect switch;
- control transfer when a newly elected leader does not yet have a manifest;
- JSON-safe API snapshots, validated settings and HTML cache policy.

A long run with one real ground station necessarily contains long periods without
a feasible downlink. Its expired tasks are expected physical/contact outcomes,
not silently counted successes. This build does not promise all deadlines under
arbitrary faults or network partitions. It remains a single-authority emulator,
with a coarse antenna box/cone model and a basic thermal/solar model.

The installed Starlette/httpx test-client pair emits one deprecation warning;
all required assertions pass. Browser screenshots were inspected locally and are
not included in this deliverable.
