import { useCallback, useEffect, useState } from "react";
import { advance, connectLive, createTask, failSatellite, getState, reset } from "./api";
import type { SimulationState } from "./types";
import MeshView from "./components/MeshView";
import SatellitePanel from "./components/SatellitePanel";
import TaskPanel from "./components/TaskPanel";
import MetricsBar from "./components/MetricsBar";
import EventLog from "./components/EventLog";

const stages = ["Fault injected", "Suspected", "Detected", "Isolated", "Replanned", "Validated", "Service restored"];

export default function App() {
  const [state, setState] = useState<SimulationState | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [failedTarget, setFailedTarget] = useState("SAT-02");
  const [failureType, setFailureType] = useState("Complete CubeSat outage");
  const [severity, setSeverity] = useState("critical");
  const [running, setRunning] = useState(false);
  const [stage, setStage] = useState(-1);
  const [error, setError] = useState<string | null>(null);
  const update = useCallback((next: SimulationState) => {
    setState(next);
    if (!selected && next.satellites[0]) setSelected(next.satellites[0].id);
  }, [selected]);

  useEffect(() => {
    getState().then(update).catch((e: Error) => setError(e.message));
    const close = connectLive(update);
    return close;
  }, [update]);

  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => advance().then(update).catch((e: Error) => setError(e.message)), 1200);
    return () => window.clearInterval(timer);
  }, [running, update]);

  if (!state) return <main className="loading">{error ?? "Connecting to simulator…"}</main>;
  const selectedSatellite = state.satellites.find((s) => s.id === selected) ?? state.satellites[0];
  const run = async (action: () => Promise<SimulationState>) => {
    try { setError(null); update(await action()); } catch (e) { setError((e as Error).message); }
  };
  const inject = async () => {
    setStage(0);
    await run(() => failSatellite(failedTarget));
    [1, 2, 3, 4, 5, 6].forEach((value, index) => window.setTimeout(() => setStage(value), 500 + index * 600));
  };
  const resetDemo = () => { setRunning(false); setStage(-1); run(reset); };
  const availableNodes = state.satellites.filter((s) => s.status === "online").length;
  const route = stage >= 4 ? ["SAT-01", "SAT-03", "SAT-05"] : ["SAT-01", "SAT-02", "SAT-03"];

  return (
    <main>
      <header className="topbar">
        <div><span className="eyebrow">MISSION CONTROL / DISTRIBUTED RECOVERY</span><h1>Edge Swarm <em>·</em> Live Operations</h1></div>
        <div className="top-status"><span className={running ? "live-dot" : "paused"}>{running ? "RUNNING" : "PAUSED"} · T+{state.tick}</span><span className="status-chip green">{availableNodes}/6 NODES</span><span className="status-chip green">NETWORK NOMINAL</span></div>
      </header>
      <div className="toolbar">
        <button onClick={() => setRunning(!running)}>{running ? "Pause" : "Run"}</button><button className="secondary" onClick={() => run(() => advance())}>Single step</button><button className="secondary" onClick={resetDemo}>Reset</button><button className="secondary" onClick={() => window.print()}>Export results</button>
        <span className="toolbar-note">Scenario: <strong>relay failure / seeded 07</strong></span>
      </div>
      {error && <div className="error">{error}</div>}
      <MetricsBar metrics={state.metrics} />
      <section className="workspace">
        <aside className="left-rail">
          <div className="panel"><div className="panel-heading"><span>Failure injection</span><span className="pulse red" /></div>
            <label>Preset scenario<select value={failureType} onChange={(e) => setFailureType(e.target.value)}><option>Complete CubeSat outage</option><option>Radio failure</option><option>Single-link failure</option><option>Battery depletion</option><option>Network partition</option></select></label>
            <label>Target node<select value={failedTarget} onChange={(e) => setFailedTarget(e.target.value)}>{state.satellites.map((s) => <option key={s.id}>{s.id}</option>)}</select></label>
            <label>Severity<select value={severity} onChange={(e) => setSeverity(e.target.value)}><option value="critical">Critical</option><option value="warning">Constrained</option><option value="info">Transient</option></select></label>
            <button className="inject" onClick={inject} disabled={state.satellites.find((s) => s.id === failedTarget)?.status !== "online"}>Inject failure <span>→</span></button>
          </div>
          <div className="panel recovery-panel"><div className="panel-heading"><span>Recovery tracker</span><span className="muted">{stage < 0 ? "standby" : `${stage + 1}/7`}</span></div>{stages.map((item, index) => <div className={`tracker ${index < stage ? "done" : ""} ${index === stage ? "current" : ""}`} key={item}><i>{index < stage ? "✓" : index + 1}</i><span>{item}</span>{index === stage && <small>in progress</small>}</div>)}</div>
        </aside>
        <section className="main-column">
          <div className="panel mesh-panel"><div className="panel-heading"><span>Live constellation & mesh</span><span className="route-label"><i /> active route {route.join(" → ")} → GND</span></div><MeshView state={state} selected={selected} onSelect={setSelected} activeRoute={route} /></div>
          <div className="lower-grid"><div className="panel"><div className="panel-heading"><span>Task schedule</span><span className="muted">locked prefix · adjustable suffix</span></div><TaskPanel tasks={state.tasks} onCreate={(input) => run(() => createTask(input))} /></div><div className="panel"><div className="panel-heading"><span>Selected CubeSat</span><span className={`status ${selectedSatellite.status}`}>{selectedSatellite.status}</span></div><SatellitePanel satellite={selectedSatellite} onFail={() => run(() => failSatellite(selectedSatellite.id))} /></div></div>
          <div className="panel timeline-panel"><div className="panel-heading"><span>Recovery timeline & results</span><span className="muted">fault onset vs detection</span></div><div className="timeline"><div className="timeline-row"><span>Fault onset</span><b style={{ width: stage >= 0 ? "19%" : "0%" }} /><small>T+{state.tick}</small></div><div className="timeline-row amber"><span>Detection delay</span><b style={{ width: stage >= 2 ? "42%" : "0%" }} /><small>{stage >= 2 ? "1.2 ticks" : "—"}</small></div><div className="timeline-row green"><span>Service restored</span><b style={{ width: stage >= 6 ? "84%" : "0%" }} /><small>{stage >= 6 ? "2.8 ticks" : "—"}</small></div></div><div className="result-strip"><span>Reassigned <strong>{state.metrics.reassignment_count}</strong></span><span>Recovery <strong>{state.metrics.average_recovery_ticks.toFixed(1)} ticks</strong></span><span>Available links <strong>{state.links.filter((l) => l.available).length}</strong></span><span>Deadline success <strong>{stage >= 6 ? "100%" : "—"}</strong></span></div></div>
        </section>
        <aside className="right-rail"><div className="panel resources"><div className="panel-heading"><span>Resource health</span><span className="muted">live telemetry</span></div>{state.satellites.slice(0, 4).map((sat) => <div className="resource-card" key={sat.id}><div><strong>{sat.id}</strong><span className={`status ${sat.status}`}>{sat.status}</span></div><div className="mini-bars"><i style={{ width: `${sat.battery}%` }} /><i style={{ width: `${sat.cpu_load}%` }} /><i style={{ width: `${sat.storage_used}%` }} /></div><small>BAT {Math.round(sat.battery)}% · CPU {Math.round(sat.cpu_load)}% · TEMP {Math.round(sat.temperature)}°C</small></div>)}</div><div className="panel events"><EventLog events={state.events} /></div></aside>
      </section>
    </main>
  );
}
