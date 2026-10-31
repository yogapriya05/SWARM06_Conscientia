# Literature review

Primary sources were retrieved directly during this build after the search service returned errors. Sources were checked on 31 October 2026. The review distinguishes established methods, engineering choices in this code and extensions that remain unimplemented. The attached mathematical-design PDF, presentation and presenter notes were read as the user's design context; their application-paper citations were not treated as independently reproduced results.

| Source | Contribution relevant to this simulator | How the code uses it | Limit of the connection |
|---|---|---|---|
| Boyd et al., 2011 [1] | Two-block ADMM, scaled multipliers, separable subproblems and primal/dual residuals | A local resource-set proximal update and a shared task-admission projection | Convex relaxation only; bounded live integer planning has no inherited global-optimum guarantee |
| NASA CYGNSS [2] | A constellation can coordinate complementary Earth observations using GNSS-derived measurements | A GNSS-R product and an optical product form a coastal survey | Synthetic tasks; no CYGNSS payload model, mission performance or wind retrieval is reproduced |
| NASA small-spacecraft power and thermal chapters [3] | Generation, loads, storage, heat balance and heat rejection constrain operations | Wh accounting and a reduced temperature predictor with explicit units | Numerical coefficients and accelerated cycles are demo choices requiring hardware calibration |
| NIST/SEMATECH CUSUM [4] | Sequential accumulation can reveal a persistent shift that individual thresholds miss | A one-sided standardized thermal-innovation detector | A residual alarm is evidence of model inconsistency, not proof of a specific failed component |
| NASA DTN overview [5] | Store-and-forward networking preserves useful data through intermittent connectivity | Product holders, buffering, alternate contacts and explicit delivery acknowledgement | Simplified bundles; no full Bundle Protocol, custody protocol or security implementation |
| Hylton et al., NASA NTRS 20240011759 [6] | Space-network architecture and DTN in operational communication contexts | Motivation for separating data availability from instantaneous connectivity | This report is not cited as a specification of our Dijkstra or SABR implementation |
| Kennedy and Eberhart, 1995 [7] | Population search with inertia/attraction-style motion provides a practical heuristic family | A small random-key PSO repair patch with a retained feasible incumbent | The integer decode, weights and budgets are our choices; no global optimality or speed advantage is claimed |

## Why ADMM is the main allocation layer

Each spacecraft has a compact local feasible set while task exclusivity couples hosts. This is a natural place to separate local resource decisions from a shared admission constraint. The augmented dual update in ADMM balances those two blocks. It is materially different from simply calling a greedy resource score “ADMM.” The implementation exposes local updates, the consensus projection, the scaled dual update, both residuals and an explicit termination cap. The analytic and independent-QP checks validate that the frozen solver behaves as the equations specify [1].

Alternative approaches address different problems. A min-cost matching model is attractive for independent one-to-one assignments, but heterogeneous CPU/memory budgets and deadlines exceed that model. A MILP can formulate a small discrete benchmark but adds solver dependencies and can be expensive during repeated repair. Pure dual ascent is easy to separate but can be sensitive to steps and coupling. A full distributed ADMM network would need message and failure handling that this single-process simulator intentionally does not pretend to implement.

The implemented relaxation is admission planning with fixed task resource profiles. It is not a complete time-indexed sensing/processing/communication optimization. Actual transfer contention and sensor-triggered replanning can change delivery outcomes after a feasible admission forecast. This separation makes the demonstration understandable while keeping its claims checkable.

## Why a mission product includes delivery

NASA's DTN material emphasizes retained information and forwarding over interrupted connectivity [5]. A useful operational outcome therefore requires more than declaring an acquisition complete. Here the task state distinguishes queued work, processing, buffered/routed data and delivery. A temporary node disappearance is not permission to invent a new copy of already acquired data. This choice is also consistent with the supplied broader design's distinction between work ownership and data availability.

The GNSS-R and imaging workloads are complementary synthetic measurements of one coastal region, motivated by constellation-based Earth observation [2]. They provide different CPU and data profiles, so an overloaded processor, limited receiver buffer or failed relay changes the actual allocation and delivery chain. The dashboard does not claim to retrieve wind speed or classify real imagery.

## Why resource prediction and fault evidence are separate

Power and thermal source material motivates an explicit physical balance rather than arbitrary increments of battery or temperature [3]. The chosen reduced thermal equation approximates heat rejection locally. Its parameters are deliberately quick enough for an interactive demonstration; they are not orbital-environment qualification results.

CUSUM is applied to innovations rather than raw hot temperatures [4]. A processor doing expected work may get hotter while still matching the model. Unexpected heating instead accumulates evidence; hard protection remains a separate path. The simulator exposes true state for independent validation, which would not be available to a flight implementation. It also freezes sensor timestamps to demonstrate the difference between a fresh observation and a repeatedly displayed cached number.

## Where PSO is useful, and where it is unnecessary

Fault repair changes only a bounded subset of tasks. Encoding host order as random keys lets a small PSO evaluate mixed integer proposals while the feasibility decoder protects resource limits. The incumbent prevents a failed search from worsening its own starting solution. These are integration choices inspired by the general PSO family [7], not a reproduction of the unprovided application papers cited in the uploaded design.

For only three route candidates, exhaustive comparison is simpler and exact over those candidates. PSO is still available for the requested demonstration, but it should be ablated against deterministic selection before being justified for onboard use. Neither a metaheuristic nor a physically connected ring solves future traffic scheduling by itself.

## Evaluation and remaining research

A meaningful comparison should hold arrivals, fault times, sensor noise and contact plans fixed. Compare resource-aware greedy admission, ADMM plus reconstruction, and the same method with bounded PSO repair. Use a small centralized integer model as a benchmark when available. Report delivered priority, deadline success, lost/retried work, conservation violations, recovery latency, solver runtime and traffic overhead. Separate generation-limited operation from saturated traffic; a high completion rate on a lightly loaded synthetic case does not establish superiority.

This package supplies regression/integration checks and deterministic scenarios, not a multi-seed statistical performance study. Useful next steps are calibrated hardware models, real ephemeris/contact traces, joint future link-capacity constraints, checkpoint/data replication policies, a small-instance MILP benchmark, and a genuinely distributed ownership/message layer. Each extension needs independent validation.

## References

1. S. Boyd, N. Parikh, E. Chu, B. Peleato and J. Eckstein, **Distributed Optimization and Statistical Learning via the Alternating Direction Method of Multipliers**, Foundations and Trends in Machine Learning 3(1), 1–122, 2011. The retrieved paper's Sections 2–3 and 7 supply the dual/ADMM and consensus/sharing background. [Author page](https://web.stanford.edu/~boyd/papers/admm_distr_stats.html), [full paper](https://web.stanford.edu/~boyd/papers/pdf/admm_distr_stats.pdf).
2. NASA Science, **CYGNSS: Cyclone Global Navigation Satellite System**. Mission page documents the eight-microsatellite ocean-wind mission. [Mission](https://science.nasa.gov/mission/cygnss/). The synthetic optical pairing is our proposed educational use case, not a claim about CYGNSS's instrument complement.
3. NASA Small Spacecraft Systems Virtual Institute, **State of the Art of Small Spacecraft Technology**, [Power Subsystems](https://www.nasa.gov/smallsat-institute/sst-soa/power-subsystems/) and [Thermal Control](https://www.nasa.gov/smallsat-institute/sst-soa/thermal-control/).
4. NIST/SEMATECH e-Handbook of Statistical Methods, **6.3.2.3. CUSUM Control Charts**. [Handbook](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm). The package's k, h and noise assumptions are illustrative; calibration and a false-alarm study remain necessary.
5. NASA, **Delay/Disruption Tolerant Networking Overview**. [Overview](https://www.nasa.gov/reference/delay-disruption-tolerant-networking-overview/).
6. A. Hylton et al., **The International Space Station, Optical Communications, and Delay Tolerant Networking: Towards A Solar System Internet Architecture**, 2024, NASA NTRS document 20240011759. [Official record and abstract](https://ntrs.nasa.gov/citations/20240011759). Only the official record/abstract was consulted, not an unavailable full-text download.
7. J. Kennedy and R. Eberhart, **Particle swarm optimization**, Proceedings of ICNN'95, pp. 1942–1948, 1995. [DOI](https://doi.org/10.1109/ICNN.1995.488968). Publication metadata was verified through the DOI registration record; no unavailable publisher full text is represented as reviewed.

No copied full articles are included in this distribution. The formulation and code are an original reduced implementation informed by these references and the supplied design, rather than a validated reproduction of any single paper.
