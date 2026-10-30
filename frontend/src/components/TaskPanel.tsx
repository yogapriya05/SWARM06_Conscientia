import { useState } from "react";
import type { Task } from "../types";

export default function TaskPanel({ tasks, onCreate }: { tasks: Task[]; onCreate: (input: Partial<Task>) => void }) {
  const [name, setName] = useState("Earth observation");
  return <div><div className="card-title"><span>Mission tasks</span><span className="muted">{tasks.length} total</span></div><form className="task-form" onSubmit={(e) => { e.preventDefault(); onCreate({ name, kind: "sensing", priority: 3, cpu_required: 18, storage_required: 8, power_required: 35, duration_ticks: 4, deadline_tick: 30 }); }}><input value={name} onChange={(e) => setName(e.target.value)} aria-label="Task name" /><button type="submit">Add task</button></form><div className="task-list">{tasks.slice().reverse().map((task) => <div className="task-row" key={task.id}><div><strong>{task.name}</strong><small>{task.kind} · P{task.priority} · {task.route.join(" → ") || "unrouted"}</small></div><span className={`task-status ${task.status}`}>{task.status}</span></div>)}</div></div>;
}
