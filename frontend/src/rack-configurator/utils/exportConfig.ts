import type { RackConfig } from "../types";

export function downloadJson(config: RackConfig) {
  const blob = new Blob([JSON.stringify(config, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `rack-config-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export function downloadCanvasPng(canvas: HTMLCanvasElement) {
  const url = canvas.toDataURL("image/png");
  const a = document.createElement("a");
  a.href = url;
  a.download = `rack-render-${Date.now()}.png`;
  a.click();
}
