import { useFleetStore } from "../store/useFleetStore";
import { Panel } from "./Panel";

const STATE_LABEL: Record<string, string> = {
  idle: "Idle",
  bidding: "Bidding",
  moving_to_pickup: "Pickup",
  moving_to_dropoff: "Dropoff",
  returning_to_charge: "To Charger",
  charging: "Charging",
  waiting: "Waiting",
  yielding: "Yielding",
};

const STATE_COLOR: Record<string, string> = {
  idle: "#94a3b8",
  bidding: "#fbbf24",
  moving_to_pickup: "#34d399",
  moving_to_dropoff: "#fb923c",
  returning_to_charge: "#c084fc",
  charging: "#c084fc",
  waiting: "#fbbf24",
  yielding: "#fbbf24",
};

const INACTIVE = new Set(["idle", "charging"]);

export function FleetRoster() {
  const snapshot = useFleetStore((s) => s.snapshot);
  const selectedAgentId = useFleetStore((s) => s.selectedAgentId);
  const setSelectedAgentId = useFleetStore((s) => s.setSelectedAgentId);
  const agents = snapshot?.primary.agents ?? [];
  const activeCount = agents.filter((a) => !INACTIVE.has(a.state)).length;

  return (
    <Panel
      title="Fleet Status"
      right={
        <div className="text-right leading-tight">
          <div className="mono text-lg font-bold text-emerald-400">
            {activeCount} <span className="text-[var(--text-dim)]">/ {agents.length}</span>
          </div>
          <div className="text-[10px] text-[var(--text-dim)]">AMRs Active</div>
        </div>
      }
    >
      <div className="flex max-h-64 flex-col gap-0.5 overflow-y-auto pr-1">
        {agents.map((a) => {
          const batteryColor = a.battery > 40 ? "#34d399" : a.battery > 20 ? "#f59e0b" : "#f87171";
          const selected = selectedAgentId === a.id;
          const stateColor = STATE_COLOR[a.state] ?? "#94a3b8";
          return (
            <button
              key={a.id}
              onClick={() => setSelectedAgentId(selected ? null : a.id)}
              className={`flex items-center gap-3 rounded-lg px-2 py-2 text-left transition ${
                selected ? "bg-cyan-500/10 ring-1 ring-cyan-500/40" : "hover:bg-white/[0.03]"
              }`}
            >
              <span className="h-2.5 w-2.5 flex-shrink-0 rounded-full" style={{ background: a.color, boxShadow: `0 0 6px 1px ${a.color}66` }} />
              <span className="mono w-14 flex-shrink-0 text-[13px] font-semibold">{a.id}</span>
              <span className="flex-1 text-[12px] font-medium" style={{ color: stateColor }}>
                {STATE_LABEL[a.state] ?? a.state}
              </span>
              <div className="h-1.5 w-16 flex-shrink-0 overflow-hidden rounded-full bg-white/10">
                <div className="h-full rounded-full transition-all" style={{ width: `${a.battery}%`, background: batteryColor }} />
              </div>
              <span className="mono w-9 flex-shrink-0 text-right text-[12px] text-[var(--text-dim)]">{a.battery.toFixed(0)}%</span>
            </button>
          );
        })}
        {agents.length === 0 && <div className="py-4 text-center text-xs text-[var(--text-dim)]">Waiting for fleet data…</div>}
      </div>
    </Panel>
  );
}
