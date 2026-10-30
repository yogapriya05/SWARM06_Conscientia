export type SatelliteStatus = "online" | "failed" | "isolated" | "degraded";

export interface Satellite {
  id: string;
  name: string;
  swarm: string;
  x: number;
  y: number;
  status: SatelliteStatus;
  battery: number;
  temperature: number;
  cpu_load: number;
  storage_used: number;
  owner_task_ids: string[];
  solar_input_w: number;
  power_draw_w: number;
}

export interface Task {
  id: string;
  name: string;
  kind: string;
  priority: number;
  cpu_required: number;
  storage_required: number;
  power_required: number;
  duration_ticks: number;
  deadline_tick: number;
  owner_id?: string | null;
  route: string[];
  status: string;
  created_tick: number;
}

export interface Link {
  source: string;
  target: string;
  distance_km: number;
  capacity_mbps: number;
  latency_ms: number;
  available: boolean;
}

export interface Event {
  id: string;
  tick: number;
  kind: string;
  message: string;
  severity: string;
  satellite_id?: string | null;
  task_id?: string | null;
}

export interface Metrics {
  total_tasks: number;
  completed_tasks: number;
  active_tasks: number;
  failed_tasks: number;
  reassignment_count: number;
  recovery_count: number;
  average_recovery_ticks: number;
  network_availability: number;
}

export interface SimulationState {
  tick: number;
  running: boolean;
  satellites: Satellite[];
  tasks: Task[];
  links: Link[];
  events: Event[];
  metrics: Metrics;
  selected_satellite_id?: string | null;
}
