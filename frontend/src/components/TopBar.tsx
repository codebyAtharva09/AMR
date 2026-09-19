import { useFleetStore } from "../store/useFleetStore";
import { useMeshHealth } from "../hooks/useMeshHealth";

const HEALTH_STYLE = {
  online: { dot: "bg-emerald-400 shadow-[0_0_8px_2px_rgba(52,211,153,0.6)]", label: "MESH ONLINE" },
  degraded: { dot: "bg-amber-400 shadow-[0_0_8px_2px_rgba(251,191,36,0.6)]", label: "MESH DEGRADED" },
  offline: { dot: "bg-red-500", label: "DISCONNECTED" },
} as const;

export function TopBar({ onOpenRackStudio }: { onOpenRackStudio?: () => void }) {
  const snapshot = useFleetStore((s) => s.snapshot);
  const health = useMeshHealth();
  const mode = snapshot?.primary.mode ?? "decentralized";
  const tick = snapshot?.primary.tick ?? 0;

  return (
    <div className="flex items-center justify-between border-b border-[var(--border-soft)] bg-[var(--bg-panel)]/80 px-5 py-3 backdrop-blur">
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-400 to-blue-600 font-bold text-slate-900 shadow-lg shadow-cyan-500/20">
          F
        </div>
        <div>
          <div className="text-sm font-bold tracking-wide">FleetOS</div>
          <div className="text-[11px] text-[var(--text-dim)] -mt-0.5">Decentralized AMR Coordination · Edge Simulation</div>
        </div>
      </div>

      <div className="flex items-center gap-5 text-xs">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${HEALTH_STYLE[health].dot}`} />
          <span className="mono text-[var(--text-dim)]">{HEALTH_STYLE[health].label}</span>
        </div>
        <div className="mono text-[var(--text-dim)]">
          TICK <span className="text-[var(--text-primary)]">{tick.toString().padStart(5, "0")}</span>
        </div>
        <div
          className={`rounded-full border px-3 py-1 font-semibold mono uppercase ${
            mode === "decentralized"
              ? "border-cyan-500/40 bg-cyan-500/10 text-cyan-300"
              : "border-amber-500/40 bg-amber-500/10 text-amber-300"
          }`}
        >
          {mode === "decentralized" ? "ORCA · Decentralized" : "Stop-and-Wait"}
        </div>
        {onOpenRackStudio && (
          <button
            onClick={onOpenRackStudio}
            className="rounded-full border border-white/15 bg-white/5 px-3 py-1 font-semibold text-[var(--text-dim)] transition hover:border-cyan-500/40 hover:text-cyan-300"
          >
            Rack Studio
          </button>
        )}
      </div>
    </div>
  );
}
