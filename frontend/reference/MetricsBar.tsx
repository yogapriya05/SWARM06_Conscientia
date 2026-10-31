import type { Metrics } from "../types";

export default function MetricsBar({ metrics }: { metrics: Metrics }) {
  return <section className="metrics">{[["Active nodes", `${metrics.network_availability}%`], ["Active tasks", metrics.active_tasks], ["Completed", metrics.completed_tasks], ["Reassignments", metrics.reassignment_count], ["Recovery", `${metrics.average_recovery_ticks.toFixed(1)} ticks`]].map(([label, value]) => <div className="metric" key={label as string}><span>{label}</span><strong>{value}</strong></div>)}</section>;
}
