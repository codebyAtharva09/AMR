import { useRackConfigStore } from "../../store/useRackConfigStore";

export function HoverTooltip() {
  const part = useRackConfigStore((s) => s.hoveredPart);
  const pos = useRackConfigStore((s) => s.hoverScreenPos);
  if (!part || !pos) return null;

  return (
    <div
      className="pointer-events-none fixed z-50 rounded-lg border border-white/15 bg-slate-900/95 px-3 py-2 text-xs shadow-xl"
      style={{ left: pos.x + 14, top: pos.y + 14 }}
    >
      <div className="font-semibold text-cyan-300">{part.label}</div>
      <div className="text-white/60">{part.detail}</div>
      {part.maxLoadKg != null && <div className="mt-0.5 text-white/45">Max load: {part.maxLoadKg.toLocaleString()} kg</div>}
    </div>
  );
}
