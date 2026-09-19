import { useRackConfigStore } from "../../store/useRackConfigStore";

export function InspectModal() {
  const part = useRackConfigStore((s) => s.selectedPart);
  const setSelected = useRackConfigStore((s) => s.setSelected);
  if (!part) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/50" onClick={() => setSelected(null)}>
      <div
        className="w-[360px] rounded-2xl border border-white/15 bg-slate-900/95 p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-white/40">Structural Breakdown</div>
            <div className="text-lg font-bold text-white">{part.label}</div>
          </div>
          <button onClick={() => setSelected(null)} className="text-white/40 hover:text-white">
            ✕
          </button>
        </div>
        <div className="space-y-2 text-sm text-white/70">
          <div className="flex justify-between border-b border-white/10 pb-2">
            <span>Spec</span>
            <span className="mono text-white/90">{part.detail}</span>
          </div>
          {part.maxLoadKg != null && (
            <div className="flex justify-between border-b border-white/10 pb-2">
              <span>Max Load</span>
              <span className="mono text-white/90">{part.maxLoadKg.toLocaleString()} kg</span>
            </div>
          )}
          <p className="pt-1 text-xs text-white/40">Click elsewhere to close. Hover any structural member for a quick readout without opening this panel.</p>
        </div>
      </div>
    </div>
  );
}
