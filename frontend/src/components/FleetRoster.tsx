import { useFleetStore } from "../store/useFleetStore";
import { Panel } from "./Panel";

const STATE_LABEL: Record<string, string> = {
  idle: "Idle",
  bidding: "Bidding",
  moving_to_pickup: "→ Pickup",
  moving_to_dropoff: "→ Dropoff",
  returning_to_charge: "→ Charger",
  charging: "Charging",
  waiting: "Waiting",
  yielding: "Yielding",
};

export function FleetRoster() {
  const snapshot = useFleetStore((s) => s.snapshot);
  const selectedAgentId = useFleetStore((s) => s.selectedAgentId);
  const setSelectedAgentId = useFleetStore((s) => s.setSelectedAgentId);
  const agents = snapshot?.primary.agents ?? [];

  return (
    <Panel title={`Fleet Roster · ${agents.length} units`}>
      <div className="flex max-h-56 flex-col gap-1.5 overflow-y-auto pr-1">
        {agents.map((a) => {
          const batteryColor = a.battery > 40 ? "#34d399" : a.battery > 20 ? "#f59e0b" : "#f87171";
          const selected = selectedAgentId === a.id;
          return (
            <button
              key={a.id}
              onClick={() => setSelectedAgentId(selected ? null : a.id)}
              className={`flex items-center gap-2.5 rounded-lg border px-2.5 py-1.5 text-left transition ${
                selected ? "border-cyan-500/50 bg-cyan-500/10" : "border-transparent bg-[#0a0f1c] hover:border-[var(--border-soft)]"
              }`}
            >
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: a.color, boxShadow: `0 0 6px 1px ${a.color}` }} />
              <span className="mono text-xs font-semibold w-16">{a.id}</span>
              <span className="text-[11px] text-[var(--text-dim)] flex-1">{STATE_LABEL[a.state] ?? a.state}</span>
              <div className="flex items-center gap-1.5">
                <div className="h-1.5 w-12 overflow-hidden rounded bg-[#1e2942]">
                  <div className="h-full rounded" style={{ width: `${a.battery}%`, background: batteryColor }} />
                </div>
                <span className="mono text-[10px] text-[var(--text-dim)] w-8 text-right">{a.battery.toFixed(0)}%</span>
              </div>
            </button>
          );
        })}
        {agents.length === 0 && <div className="py-4 text-center text-xs text-[var(--text-dim)]">Waiting for fleet data…</div>}
      </div>
    </Panel>
  );
}
