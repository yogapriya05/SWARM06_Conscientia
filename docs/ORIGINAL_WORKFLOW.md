# Simulation workflow

## Model

The default scenario contains two three-satellite swarms. Each satellite has a
position in a normalized orbital plane, a 1,000 Wh battery, a CPU budget, a
thermal state and finite storage. Links are valid only when their configured
distance is below the 1,200 km radio range. The default mesh is deliberately
redundant: each swarm has a ring and the two swarms have two cross-links.

At every tick, the engine:

1. computes solar input from a deterministic orbit phase and eclipse window;
2. calculates load from assigned tasks and baseline avionics;
3. charges or discharges the battery with converter efficiency and clamps it to
   safe limits;
4. updates temperature using generated heat and radiative cooling;
5. advances task work and completes tasks that reach their duration;
6. detects stale/failed nodes and repairs affected task ownership and routes.

This is a deliberately executable engineering model rather than a flight
qualification model. Values are representative of a small satellite payload.
The energy update follows the IAC paper's conservation principle:

`battery_delta = (solar_input - load) * dt * efficiency`

with separate charge/discharge efficiencies and a conservative low-state
reserve. The allocation and repair flow follows the companion allocation
monograph and LRPSO-DTA paper: screen candidates, lock work already committed
in the near horizon, and search only the free suffix.

## REST demo

```bash
# Initial state
curl http://localhost:8000/api/state

# Add a task
curl -X POST http://localhost:8000/api/tasks \
  -H 'content-type: application/json' \
  -d '{"name":"Thermal map","kind":"sensing","priority":4,
       "cpu_required":20,"storage_required":10,"power_required":40,
       "duration_ticks":5,"deadline_tick":40}'

# Fail SAT-02; affected tasks are isolated, rerouted and reassigned
curl -X POST http://localhost:8000/api/failures \
  -H 'content-type: application/json' \
  -d '{"satellite_id":"SAT-02","reason":"simulated transceiver fault"}'

# Advance three ticks
curl -X POST http://localhost:8000/api/tick \
  -H 'content-type: application/json' -d '{"ticks":3}'
```

The websocket endpoint `/api/live` emits a complete state snapshot after every
tick, task admission and failure recovery. The frontend consumes those
snapshots directly, so the dashboard remains usable if the simulation loop is
running without a browser refresh.

## Configurable swarms

The dashboard can rebuild the constellation with 1–8 swarms and 1–12
satellites per swarm. Each satellite receives an orbital phase and advances
along a deterministic circular trajectory on every simulation step. Failure
injection can target an entire swarm, select a failure mode, and choose a
duration. At the end of that duration the swarm is automatically marked
online and pending work is allocated again; the manual reconnect action
performs the same recovery immediately.
