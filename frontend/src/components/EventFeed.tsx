import { useFleetStore } from "../store/useFleetStore";
import { Panel } from "./Panel";

export function EventFeed() {
  const snapshot = useFleetStore((s) => s.snapshot);
  const events = snapshot?.primary.events ?? [];

  return (
    <Panel title="Mesh Traffic (P2P, no central server)">
      <div className="flex max-h-40 flex-col gap-1 overflow-y-auto font-mono text-[11px] leading-relaxed">
        {events
          .slice()
          .reverse()
          .map((e, i) => (
            <div key={i} className="text-[var(--text-dim)]">
              <span className="text-cyan-400">▸</span> {e}
            </div>
          ))}
        {events.length === 0 && <div className="text-[var(--text-dim)]">No mesh traffic yet…</div>}
      </div>
    </Panel>
  );
}
