import { useState } from "react";
import { api } from "../api";
import { useFleetStore } from "../store/useFleetStore";
import { Panel } from "./Panel";

const CHOKE_POINTS: { label: string; row: number; col: number }[] = [
  { label: "Aisle 4 (mid)", row: 6, col: 4 },
  { label: "Aisle 12 (mid)", row: 6, col: 12 },
  { label: "Aisle 20 (mid)", row: 6, col: 20 },
  { label: "Top junction", row: 0, col: 12 },
  { label: "Bottom junction", row: 10, col: 12 },
];

export function ControlPanel() {
  const snapshot = useFleetStore((s) => s.snapshot);
  const mode = snapshot?.primary.mode ?? "decentralized";
  const fleetSize = snapshot?.primary.agents.length ?? 0;
  const [blocked, setBlocked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  const toggleBlock = async (row: number, col: number) => {
    const key = `${row},${col}`;
    setBusy(true);
    if (blocked.has(key)) {
      await api.unblockAisle(row, col);
      setBlocked((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    } else {
      await api.blockAisle(row, col);
      setBlocked((prev) => new Set(prev).add(key));
    }
    setBusy(false);
  };

  const setMode = async (m: "decentralized" | "stop_and_wait") => {
    setBusy(true);
    await api.setMode(m);
    setBusy(false);
  };

  const resetFleet = async () => {
    setBusy(true);
    await api.reset();
    setBlocked(new Set());
    setBusy(false);
  };

  return (
    <Panel title="Fleet Control">
      <div className="mb-4">
        <div className="mb-1.5 text-[10px] uppercase text-[var(--text-dim)]">Coordination mode</div>
        <div className="flex rounded-lg border border-[var(--border-soft)] bg-[#0a0f1c] p-1">
          <button
            disabled={busy}
            onClick={() => setMode("decentralized")}
            className={`flex-1 rounded-md py-1.5 text-xs font-semibold transition ${
              mode === "decentralized" ? "bg-cyan-500 text-slate-900 shadow shadow-cyan-500/30" : "text-[var(--text-dim)] hover:text-white"
            }`}
          >
            Decentralized ORCA
          </button>
          <button
            disabled={busy}
            onClick={() => setMode("stop_and_wait")}
            className={`flex-1 rounded-md py-1.5 text-xs font-semibold transition ${
              mode === "stop_and_wait" ? "bg-amber-500 text-slate-900 shadow shadow-amber-500/30" : "text-[var(--text-dim)] hover:text-white"
            }`}
          >
            Stop-and-Wait
          </button>
        </div>
      </div>

      <div className="mb-4">
        <div className="mb-1.5 text-[10px] uppercase text-[var(--text-dim)]">Inject aisle blockage</div>
        <div className="grid grid-cols-2 gap-2">
          {CHOKE_POINTS.map((c) => {
            const key = `${c.row},${c.col}`;
            const active = blocked.has(key);
            return (
              <button
                key={key}
                disabled={busy}
                onClick={() => toggleBlock(c.row, c.col)}
                className={`rounded-md border px-2 py-1.5 text-[11px] font-medium transition ${
                  active
                    ? "border-red-500/60 bg-red-500/15 text-red-300"
                    : "border-[var(--border-soft)] bg-[#0a0f1c] text-[var(--text-dim)] hover:border-red-500/40 hover:text-red-300"
                }`}
              >
                {active ? "Clear " : "Block "}
                {c.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="mb-3">
        <div className="mb-1.5 flex items-center justify-between text-[10px] uppercase text-[var(--text-dim)]">
          <span>Fleet size</span>
          <span className="mono text-[var(--text-primary)]">{fleetSize} units</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              await api.addAgent();
              setBusy(false);
            }}
            className="rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 py-2 text-xs font-semibold text-slate-900 shadow-lg shadow-cyan-500/20 transition hover:brightness-110 disabled:opacity-50"
          >
            + Deploy Robot
          </button>
          <button
            disabled={busy || fleetSize <= 1}
            onClick={async () => {
              setBusy(true);
              await api.removeAgent();
              setBusy(false);
            }}
            className="rounded-md border border-[var(--border-soft)] bg-[#0a0f1c] py-2 text-xs font-semibold text-[var(--text-dim)] transition hover:border-red-500/40 hover:text-red-300 disabled:opacity-40"
          >
            − Remove Robot
          </button>
        </div>
      </div>

      <button
        disabled={busy}
        onClick={resetFleet}
        className="w-full rounded-md border border-[var(--border-soft)] bg-[#0a0f1c] py-2 text-xs font-semibold text-[var(--text-dim)] transition hover:border-amber-500/40 hover:text-amber-300 disabled:opacity-50"
      >
        Reset Fleet (back to 10 robots)
      </button>
    </Panel>
  );
}
