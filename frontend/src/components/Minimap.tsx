import { useCallback, useEffect, useRef } from "react";
import { useFleetStore } from "../store/useFleetStore";

const MAP_W = 216;
const MAP_H = 152;
const PAD = 10;

/** Fixed top-down overview in the corner of the 3D view: rack blocks,
 * stations, and every agent's live position/heading - click a dot to select
 * (and follow) that robot, same as clicking it in the 3D scene or roster. */
export function Minimap({ width, depth, cell }: { width: number; depth: number; cell: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const layout = useFleetStore((s) => s.layout);
  const snapshot = useFleetStore((s) => s.snapshot);
  const selectedAgentId = useFleetStore((s) => s.selectedAgentId);
  const setSelectedAgentId = useFleetStore((s) => s.setSelectedAgentId);

  // World (x,z in scene units) -> minimap pixel space, letterboxed to keep aspect.
  const toPixel = useCallback(
    (x: number, z: number) => {
      const usableW = MAP_W - PAD * 2;
      const usableH = MAP_H - PAD * 2;
      const scale = Math.min(usableW / Math.max(width, 1), usableH / Math.max(depth, 1));
      const offX = PAD + (usableW - width * scale) / 2;
      const offY = PAD + (usableH - depth * scale) / 2;
      return [offX + x * scale, offY + z * scale] as const;
    },
    [width, depth]
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, MAP_W, MAP_H);
    ctx.fillStyle = "rgba(10,14,22,0.55)";
    ctx.fillRect(0, 0, MAP_W, MAP_H);

    if (!layout) return;

    // floor footprint
    const [fx0, fy0] = toPixel(-cell / 2, -cell / 2);
    const [fx1, fy1] = toPixel(width - cell / 2, depth - cell / 2);
    ctx.strokeStyle = "rgba(255,255,255,0.15)";
    ctx.lineWidth = 1;
    ctx.strokeRect(fx0, fy0, fx1 - fx0, fy1 - fy0);

    // racks
    ctx.fillStyle = "rgba(212,66,13,0.55)";
    for (const r of layout.racks) {
      const [x, y] = toPixel(r.col * cell - cell / 2, r.row * cell - cell / 2);
      ctx.fillRect(x, y, cell * (fx1 - fx0) / Math.max(width, 1) || 3, cell * (fy1 - fy0) / Math.max(depth, 1) || 3);
    }

    const dot = (pts: [number, number][], color: string, r: number) => {
      ctx.fillStyle = color;
      for (const [row, col] of pts) {
        const [x, y] = toPixel(col * cell, row * cell);
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fill();
      }
    };
    dot(layout.pickup_stations, "#22d3ee", 2.5);
    dot(layout.dropoff_stations, "#34d399", 2.5);
    dot(layout.charging_stations, "#f59e0b", 2.5);

    const agents = snapshot?.primary.agents ?? [];
    for (const a of agents) {
      const [x, y] = toPixel(a.x, a.y);
      const selected = a.id === selectedAgentId;
      if (selected) {
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.fillStyle = a.color;
      ctx.beginPath();
      ctx.arc(x, y, selected ? 3.2 : 2.6, 0, Math.PI * 2);
      ctx.fill();
      const heading = Math.atan2(a.vx, a.vy);
      if (Math.hypot(a.vx, a.vy) > 0.05) {
        ctx.strokeStyle = a.color;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x + Math.sin(heading) * 6, y + Math.cos(heading) * 6);
        ctx.stroke();
      }
    }
  }, [layout, snapshot, selectedAgentId, toPixel, cell, width, depth]);

  const handleClick: React.MouseEventHandler<HTMLCanvasElement> = (e) => {
    const agents = snapshot?.primary.agents ?? [];
    if (agents.length === 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * MAP_W;
    const py = ((e.clientY - rect.top) / rect.height) * MAP_H;

    let closest: string | null = null;
    let bestDist = Infinity;
    for (const a of agents) {
      const [x, y] = toPixel(a.x, a.y);
      const d = Math.hypot(x - px, y - py);
      if (d < bestDist) {
        bestDist = d;
        closest = a.id;
      }
    }
    if (closest && bestDist < 14) {
      setSelectedAgentId(selectedAgentId === closest ? null : closest);
    }
  };

  return (
    <div className="pointer-events-auto absolute right-4 top-4 overflow-hidden rounded-lg border border-white/10 bg-black/30 shadow-lg backdrop-blur-sm">
      <div className="border-b border-white/10 px-2 py-1 text-[9px] font-semibold uppercase tracking-wider text-white/50">
        Overview
      </div>
      <canvas
        ref={canvasRef}
        width={MAP_W}
        height={MAP_H}
        onClick={handleClick}
        className="block cursor-pointer"
        style={{ width: MAP_W, height: MAP_H }}
      />
    </div>
  );
}
