import type { Event } from "../types";

export default function EventLog({ events }: { events: Event[] }) {
  return <div><div className="card-title"><span>Event stream</span><span className="muted">latest first</span></div><div className="event-list">{events.slice(0, 12).map((event) => <div className={`event ${event.severity}`} key={event.id}><span className="event-tick">T+{event.tick}</span><span><strong>{event.kind}</strong><br />{event.message}</span></div>)}</div></div>;
}
