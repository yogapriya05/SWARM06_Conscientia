import type { Satellite } from "../types";

export default function SatellitePanel({ satellite, onFail }: { satellite: Satellite; onFail: () => void }) {
  return <div><div className="card-title"><span>{satellite.name}</span><span className={`status ${satellite.status}`}>{satellite.status}</span></div><p className="muted">{satellite.swarm} · coordinates {satellite.x.toFixed(2)}, {satellite.y.toFixed(2)}</p>
    <div className="resource-list">{[["Battery", satellite.battery, "%"], ["CPU load", satellite.cpu_load, "%"], ["Storage", satellite.storage_used, "%"], ["Thermal", satellite.temperature, "°C"]].map(([label, value, unit]) => <div className="resource" key={label as string}><div><span>{label}</span><strong>{Number(value).toFixed(1)}{unit}</strong></div><div className="bar"><i style={{ width: `${label === "Thermal" ? Math.min(100, (Number(value) / 90) * 100) : Number(value)}%` }} /></div></div>)}</div>
    <div className="sat-actions"><span className="muted">{satellite.owner_task_ids.length} assigned tasks · {satellite.power_draw_w.toFixed(0)} W draw</span><button disabled={satellite.status !== "online"} onClick={onFail}>Fail node</button></div>
  </div>;
}
