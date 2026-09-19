import { useFleetStore } from "../store/useFleetStore";
import { Panel } from "./Panel";

const TICK_SECONDS = 0.1; // matches the backend simulation step (DT)

function parseEvent(raw: string): { time: string; message: string; color: string } {
  const m = raw.match(/^\[t(\d+)\]\s*(.*)$/);
  const tick = m ? Number(m[1]) : null;
  const message = m ? m[2] : raw;

  let time = "--:--";
  if (tick !== null) {
    const total = Math.floor(tick * TICK_SECONDS);
    time = `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
  }

  let color = "#60a5fa"; // announcements
  if (/WON/.test(message)) color = "#34d399";
  else if (/\bbid\b/.test(message)) color = "#fbbf24";

  return { time, message, color };
}

export function EventFeed() {
  const snapshot = useFleetStore((s) => s.snapshot);
  const events = snapshot?.primary.events ?? [];
  const rows = events.slice().reverse().map(parseEvent);

  return (
    <Panel
      title="Recent Events"
      right={<span className="text-[10px] text-[var(--text-dim)]">P2P mesh · no central server</span>}
    >
      <div className="flex max-h-48 flex-col gap-2 overflow-y-auto pr-1">
        {rows.map((r, i) => (
          <div key={i} className="flex items-start gap-2.5 text-[12px] leading-snug">
            <span className="mt-1 h-2 w-2 flex-shrink-0 rounded-full" style={{ background: r.color }} />
            <span className="mono w-10 flex-shrink-0 text-[11px] text-[var(--text-dim)]">{r.time}</span>
            <span className="text-[var(--text-primary)]/90">{r.message}</span>
          </div>
        ))}
        {rows.length === 0 && <div className="text-xs text-[var(--text-dim)]">No mesh traffic yet…</div>}
      </div>
    </Panel>
  );
}
