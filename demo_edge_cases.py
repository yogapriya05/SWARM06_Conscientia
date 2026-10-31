#!/usr/bin/env python3
"""Edge-case and optimisation demo for the swarm allocation / self-healing simulator.

Put this file next to run.py (the `hackathon/` folder) and run:

    python demo_edge_cases.py              # run everything
    python demo_edge_cases.py --list       # list scenarios
    python demo_edge_cases.py --only B1 C1 # run selected scenarios
    python demo_edge_cases.py --group C    # run one group

Only numpy is needed (the engine does not import FastAPI). Each scenario builds a
fresh deterministic engine, injects one situation, and asserts the behaviour the
design claims. A scenario prints what it observed; a failed assertion = FAIL.
"""
import argparse
import math
import pathlib
import sys
import time
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

from backend.app import coordination  # noqa: E402
from backend.app.engine import Engine  # noqa: E402
from backend.app.models import Config  # noqa: E402
from backend.app.network import build_links, pair_key  # noqa: E402
from backend.lab_core.allocator import solve_relaxation  # noqa: E402

SCENARIOS = []
NOTES = []


def scenario(sid, title):
    def wrap(fn):
        SCENARIOS.append((sid, title, fn))
        return fn
    return wrap


def say(msg):
    NOTES.append(msg)


def make(**kw):
    """Quiet, deterministic engine: no auto workload, no random faults/revival."""
    cfg = dict(auto_tasks=False, random_failures=False, random_revival=False)
    cfg.update(kw)
    return Engine(Config(**cfg), seed_tasks=False)


def run_until(e, pred, limit=150):
    for _ in range(limit):
        if pred():
            return
        e.step(emit_snapshot=False)
        e.validate()          # conservation / bounds invariants every second
    assert pred(), "condition not reached within %d s" % limit


def assigned_task(e, **kw):
    t = e.add_task(**kw)
    run_until(e, lambda: t.owner is not None or t.status in {"deferred", "expired"}, 40)
    return t


# --------------------------------------------------------------------------- A
@scenario("A1", "Full pipeline: pending > assigned > captured > processed > delivered")
def a1():
    e = make()
    t = e.add_task()
    say(f"new task: owner={t.owner}, coordination={t.coordination_status} (buffered, no owner yet)")
    assert t.owner is None
    run_until(e, lambda: t.status == "delivered", 200)
    path = [x["status"] for x in t.transitions]
    assert path == ["pending", "assigned", "captured", "processed", "delivered"], path
    assert t.delivered_at <= t.delivery_deadline and t.valid_product
    say("lifecycle: " + " > ".join(path))
    say(f"owner={t.owner}, delivered at T+{t.delivered_at:.0f}s (deadline T+{t.delivery_deadline:.0f}s), "
        f"ownership commits={e.state.counters['ownership_commits']}")
    assert e.state.counters["ownership_commits"] == 1


@scenario("A2", "Coordinator = lowest mean link cost; request travels there before any owner exists")
def a2():
    e = make()
    leader = e.state.coordinator["node_id"]
    eligible = [s for s in e.state.satellites.values() if s.can_compute and s.can_relay]
    expected = min(eligible, key=lambda s: (s.node_weight, s.id)).id
    assert leader == expected
    say("node scores (lower wins): " + ", ".join(
        f"{s.id}={s.node_weight:.2f}" for s in sorted(eligible, key=lambda s: s.node_weight)[:4]) + " ...")
    t = e.add_task()
    seen = [t.coordination_status]
    while t.owner is None:
        e.step(emit_snapshot=False)
        if t.coordination_status != seen[-1]:
            seen.append(t.coordination_status)
        assert e.state.time_s < 60
    say(f"coordinator={leader} (epoch {e.state.coordinator['epoch']}); phases seen: {' > '.join(seen)}")
    assert t.request_path[-1] == leader and t.owner in t.shared_with
    say(f"request path {' > '.join(t.request_path)}; owner {t.owner} held the manifest before commit")


@scenario("A3", "Competing / stale ownership claim is rejected, owner and reservations unchanged")
def a3():
    e = make()
    t = assigned_task(e)
    owner, version = t.owner, t.lease_version
    cpu = e.state.satellites[owner].allocated_cpu
    ok = coordination.conflict_demo(e.state, t)
    last = e.state.commit_audit[-1]
    assert not ok and t.owner == owner and t.lease_version == version
    assert e.state.satellites[owner].allocated_cpu == cpu
    assert e.state.counters["conflicts_prevented"] == 1
    say(f"claim rejected: '{last['reason']}'; owner still {owner}, lease v{version}, CPU reservation {cpu:.0f}% unchanged")


@scenario("A4", "Disconnected ingress node: request stays buffered, then flows after reconnection")
def a4():
    e = make()
    source = "SAT-01"
    assert source != e.state.coordinator["node_id"]
    e.inject(source, "radio")
    t = e.add_task(request_source=source)
    e.step(6, emit_snapshot=False)
    msg = next(m for m in e.state.control_messages if m["task_id"] == t.task_id and m["kind"] == "request")
    say(f"after 6 s with {source} radio down: owner={t.owner}, message status={msg['status']}, holder={msg['holder']}")
    assert t.owner is None and msg["status"] == "buffered" and msg["holder"] == source
    e.recover(source)
    run_until(e, lambda: t.owner is not None, 80)
    say(f"after recovery: owner={t.owner}, request path {' > '.join(t.request_path)}")
    assert t.request_path[0] == source


@scenario("A5", "Newly elected leader without the manifest must receive it over a real path")
def a5():
    e = make()
    t = assigned_task(e)
    leader = e.state.coordinator["node_id"]
    t.shared_with = [leader]
    t.owner = None
    t.status = "pending"
    t.coordination_status = "ready"
    e.inject(leader, "cpu")                      # old leader loses compute -> re-election
    new = e.state.coordinator["node_id"]
    msgs = [m for m in e.state.control_messages if m["kind"] == "election_manifest" and m["target"] == new]
    say(f"leader {leader} lost compute; new leader {new} (epoch {e.state.coordinator['epoch']}); "
        f"has manifest? {new in t.shared_with}; status={t.coordination_status}")
    assert new not in t.shared_with and t.owner is None and msgs
    run_until(e, lambda: new in t.shared_with, 60)
    say("manifest delivered to the new leader through routed control message")


# --------------------------------------------------------------------------- B
@scenario("B1", "ADMM on frozen problems vs the analytic answer (split, deferral, capacity spill)")
def b1():
    # (1) two identical hosts, one task: closed form x = 0.5 each.
    n, m = 2, 1
    A = [np.array([[1.0]]), np.array([[1.0]])]
    b = [np.array([5.0]), np.array([5.0])]
    x, z, hist, conv = solve_relaxation(np.array([[-2.0], [-2.0]]), A, b, np.ones((n, m)), 200, 2.0, 1e-6)
    say(f"identical hosts: z={z.ravel().round(4)} (analytic 0.5, 0.5), iterations={len(hist)}, converged={conv}")
    assert conv and np.allclose(z.ravel(), 0.5, atol=1e-3)
    # (2) positive cost: defer instead of forcing placement.
    x, z, hist, conv = solve_relaxation(np.array([[1.0], [1.0]]), A, b, np.ones((n, m)), 200, 2.0, 1e-6)
    say(f"positive cost: z={z.ravel().round(4)} -> task left unassigned (deferral)")
    assert np.allclose(z, 0, atol=1e-6)
    # (3) host 0 resource-limited to 0.3 of the task: spill goes to host 1.
    b2 = [np.array([0.3]), np.array([5.0])]
    x, z, hist, conv = solve_relaxation(np.array([[-3.0], [-2.0]]), A, b2, np.ones((n, m)), 400, 2.0, 1e-6)
    say(f"capacity-limited preferred host: z={z.ravel().round(3)} (host0 capped at 0.3, rest to host1)")
    assert abs(z[0, 0] - 0.3) < 5e-3 and abs(z.sum() - 1) < 5e-3
    # (4) ineligible (cap=0) host gets nothing.
    x, z, hist, conv = solve_relaxation(np.array([[-9.0], [-1.0]]), A, [np.array([5.0])] * 2,
                                        np.array([[0.0], [1.0]]), 200, 2.0, 1e-6)
    say(f"ineligible host (cap 0) despite best cost: z={z.ravel().round(3)}")
    assert z[0, 0] == 0 and z[1, 0] > 0.9
    r = hist[-1]
    say(f"final residuals primal={r['primal']:.2e}, dual={r['dual']:.2e} (both below tolerance when converged)")


@scenario("B2", "Live optimisation: ranking follows battery, load and route; changing resources changes the owner")
def b2():
    e = make()
    t = assigned_task(e)
    rank = sorted(e.state.allocator["fractions"][t.task_id].items(), key=lambda kv: -kv[1])[:4]
    costs = e.state.allocator["costs"][t.task_id]
    say("ADMM top hosts (fraction, cost): " + ", ".join(f"{k}=({v:.2f}, {costs[k]:.2f})" for k, v in rank))
    say(f"owner chosen: {t.owner}; ADMM iterations={e.state.allocator['iterations']}, "
        f"converged={e.state.allocator['converged']}, residual p={e.state.allocator['primal_residual']:.1e}")
    assert t.owner in [k for k, _ in rank]                 # owner comes from ADMM's top-ranked hosts
    first = t.owner
    e2 = make()
    e2.state.satellites[first].battery_wh = 25            # make the previous winner unattractive
    t2 = assigned_task(e2)
    say(f"same request with {first} battery 25 Wh: owner moves to {t2.owner}")
    assert t2.owner != first
    e3 = make()
    e3.set_stress(first, cpu_pct=80)                      # heavy external load on the winner
    t3 = assigned_task(e3)
    say(f"same request with {first} under 80% external CPU load: owner moves to {t3.owner}")
    assert t3.owner != first


@scenario("B3", "PSO repair: bounded (6 particles x 12 iterations), never worse than the greedy incumbent")
def b3():
    e = make()
    hosts = ["SAT-01", "SAT-02", "SAT-03", "SAT-04"]                   # crowd tasks onto few nodes
    tasks = [e.add_task(priority=p, allowed_satellites=hosts) for p in (5, 4, 3, 2, 1)]
    n = len(e.state.satellites)                                       # wait until every manifest has been shared
    run_until(e, lambda: all(t.owner is not None and len(t.shared_with) == n for t in tasks), 60)
    say("initial owners: " + ", ".join(f"{t.task_id}(p{t.priority})->{t.owner}" for t in tasks))
    unstarted = [t for t in tasks if t.status == "assigned" and t.progress_capture_s == 0]
    owners = {}
    for t in unstarted:
        owners.setdefault(t.owner, []).append(t)
    victim = max(owners, key=lambda k: len(owners[k]))
    hit = list(owners[victim])
    e.inject(victim, "thermal")
    st = e.state.repair
    keys = ("iterations", "evaluations", "improved", "incumbent_score", "best_score", "scope_tasks")
    say(f"{victim} thermal fault orphans {len(hit)} unstarted task(s); PSO: " + ", ".join(
        f"{k}={st[k]:.2f}" if isinstance(st[k], float) else f"{k}={st[k]}" for k in keys if k in st))
    assert st["iterations"] == 12 and st["evaluations"] == 6 * 13
    assert st["best_score"] >= st["incumbent_score"] - 1e-9            # incumbent can never be made worse
    assert all(t.owner not in (None, victim) for t in hit)
    say("re-hosted at the same simulated instant, one owner each: " + ", ".join(f"{t.task_id}->{t.owner}" for t in hit))
    say("note: improved=False is normal - with few hosts the ADMM-ranked greedy answer is already the best found")


# --------------------------------------------------------------------------- C
@scenario("C1", "Owner fails before capture: immediate reallocation, no clock advance, single owner")
def c1():
    e = make()
    t = assigned_task(e)
    old, now = t.owner, e.state.time_s
    e.inject(old, "thermal")
    assert e.state.time_s == now and t.status == "assigned" and t.owner != old and t.reassignments == 1
    say(f"{old} thermal fault at T+{now:.0f}s -> {t.owner} owns it at T+{e.state.time_s:.0f}s "
        f"(reassignments={t.reassignments}, lease v{t.lease_version})")
    run_until(e, lambda: t.status == "delivered", 250)
    say("task still delivered end-to-end after the failure")


@scenario("C2", "CPU fault after capture: raw data and checkpoint retained, nothing recaptured")
def c2():
    e = make()
    t = assigned_task(e)
    run_until(e, lambda: t.status == "captured", 100)
    e.step(2, emit_snapshot=False)
    owner, at, prog = t.owner, t.captured_at, t.progress_cycles
    e.inject(owner, "cpu", duration_s=6)
    e.step(4, emit_snapshot=False)
    say(f"during fault: status={t.status}, holder={t.holder}, checkpoint {prog:.0f} -> {t.progress_cycles:.0f} cycles (frozen)")
    assert t.status == "captured" and t.holder == owner and t.progress_cycles == prog
    run_until(e, lambda: t.status == "delivered", 250)
    assert t.captures == 1 and t.captured_at == at and t.reassignments == 0
    say(f"resumed on {owner}, delivered; captures={t.captures}, reassignments={t.reassignments}")


@scenario("C3", "Storage fault on the only data copy: task FAILS, no copy is invented")
def c3():
    e = make()
    t = assigned_task(e)
    run_until(e, lambda: t.status == "captured", 100)
    e.inject(t.owner, "storage")
    say(f"status after storage fault on holder: {t.status} ('{t.note}')")
    assert t.status == "failed"
    e.validate()


@scenario("C4", "Relay link fails mid-delivery: new route, same product, no recapture")
def c4():
    e = make()
    t = assigned_task(e)
    run_until(e, lambda: t.status == "processed", 150)
    hop, original, stamp = t.route_hops[0], t.route[:], t.captured_at
    e.block_link(hop["source"], hop["target"])
    say(f"blocked {hop['source']}-{hop['target']}; route {' > '.join(original)} -> {' > '.join(t.route)}; reroutes={e.state.counters['reroutes']}")
    assert t.route and t.route != original and e.state.counters["reroutes"] >= 1
    run_until(e, lambda: t.status == "delivered", 250)
    assert t.captures == 1 and t.captured_at == stamp


@scenario("C5", "Unexpected heating: CUSUM isolates the node before the hard 76 C limit")
def c5():
    e = make()
    sat = e.state.satellites["SAT-02"]
    e.set_stress("SAT-02", heat_w=20)
    for _ in range(12):
        e.step(emit_snapshot=False)
        if "SAT-02" in e.monitor.latched:
            break
    say(f"CUSUM alarm at T+{e.state.time_s:.0f}s with temperature {sat.temperature_c:.1f} C (hard limit 76 C); reasons={sat.reasons}")
    assert "SAT-02" in e.monitor.latched and sat.temperature_c < e.state.config.thermal_limit_c
    assert sat.health == "isolated"


@scenario("C6", "Cooling failure + full CPU load: gradual heating until hard thermal protection")
def c6():
    e = make()
    sat = e.state.satellites["SAT-03"]
    start = sat.temperature_c
    e.set_stress("SAT-03", cpu_pct=100, cooling_scale=0.2)
    e.step(emit_snapshot=False)
    assert sat.temperature_c > start and sat.health != "isolated"
    for _ in range(60):
        e.step(emit_snapshot=False)
        if sat.health == "isolated":
            break
    say(f"temperature {start:.1f} C -> {sat.temperature_c:.1f} C; isolated at T+{e.state.time_s:.0f}s; reasons={sat.reasons}")
    assert sat.health == "isolated"


@scenario("C7", "Stale telemetry: healthy at injection, isolated only after 8 s of silence")
def c7():
    e = make()
    e.inject("SAT-04", "stale")
    now_state = e.state.satellites["SAT-04"].health
    e.step(9, emit_snapshot=False)
    later = e.state.satellites["SAT-04"]
    say(f"immediately after freezing sensors: {now_state}; after 9 s: {later.health} ({later.reasons})")
    assert now_state == "healthy" and later.health == "isolated"


@scenario("C8", "Recovery hysteresis: a recovered node must show 3 fresh safe samples to rejoin")
def c8():
    e = make()
    e.inject("SAT-05", "offline")
    e.recover("SAT-05")
    sat = e.state.satellites["SAT-05"]
    say(f"right after recovery command: {sat.health} ({sat.reasons})")
    assert sat.health == "isolated"
    for _ in range(10):
        e.step(emit_snapshot=False)
        if sat.health == "healthy":
            break
    say(f"healthy again at T+{e.state.time_s:.0f}s; recovered_nodes={e.state.counters['recovered_nodes']}")
    assert sat.health == "healthy"


@scenario("C9", "CPU overload: unstarted work is moved; running work is throttled, never over-served")
def c9():
    e = make()
    t = assigned_task(e)
    old = t.owner
    e.set_stress(old, cpu_pct=85)
    assert t.owner != old and t.status == "assigned"
    say(f"85% external load on {old}: uncaptured task moved to {t.owner}")
    run_until(e, lambda: t.status == "captured", 100)
    owner, before = t.owner, t.progress_cycles
    e.set_stress(owner, cpu_pct=89)
    e.step(1, emit_snapshot=False)
    gained = t.progress_cycles - before
    full = e.state.satellites[owner].cycles_per_s * t.cpu_demand / 100
    say(f"running image on {owner} under 89% load: gained {gained:,.0f} of {full:,.0f} cycles this second (throttled)")
    assert 0 < gained < full


@scenario("C10", "All nodes offline: task is deferred, then expires; nothing is invented")
def c10():
    e = make()
    for sat in list(e.state.satellites):
        e.inject(sat, "offline")
    t = e.add_task(delivery_deadline=e.state.time_s + 8)
    e.step(10, emit_snapshot=False)
    say(f"status={t.status}, owner={t.owner}, attempts={t.attempts} ({t.note})")
    assert t.status == "expired" and t.owner is None and t.attempts == 0


@scenario("C11", "Impossible deadline: never reported as delivered late")
def c11():
    e = make()
    t = e.add_task(delivery_deadline=e.state.time_s + 3)
    e.step(8, emit_snapshot=False)
    say(f"status={t.status} (deadline T+{t.delivery_deadline:.0f}s, now T+{e.state.time_s:.0f}s); delivered_mb={e.state.counters['delivered_mb']}")
    assert t.status in {"deferred", "expired"} and e.state.counters["delivered_mb"] == 0


@scenario("C12", "Attitude fault: image that cannot be pointed is released and re-hosted")
def c12():
    e = make()
    t = assigned_task(e)
    old = t.owner
    e.inject(old, "attitude")
    say(f"{old} attitude fault -> owner {t.owner}, status {t.status}")
    assert t.owner != old


@scenario("C13", "Rare random failures run independently of packet-effect switch")
def c13():
    e = Engine(Config(auto_tasks=False, space_effects=False, random_failures=True,
                      random_failure_rate_per_sat_s=0.01, random_revival=False), seed_tasks=False)
    e.step(120, emit_snapshot=False)
    e.validate()
    c = e.state.counters
    say(f"120 s, packet effects OFF: random_failures={c['random_failures']}, bit_flips={c['bit_flips']}, retries={c['retries']}")
    assert c["random_failures"] > 0 and c["bit_flips"] == 0


# --------------------------------------------------------------------------- D
@scenario("D1", "Packet corruption: CRC32 rejects bit-flips and truncation, retries, product still verified")
def d1():
    for mode, counter in [("bit_flip", "bit_flips"), ("partial_packet", "partial_packets")]:
        e = make(space_effects=True)
        e.state.next_effect_s = 1e9
        t = assigned_task(e)
        run_until(e, lambda: t.status == "processed", 150)
        hop = t.route_hops[0]
        key = pair_key(hop["source"], hop["target"])
        e.state.effects[key] = {"kind": mode, "until_s": e.state.time_s + 5, "source": hop["source"], "target": hop["target"]}
        e.state.version += 1
        e.step(4, emit_snapshot=False)
        assert e.state.counters[counter] > 0 and t.status != "delivered"
        run_until(e, lambda: t.status == "delivered", 250)
        say(f"{mode}: {e.state.counters[counter]} bad packets caught, retries={e.state.counters['retries']}, "
            f"acked={e.state.counters['packets_acked']}, valid product={t.valid_product}")
        assert t.valid_product and e.state.counters["retries"] > 0


# --------------------------------------------------------------------------- E
@scenario("E1", "Bounded queue and atomic campaigns")
def e1():
    e = make()
    e.state.config.max_active_tasks = 3
    e.add_campaign()                                     # uses 2 slots
    before = len(e.state.tasks)
    try:
        e.add_campaign()                                 # needs 2, only 1 left
        raise AssertionError("campaign should have been refused")
    except ValueError as err:
        say(f"second campaign refused: '{err}'; task count stayed {before} (no half-created pair)")
    assert len(e.state.tasks) == before


@scenario("E2", "Input validation (swarm count, size, speed, spacing, failure rate)")
def e2():
    bad = [dict(swarm_count=3), dict(satellites_per_swarm=0), dict(satellites_per_swarm=21),
           dict(speed=0.5), dict(speed=101), dict(spacing_km=40.0), dict(random_failure_rate_per_sat_s=0.5)]
    for kw in bad:
        try:
            Config(**kw)
            raise AssertionError(f"{kw} should be rejected")
        except ValueError:
            pass
    say(f"{len(bad)} invalid configurations all rejected")
    e = make()
    for kw, label in [(dict(delivery_deadline=-1), "past deadline"), (dict(request_source="NOPE"), "unknown source"),
                      (dict(observation_window=[10, 5]), "inverted window")]:
        try:
            e.add_task(**kw)
            raise AssertionError(label)
        except ValueError:
            pass
    say("invalid task requests rejected (past deadline, unknown source, inverted window)")


@scenario("E3", "Determinism: same seed gives the same run; time step does not change results")
def e3():
    def run(chunks):
        e = make(space_effects=True, random_failures=True, random_failure_rate_per_sat_s=0.002, seed=11)
        e.add_task()
        for c in chunks:
            e.step(c, emit_snapshot=False)
        s = e.state
        return (round(s.satellites["SAT-01"].battery_wh, 9), dict(s.counters), next(iter(s.tasks.values())).status)
    a, b = run([60]), run([1] * 60)
    say(f"60 s as one step vs 60 x 1 s: identical? {a == b}; counters sample {dict(list(a[1].items())[:3])}")
    assert a == b


@scenario("E4", "Antenna pointing fault: links lost to body/beam blockage and graph re-weighted")
def e4():
    e = make()
    before = {l.key: l for l in build_links(e.state) if l.source == "SAT-01" and l.target != "GND"}
    e.inject("SAT-01", "antenna")
    after = {l.key: l for l in build_links(e.state) if l.source == "SAT-01" and l.target != "GND"}
    dead = [k for k, l in after.items() if not l.available]
    changed = sum(abs(after[k].weight - before[k].weight) > 0.5 for k in before)
    say(f"SAT-01: {len(dead)}/{len(after)} links now unavailable ({after[dead[0]].reason if dead else '-'}); {changed} weights changed")
    assert dead and changed


@scenario("E5", "Graph history: the initial graph is immutable across 18 reconstructions")
def e5():
    import json
    e = make()
    first = json.dumps(e.snapshot()["graph_history"][0], sort_keys=True)
    for _ in range(18):
        e.reconstruct("demo snapshot")
    snaps = e.snapshot()["graph_history"]
    say(f"{len(snaps)} snapshots kept; first epoch={snaps[0]['epoch']}; spanning backbone edges={len(snaps[0]['backbone'])} for {len(e.state.satellites)} nodes")
    assert snaps[0]["epoch"] == 1 and len(snaps) == 16 and json.dumps(snaps[0], sort_keys=True) == first
    assert len(snaps[0]["backbone"]) == len(e.state.satellites) - 1


@scenario("E6", "Scale and degenerate sizes: 1 satellite and 40 satellites")
def e6():
    one = make(swarm_count=1, satellites_per_swarm=1)
    t = one.add_task()
    one.step(10, emit_snapshot=False)
    say(f"1 satellite: coordinator={one.state.coordinator['node_id']}, task owner={t.owner}, coordination={t.coordination_status}")
    big = make(satellites_per_swarm=20)
    links = [l for l in build_links(big.state) if l.target != "GND"]
    assert len(big.state.satellites) == 40 and len(links) == 40 * 39 // 2
    tt = big.add_task()
    t0 = time.perf_counter()
    big.step(40, emit_snapshot=False)
    big.validate()
    say(f"40 satellites: {len(links)} candidate links, 40 s simulated in {time.perf_counter() - t0:.1f}s wall, owner={tt.owner}")
    assert all(math.isfinite(l.weight) and l.weight > 0 for l in links)


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--group")
    args = ap.parse_args()
    if args.list:
        for sid, title, _ in SCENARIOS:
            print(f"{sid:4} {title}")
        return 0
    chosen = [s for s in SCENARIOS
              if (not args.only or s[0] in args.only) and (not args.group or s[0].startswith(args.group.upper()))]
    results = []
    for sid, title, fn in chosen:
        NOTES.clear()
        t0 = time.perf_counter()
        try:
            fn()
            ok = True
            err = ""
        except Exception as ex:  # noqa: BLE001 - report every failure, keep going
            ok = False
            err = "".join(traceback.format_exception_only(type(ex), ex)).strip()
        dt = time.perf_counter() - t0
        print(f"[{'PASS' if ok else 'FAIL'}] {sid:3} {title}  ({dt:.1f}s)")
        for n in NOTES:
            print("        " + n)
        if not ok:
            print("        !! " + err)
        results.append(ok)
    print(f"\n{sum(results)}/{len(results)} scenarios passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
