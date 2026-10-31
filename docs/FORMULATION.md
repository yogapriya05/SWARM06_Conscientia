# Model and algorithm

This is a working local simulator, not flight software. It integrates resource admission, synthetic sensing, fault isolation and delivered-data accounting. The optimization agents and their messages are emulated inside one Python process. The requested package modules are independent of the dashboard.

## 1. Mission

A coastal survey is a campaign with two complementary products for the same region and time of request:

- **GNSS-R measurement:** acquire/process a synthetic GNSS reflectometry delay-Doppler product, using 18 CPU percentage points for 12 s and producing 4 MB by default.
- **Remote sensing image:** acquire/process a synthetic optical image, using 30 CPU percentage points for 20 s and producing 14 MB by default.

A GNSS-R receiver observes navigation signals reflected from the surface. These spacecraft are consumers of GNSS signals, not navigation-signal transmitters. The mission is inspired by the complementary use of reflected-signal measurements and imaging. No measured geophysical accuracy is claimed. A campaign is complete only after both products reach ground before their respective deadlines. The products are independent jobs, so failure of one does not manufacture or erase the other.

All nodes carry a GNSS-R receiver; every fourth node lacks the camera. Each spacecraft has a fixed synthetic phase, a broad imaging footprint and a changing sunlight/eclipse state. Observation opportunities are generated from a phase/longitude mask, not orbital propagation. Nodes do not maneuver to reach targets.

Automatic arrivals create a new, uniquely identified campaign every 24 simulated seconds. Operators can add either product or another survey pair. Every acquisition instance has its own task ID. A physical node keeps its ID across failure and recovery; it is excluded from the applicable computation/routing graph while unavailable.

## 2. State, units and decisions

For spacecraft i, the simulator stores energy E_i [Wh], lumped temperature T_i [°C], CPU capacity F_i [percentage points], payload CPU reservations L_i, external CPU load X_i, stored data B_i [decimal MB], reserved data R_i [MB], capabilities, component fault flags, and timestamped sensor readings.

A task j has priority p_j, demand a_j [CPU percentage points], remaining work W_j [CPU percentage points × s], product/peak reserved memory b_j [MB], release time, delivery deadline d_j, required payload and region. The bundled acquisition/processing duration is W_j/a_j. There is no separate raw-image buffer or streaming waveform simulator; the declared memory profile represents the peak working/product reservation of this reduced workload.

The binary admission decision is y_ij = 1 when i becomes the exclusive processing owner of j. CPU service is a fixed declared profile, with proportional throttling if externally injected work takes capacity away. ADMM dynamically chooses resource-bundle placement/admission; it does not optimize processor clock frequency or arbitrary continuous CPU profiles.

Routing also selects a current data holder and an ordered sequence of contact hops. Processing owner and data holder can differ. A successful relay changes the holder only when the entire product has crossed the hop.

## 3. Physical dynamics

### Energy

With Δt in seconds,

E_i(t+Δt) = clip[E_i(t) + (0.9 P_solar,i − P_load,i) Δt / 3600, 0, 100].

P_load = 8 + 0.45 CPU_actual + 8 I_radio-active + P_extra-drain [W].

P_solar is 46 W in synthetic sunlight and zero in eclipse. A 180 s accelerated cycle has 120 s of sunlight. Charge efficiency is 0.9. CPU is in percentage points of the configured processor. The defaults are demonstration coefficients, not measurements of a particular CubeSat.

Actual energy is integrated once per interval. Admission does not debit actual battery energy and therefore does not double-charge a job. The admission forecast gives no credit for future sunlight and includes existing committed CPU in baseline power. The energy-used metric is the gross integrated electrical load, not net battery depletion; solar generation can increase battery energy while this metric increases.

### Temperature

C dT/dt = Q − K(T−T_ref),

Q = 4 + 0.50 CPU_actual + 5 I_radio-active + Q_unmodelled [W].

C = 20 J/K, K = 0.9 × cooling_scale W/K, T_ref = 20 °C. The exact constant-input solution is

T(t+Δt) = T_eq + [T(t)−T_eq] exp(−K Δt/C), with T_eq = T_ref + Q/K.

This is a deliberately accelerated lumped approximation to internal conduction and locally linearized radiative heat rejection. It is not atmospheric convection. The thermal fault demonstration applies 100% external CPU and reduces cooling to 20%; the high heat load progressively crosses the 76 °C protection threshold. Separately, an unmodelled heater makes actual temperature diverge from the nominal predictor and can trigger CUSUM before the hard threshold.

### CPU and data

15% CPU is reserved for essential control. New payload jobs must fit under the remaining CPU budget after external stress and existing commitments. For already running work under stress,

service_ij = a_j min[1, max(0,100−15−X_i) / Σ_running a_j].

W_j decreases by service_ij Δt. Thus service cannot exceed remaining hardware capacity. CPU failure removes processing capability; radio capability can remain. Thermal, battery, storage and full-node protection isolate both capabilities. A radio fault can leave local processing operational, but no new observation is admitted on a host without a predicted delivery path.

Memory is reserved on admission. When processing finishes, reservation becomes actual product storage. Receiver memory is reserved before a hop begins. At hop acknowledgement, sender storage is released and receiver storage becomes actual. Partial transmissions do not erase the sender's full product. Aborting a partial hop releases only the partial receiver reservation and resets that hop's byte progress.

## 4. Frozen admission problem

At each planning epoch, retain unaffected running jobs as a fixed prefix. Consider up to 24 queued/orphan tasks and all currently known hosts. Let x_ij ∈ [0,1] be the relaxed admission fraction, not an executable command. Let q_ij ∈ {0,1} encode payload, visibility, fresh health, individual resource checks and existence of a predicted delivery route. Ineligible pairs have upper bound zero.

The convex relaxation minimizes

    Σ_i,j c_ij x_ij + (γ/2) Σ_i,j x_ij²

subject to

    0 ≤ x_ij ≤ q_ij
    A_i x_i ≤ h_i                         for every satellite
    Σ_i x_ij ≤ 1                         for every task.

The inequality permits deferral instead of forcing infeasible work. An equivalent missed-utility cost includes v_j(1−Σ_i x_ij); the constant Σ_j v_j can be omitted.

The code uses γ=0.3. Its linear coefficient is

c_ij = 0.4(1−E_i/100) + 0.35 L_i/100
       + 0.2 max(0,T_i−40)/30 + 0.2 e_j + 0.04 route_cost_ij − v_j,

v_j = 1.2 + 0.38 p_j + min(2, processing_duration_j / remaining_deadline_j),

e_j = 0.45 W_j/3600 + 0.006 b_j [Wh].

These weights are explicit engineering preferences. They are not constants taken from a publication. The quadratic term makes the frozen objective strictly convex but can also spread one task fractionally over equivalent hosts. Integer reconstruction resolves that ambiguity.

### Local resource set

The four normalized rows of A_i represent CPU, memory, energy and thermal CPU headroom:

1. Σ a_j x_ij ≤ max(0,100−15−X_i−L_i).
2. Σ b_j x_ij ≤ storage_capacity−stored−reserved.
3. Σ e_j x_ij ≤ conservative available energy after reserve and baseline horizon load.
4. Σ a_j x_ij ≤ thermal CPU headroom.

The common forecast horizon is the longest candidate processing duration plus 8 s (up to 240 s). Its baseline load includes control, external stress, existing payload commitments and injected battery drain. Available energy uses the lower of actual energy and sensor energy minus 0.12 Wh. Thermal prediction starts from the upper of actual temperature and measured temperature plus 0.6 °C. These are illustrative margins, not calibrated confidence bounds.

For thermal headroom, invert the exact constant-load temperature solution at that horizon to find allowable heat under the 74 °C planning limit (2 °C below hard protection). Subtract baseline heat and convert the remainder to incremental CPU. Both existing load and new jobs are accounted for.

The routing existence test is a single-product forecast. Shared future contact capacity is not jointly reserved in ADMM, and the relaxation is not an end-to-end multicommodity scheduling model. Real capacity contention is enforced by the execution layer; jobs can subsequently miss deadlines when forecast contention is too optimistic. Such misses are recorded explicitly.

## 5. ADMM and dual decomposition

Introduce a consensus copy z of x. Let f(x) contain separable local costs and local feasible-set indicators. Let g(z) be the indicator of nonnegative task columns summing to at most one. Then

    minimize f(x)+g(z), subject to x−z=0.

The scaled augmented Lagrangian is

    Lρ = f(x)+g(z)+(ρ/2)||x−z+u||²−(ρ/2)||u||².

The scaled multiplier u = λ/ρ is the dual variable. Local resource tradeoffs remain in f; the shared exclusive-admission constraint remains in g. This is a two-block ADMM splitting with separable x subproblems, not a many-block extension with an assumed convergence theorem.

The update rules implemented in allocator.py are:

    v_i = [ρ(z_i−u_i)−c_i] / (ρ+γ)
    x_i ← EuclideanProjection_Fi(v_i)
    z_:j ← Projection_{z≥0, Σz≤1}(x_:j+u_:j)
    u_i ← u_i+x_i−z_i.

Dykstra projections solve each small local projection numerically over a box and four halfspaces, capped at 600 inner cycles and tested for both iterate change and constraint error. The task projection uses the exact capped-simplex sorting formula. The outer default cap is 32 iterations, with ρ=2. Both residuals must be below 0.005 to report convergence:

    r = ||x−z||₂,    s = ρ||z_new−z_old||₂.

The UI explicitly reports an iteration-budget stop when residual tolerance is not reached. A frozen convex ADMM problem under appropriate exactness and coordination assumptions has the familiar convergence result [1]. The live, bounded-iteration, numerically projected, changing integer simulator is not covered by a global optimality claim. Tests compare frozen subproblems against analytic answers and an independent SciPy SLSQP reference.

Only queued work is reconsidered in ordinary admission. New epochs rebuild coordinates from current task IDs; stale dual vectors are not incorrectly reused after a task/host dimension change. Coordination is emulated as independent local updates plus a coordinator projection. The displayed 3 N M K scalar count represents one x upload, one z return and one explicit dual-state record per epoch; it is an accounting estimate, not measured RF traffic. A distributed implementation would need actual message versions, membership, authentication and failure semantics.

## 6. Executable reconstruction and bounded PSO

A positive fractional variable never starts a task by itself. Tasks are considered by repair urgency, priority, deadline and ID. Hosts are ranked by descending consensus fraction and then linear cost. Before each assignment, the engine independently checks current CPU, memory, battery forecast, temperature forecast, health, timestamp, payload, synthetic visibility, deadline and predicted route. Reservations are updated before the next task is considered. A rejected task stays queued until its deadline.

For up to eight orphan tasks, PSO searches random-key host orderings against copied resource ledgers. It uses 8 particles and 12 iterations by default (104 evaluated schedules including initialization). The all-zero key is the ADMM-ranked greedy incumbent. Only a strictly better feasible candidate replaces it. The objective rewards repaired task priority, then ADMM preference and route cost. Each committed host is checked again against the authoritative state. No unaffected running job is moved to improve a heuristic score.

For route repair, time-dependent search produces up to three distinct candidate contact paths. A bounded scalar PSO search chooses among those alternatives using arrival time plus twice the link-cost sum. With so few candidates, direct enumeration would be an appropriate cheaper baseline; PSO is included as requested, with no claim that it outperforms exact routing or enumeration. Neither placement PSO nor route PSO creates a physical link or guarantees global optimality [7].

## 7. Contacts and transfer execution

A persistent reciprocal ring supplies baseline inter-satellite contacts. Short chords appear in synthetic 80 s cycles. S1 has continuous synthetic ground access; the opposite node has an additional periodic ground window. Component health and manually blocked edges remove links. Future routing uses currently known health; it does not assume a failed satellite will recover before an unknown time.

Each contact has start, end, effective rate, one-way latency and a relative weight. For one complete product, a feasible next-hop arrival is

    depart = max(previous_arrival, contact_start)
    arrive = depart + 8 × product_MB / rate_Mbps + latency_s.

It must fit inside the contact and before the delivery deadline. Earliest-arrival Dijkstra search uses the FIFO property of these contacts. Receiver storage and health are checked. Alternate routes are generated by banning edges of the first path. The code is a simplified contact-graph planner inspired by scheduled DTN, not a complete CCSDS SABR implementation [5,6].

The relative edge weight combines normalized latency (0.45), endpoint battery penalty (0.25), nominal loss (0.20), and high-temperature penalty (0.10). Rates are multiplied by (1−loss) to model effective goodput. There is no stochastic packet-loss/retransmission model.

At each tick, a reciprocal physical pair has a shared half-duplex byte budget. Each satellite also shares a 24 Mbps radio budget across transmission and reception; ground has 48 Mbps. A latency allowance is removed from each pair's interval. Multiple products cannot each consume the entire link independently. Products advance by at most one hop per tick, so time is quantized conservatively. Delivery must occur on a tick boundary not later than the deadline. Future contacts are heuristic forecasts; actual execution checks contact, capacity and receiver reservation again.

## 8. Detection, isolation and recovery

Sensors are sampled after each physical interval. Independent zero-mean Gaussian noise is added to temperature (0.15 °C), energy (0.03 Wh), CPU (0.5 percentage points) and stored-data readings (0.04 MB), scaled by the UI noise setting. Noise affects observations, not true energy or temperature. Battery and CPU samples are clipped to physical ranges. The resource ledger, rather than a noisy storage reading, controls buffer allocation.

Telemetry carries its own timestamp. Freezing sensor data preserves the old timestamp. Replayed samples do not accumulate new CUSUM evidence. A sample older than 8 s is unavailable for admission and causes isolation. Staleness establishes lack of trustworthy state, not permanent spacecraft death.

Temperature CUSUM uses the standardized innovation between the measured new temperature and the nominal thermal prediction:

    z = (T_measured − T_predicted) / max(0.15,0.15 noise_scale)
    C ← max(0, C+z−0.6)
    alarm when C ≥ 12.

This upper-tail detector targets unexpected heating. A known workload raises predicted temperature too, so normal processing is not itself a fault. A cooling reduction included in the known model is caught through the hard limit; an unmodelled heater produces a residual alarm. Thresholds are illustrative and have no claimed false-alarm probability or component-level diagnostic certainty [4]. CUSUM latches until explicit recovery/reset. High temperature and low battery also have independent hard checks against true simulator state; this truth guard is not a deployable onboard estimator.

A compute owner that becomes unavailable loses its uncheckpointed progress. The engine releases its working reservation, requeues the same task ID, records lost work and uses ADMM plus bounded repair to assign a new owner. Retrying is recorded as another attempt. A data holder that fails retains its unique stored product; the system waits for that holder to recover, or discards the product explicitly when its deadline expires. It never teleports completed data to an arbitrary replacement node. Broken routes can be changed while retaining the existing holder.

Manual recovery clears fault flags and stress, restores battery to at least 65 Wh and temperature to at most 34 °C, and waits for three fresh safe samples. This is an operator reset of a demo, not an autonomous physical battery repair. A timed transient flag simply expires; actual resources still have to recover and CUSUM is reset. Safety isolation uses hysteresis below 70 °C and above reserve plus 0.5 Wh before re-entry.

Recovery time measures task service resumption: from a detected processing/route interruption to reassignment or a useful resumed transfer. Immediate repair in the same simulated epoch legitimately gives 0 s. This is different from wall-clock solver runtime, node repair duration, and final delivery latency.

## 9. Ownership and scope

One authoritative state writer and a service lock serialize API commands, the simulation loop, snapshots and resets. A task has at most one processing owner and one confirmed data holder. This provides deterministic local exclusivity. It does not implement replicated ownership leases, quorum commits, Byzantine agreement or partition-safe distributed execution. Those features appeared in the supplied broader design; they must not be claimed for this smaller prototype.

Other exclusions are detailed attitude control, orbital/J2 propagation, GNSS waveform processing, image inference accuracy, RF contention beyond the stated radio budgets, radiation faults, sensor authentication, flash wear, battery electrochemistry, calibrated uncertainty sets, terminal eclipse-safe sets and a recursive-feasibility proof. The code is useful for studying integration behavior under controlled faults; it cannot establish flight readiness.

## 10. What is checked

The executable invariant validator independently checks CPU ownership sums, stored-product sums, reservation sums, buffer capacity, energy bounds, finite temperature, task progress bounds, actual transfer capacity, and absence of late successful delivery. Tests cover deferral, all nodes unavailable, transient recovery, payload restrictions, frozen data, external CPU throttling, unexpected heating, battery drain, route repair, failed holders, noisy sensors, reproducible seeds, HTTP validation, loop control, WebSocket updates and 3/6/20/40 nodes.

The package contains test results and reproducible scenario output in `evidence/`. These are measured local integration results, not evidence of PSO superiority, flight safety or distributed convergence under faults. See `LITERATURE.md` for source interpretation and `../README.md` for commands.
