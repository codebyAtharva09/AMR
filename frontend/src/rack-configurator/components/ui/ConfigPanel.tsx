import { useRackConfigStore } from "../../store/useRackConfigStore";
import type { CameraPreset, CargoVariant, ColorTheme, DeckingType, RackType } from "../../types";
import { GlassPanel, Field, SegButton } from "./Glass";
import { downloadCanvasPng, downloadJson } from "../../utils/exportConfig";

const RACK_TYPES: { value: RackType; label: string }[] = [
  { value: "selective", label: "Selective" },
  { value: "cantilever", label: "Cantilever" },
  { value: "drive_in", label: "Drive-In" },
];

const DECKING_TYPES: { value: DeckingType; label: string }[] = [
  { value: "wire_mesh", label: "Wire Mesh" },
  { value: "flush_steel", label: "Flush Steel" },
  { value: "wood_panel", label: "Wood Panel" },
  { value: "open_frame", label: "Open Frame" },
];

const CARGO_VARIANTS: { value: CargoVariant; label: string }[] = [
  { value: "boxes", label: "Boxes" },
  { value: "shrinkwrap", label: "Shrink-wrap" },
  { value: "drums", label: "Drums" },
  { value: "empty", label: "Empty" },
];

const THEMES: { value: ColorTheme; label: string }[] = [
  { value: "industrial", label: "Industrial" },
  { value: "galvanized", label: "Galvanized" },
  { value: "safety", label: "Safety" },
];

const CAMERA_PRESETS: { value: CameraPreset; label: string }[] = [
  { value: "isometric", label: "Isometric" },
  { value: "front", label: "Front" },
  { value: "top", label: "Top-Down" },
  { value: "side", label: "Side" },
  { value: "walkthrough", label: "Walkthrough" },
];

export function ConfigPanel({ canvasRef }: { canvasRef: React.RefObject<HTMLCanvasElement | null> }) {
  const config = useRackConfigStore((s) => s.config);
  const set = useRackConfigStore((s) => s.set);
  const cameraPreset = useRackConfigStore((s) => s.cameraPreset);
  const setCameraPreset = useRackConfigStore((s) => s.setCameraPreset);

  return (
    <div className="flex max-h-[calc(100vh-1.5rem)] w-[340px] flex-col gap-3 overflow-y-auto pr-1">
      <GlassPanel title="Racking System">
        <div className="grid grid-cols-3 gap-1.5">
          {RACK_TYPES.map((r) => (
            <SegButton key={r.value} active={config.rackType === r.value} onClick={() => set("rackType", r.value)}>
              {r.label}
            </SegButton>
          ))}
        </div>
      </GlassPanel>

      <GlassPanel title="Bay & Tier Layout">
        <Field label="Bay count" hint={`${config.bays} bays`}>
          <input type="range" min={1} max={6} value={config.bays} onChange={(e) => set("bays", Number(e.target.value))} className="w-full accent-cyan-400" />
        </Field>
        <Field label="Tier / level count" hint={`${config.tiers} levels`}>
          <input type="range" min={2} max={6} value={config.tiers} onChange={(e) => set("tiers", Number(e.target.value))} className="w-full accent-cyan-400" />
        </Field>
        <Field label="Bay width" hint={`${config.bayWidthMm}mm / ${(config.bayWidthMm / 304.8).toFixed(1)}ft`}>
          <input type="range" min={1800} max={3600} step={50} value={config.bayWidthMm} onChange={(e) => set("bayWidthMm", Number(e.target.value))} className="w-full accent-cyan-400" />
        </Field>
        <Field label="Bay depth" hint={`${config.bayDepthMm}mm / ${(config.bayDepthMm / 304.8).toFixed(1)}ft`}>
          <input type="range" min={800} max={1500} step={25} value={config.bayDepthMm} onChange={(e) => set("bayDepthMm", Number(e.target.value))} className="w-full accent-cyan-400" />
        </Field>
        <Field label="Clearance height" hint={`${config.clearanceHeightMm}mm / ${(config.clearanceHeightMm / 304.8).toFixed(1)}ft`}>
          <input type="range" min={900} max={2400} step={50} value={config.clearanceHeightMm} onChange={(e) => set("clearanceHeightMm", Number(e.target.value))} className="w-full accent-cyan-400" />
        </Field>
      </GlassPanel>

      {config.rackType !== "cantilever" && (
        <GlassPanel title="Shelf Decking">
          <div className="grid grid-cols-2 gap-1.5">
            {DECKING_TYPES.map((d) => (
              <SegButton key={d.value} active={config.decking === d.value} onClick={() => set("decking", d.value)}>
                {d.label}
              </SegButton>
            ))}
          </div>
        </GlassPanel>
      )}

      <GlassPanel title="Cargo">
        <Field label="Load cargo">
          <button
            onClick={() => set("cargoEnabled", !config.cargoEnabled)}
            className={`w-full rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
              config.cargoEnabled ? "bg-emerald-500 text-slate-900" : "bg-white/10 text-white/60"
            }`}
          >
            {config.cargoEnabled ? "Cargo ON" : "Cargo OFF"}
          </button>
        </Field>
        {config.cargoEnabled && (
          <>
            <Field label="Load density" hint={`${config.loadDensity}%`}>
              <input type="range" min={0} max={100} value={config.loadDensity} onChange={(e) => set("loadDensity", Number(e.target.value))} className="w-full accent-emerald-400" />
            </Field>
            <Field label="Cargo type">
              <div className="grid grid-cols-2 gap-1.5">
                {CARGO_VARIANTS.map((c) => (
                  <SegButton key={c.value} active={config.cargoVariant === c.value} onClick={() => set("cargoVariant", c.value)}>
                    {c.label}
                  </SegButton>
                ))}
              </div>
            </Field>
          </>
        )}
      </GlassPanel>

      <GlassPanel title="Color Theme">
        <div className="grid grid-cols-3 gap-1.5">
          {THEMES.map((t) => (
            <SegButton key={t.value} active={config.colorTheme === t.value} onClick={() => set("colorTheme", t.value)}>
              {t.label}
            </SegButton>
          ))}
        </div>
      </GlassPanel>

      <GlassPanel title="Camera View">
        <div className="grid grid-cols-2 gap-1.5">
          {CAMERA_PRESETS.map((c) => (
            <SegButton key={c.value} active={cameraPreset === c.value} onClick={() => setCameraPreset(c.value)}>
              {c.label}
            </SegButton>
          ))}
        </div>
      </GlassPanel>

      <div className="flex gap-2">
        <button
          onClick={() => downloadJson(config)}
          className="flex-1 rounded-lg bg-white/10 py-2 text-xs font-semibold text-white/80 transition hover:bg-white/15"
        >
          Export JSON
        </button>
        <button
          onClick={() => canvasRef.current && downloadCanvasPng(canvasRef.current)}
          className="flex-1 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 py-2 text-xs font-semibold text-slate-900 transition hover:brightness-110"
        >
          Export PNG
        </button>
      </div>
    </div>
  );
}
