import type { SimulationState } from "../types";

export default function MeshView({ state, selected, onSelect, activeRoute = [] }: { state: SimulationState; selected: string | null; onSelect: (id: string) => void; activeRoute?: string[] }) {
  const width = 620, height = 330;
  const points = Object.fromEntries(state.satellites.map((s) => [s.id, { x: 40 + s.x * 540, y: 30 + s.y * 260 }]));
  return <div><div className="card-title"><span>Orbital mesh</span><span className="muted">{state.links.filter((l) => l.available).length} active links</span></div>
    <svg className="mesh" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Satellite mesh">
      {state.links.map((l) => { const active = activeRoute.includes(l.source) && activeRoute.includes(l.target); return <line key={`${l.source}-${l.target}`} x1={points[l.source].x} y1={points[l.source].y} x2={points[l.target].x} y2={points[l.target].y} className={`link ${l.available ? "" : "unavailable"} ${active ? "active-route" : ""}`} />; })}
      {activeRoute.slice(0, -1).map((id, index) => {
        const next = points[activeRoute[index + 1]];
        const point = points[id];
        if (!point || !next) return null;
        return <circle key={`packet-${id}`} r="4" className="packet"><animate attributeName="cx" values={`${point.x};${next.x};${point.x}`} dur="2.4s" repeatCount="indefinite" /><animate attributeName="cy" values={`${point.y};${next.y};${point.y}`} dur="2.4s" repeatCount="indefinite" /></circle>;
      })}
      {state.satellites.map((s) => <g key={s.id} onClick={() => onSelect(s.id)} className="node" role="button" tabIndex={0}><circle cx={points[s.id].x} cy={points[s.id].y} r={selected === s.id ? 24 : 19} className={`node-circle ${s.status}`} /><text x={points[s.id].x} y={points[s.id].y + 4} textAnchor="middle">{s.name.replace("SAT-", "")}</text><text x={points[s.id].x} y={points[s.id].y + 39} textAnchor="middle" className="node-label">{Math.round(s.battery)}% · {s.status}</text></g>)}
      <g className="ground-station"><rect x="520" y="278" width="70" height="22" rx="4" /><text x="555" y="293" textAnchor="middle">GROUND</text></g>
    </svg>
    <div className="legend"><span><i className="legend-dot online" /> operating</span><span><i className="legend-dot failed" /> failed</span><span><i className="legend-line active" /> active route</span><span><i className="legend-line dashed" /> unavailable contact</span></div>
  </div>;
}
