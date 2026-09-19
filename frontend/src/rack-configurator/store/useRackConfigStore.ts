import { create } from "zustand";
import { DEFAULT_CONFIG } from "../types";
import type { CameraPreset, PartInfo, RackConfig } from "../types";

interface RackConfigStore {
  config: RackConfig;
  hoveredPart: PartInfo | null;
  hoverScreenPos: { x: number; y: number } | null;
  selectedPart: PartInfo | null;
  cameraPreset: CameraPreset;
  set: <K extends keyof RackConfig>(key: K, value: RackConfig[K]) => void;
  setHovered: (part: PartInfo | null, pos?: { x: number; y: number } | null) => void;
  setSelected: (part: PartInfo | null) => void;
  setCameraPreset: (preset: CameraPreset) => void;
  reset: () => void;
}

export const useRackConfigStore = create<RackConfigStore>((set) => ({
  config: { ...DEFAULT_CONFIG },
  hoveredPart: null,
  hoverScreenPos: null,
  selectedPart: null,
  cameraPreset: "isometric",
  set: (key, value) => set((s) => ({ config: { ...s.config, [key]: value } })),
  setHovered: (part, pos) => set({ hoveredPart: part, hoverScreenPos: pos ?? null }),
  setSelected: (part) => set({ selectedPart: part }),
  setCameraPreset: (preset) => set({ cameraPreset: preset }),
  reset: () => set({ config: { ...DEFAULT_CONFIG } }),
}));
