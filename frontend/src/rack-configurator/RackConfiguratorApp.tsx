import { useRef } from "react";
import { RackScene } from "./components/3d/RackScene";
import { ConfigPanel } from "./components/ui/ConfigPanel";
import { StatsHUD } from "./components/ui/StatsHUD";
import { HoverTooltip } from "./components/ui/HoverTooltip";
import { InspectModal } from "./components/ui/InspectModal";

export function RackConfiguratorApp({ onClose }: { onClose?: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  return (
    <div className="fixed inset-0 z-30 bg-[#0b0e13]">
      <div className="absolute inset-0">
        <RackScene ref={canvasRef} />
      </div>

      <div className="pointer-events-none absolute left-4 top-4 right-4 flex items-start justify-between">
        <div className="pointer-events-auto rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 backdrop-blur-xl">
          <div className="text-sm font-bold text-white">Rack Studio</div>
          <div className="text-[11px] text-white/50">Procedural Warehouse Racking Configurator</div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="pointer-events-auto rounded-lg border border-white/15 bg-white/10 px-3 py-2 text-xs font-semibold text-white/80 backdrop-blur-xl transition hover:bg-white/20"
          >
            ← Back to Fleet
          </button>
        )}
      </div>

      <div className="absolute right-4 top-20 bottom-4">
        <ConfigPanel canvasRef={canvasRef} />
      </div>

      <div className="absolute bottom-4 left-4">
        <StatsHUD />
      </div>

      <HoverTooltip />
      <InspectModal />
    </div>
  );
}
