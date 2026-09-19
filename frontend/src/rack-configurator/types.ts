export type RackType = "selective" | "cantilever" | "drive_in";
export type DeckingType = "wire_mesh" | "flush_steel" | "wood_panel" | "open_frame";
export type ColorTheme = "industrial" | "galvanized" | "safety";
export type CargoVariant = "boxes" | "shrinkwrap" | "drums" | "empty";
export type CameraPreset = "isometric" | "front" | "top" | "side" | "walkthrough";

export interface RackConfig {
  rackType: RackType;
  bays: number;
  tiers: number;
  bayWidthMm: number;
  bayDepthMm: number;
  clearanceHeightMm: number;
  decking: DeckingType;
  cargoEnabled: boolean;
  loadDensity: number; // 0-100
  cargoVariant: CargoVariant;
  colorTheme: ColorTheme;
}

export const DEFAULT_CONFIG: RackConfig = {
  rackType: "selective",
  bays: 3,
  tiers: 4,
  bayWidthMm: 2700,
  bayDepthMm: 1100,
  clearanceHeightMm: 1500,
  decking: "wire_mesh",
  cargoEnabled: true,
  loadDensity: 70,
  cargoVariant: "boxes",
  colorTheme: "industrial",
};

export interface ThemePalette {
  upright: string;
  brace: string;
  beam: string;
  connector: string;
}

export const THEME_PALETTES: Record<ColorTheme, ThemePalette> = {
  industrial: { upright: "#e8631c", brace: "#c94f14", beam: "#1e6f8f", connector: "#f0f0f0" },
  galvanized: { upright: "#aab3bd", brace: "#8b95a1", beam: "#7f8c99", connector: "#e8ecef" },
  safety: { upright: "#f7c600", brace: "#d9ac00", beam: "#1f2937", connector: "#ff3b30" },
};

export interface PartInfo {
  label: string;
  detail: string;
  maxLoadKg?: number;
}
