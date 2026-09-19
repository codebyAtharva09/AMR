import { useRackConfigStore } from "../../store/useRackConfigStore";
import { computeBom } from "../../utils/bom";
import { GlassPanel } from "./Glass";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white/5 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-white/45">{label}</div>
      <div className="mono text-base font-bold text-white">{value}</div>
    </div>
  );
}

export function StatsHUD() {
  const config = useRackConfigStore((s) => s.config);
  const bom = computeBom(config);

  return (
    <GlassPanel title="Live Structural Stats" className="w-[300px]">
      <div className="grid grid-cols-2 gap-2">
        <Stat label="Weight Capacity" value={`${(bom.totalWeightCapacityKg / 1000).toFixed(1)}t`} />
        <Stat label="Pallet Slots" value={`${bom.totalPalletSlots}`} />
        <Stat label="Footprint" value={`${bom.footprintSqM.toFixed(1)} m²`} />
        <Stat label="Footprint (ft²)" value={`${bom.footprintSqFt.toFixed(0)} ft²`} />
      </div>
      <div className="mt-3 border-t border-white/10 pt-3 text-[11px] text-white/60">
        <div className="mb-1 text-[10px] uppercase tracking-wide text-white/40">Bill of Materials</div>
        <div className="flex justify-between"><span>Upright frames</span><span className="mono text-white/85">{bom.uprightFrames}</span></div>
        <div className="flex justify-between"><span>Beams</span><span className="mono text-white/85">{bom.beams}</span></div>
        <div className="flex justify-between"><span>Deck panels</span><span className="mono text-white/85">{bom.deckPanels}</span></div>
      </div>
    </GlassPanel>
  );
}
