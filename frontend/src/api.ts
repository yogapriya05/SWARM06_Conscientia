import type { SimulationState, Task } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? `http://${window.location.hostname}:8000`;

export async function getState(): Promise<SimulationState> {
  const response = await fetch(`${API_URL}/api/state`);
  if (!response.ok) throw new Error(`State request failed: ${response.status}`);
  return response.json();
}

export async function advance(ticks = 1): Promise<SimulationState> {
  const response = await fetch(`${API_URL}/api/tick`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticks }),
  });
  if (!response.ok) throw new Error(`Tick request failed: ${response.status}`);
  return response.json();
}

export async function createTask(input: Partial<Task>): Promise<SimulationState> {
  const response = await fetch(`${API_URL}/api/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(`Task request failed: ${response.status}`);
  return response.json();
}

export async function failSatellite(id: string): Promise<SimulationState> {
  const response = await fetch(`${API_URL}/api/failures`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ satellite_id: id, reason: "manual demonstration fault" }),
  });
  if (!response.ok) throw new Error(`Failure request failed: ${response.status}`);
  return response.json();
}

export async function reset(): Promise<SimulationState> {
  const response = await fetch(`${API_URL}/api/reset`, { method: "POST" });
  if (!response.ok) throw new Error(`Reset request failed: ${response.status}`);
  return response.json();
}

export function connectLive(onState: (state: SimulationState) => void): () => void {
  const socket = new WebSocket(`${API_URL.replace(/^http/, "ws")}/api/live`);
  socket.onmessage = (event) => onState(JSON.parse(event.data) as SimulationState);
  return () => socket.close();
}
