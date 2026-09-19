import { useMemo } from "react";
import { THEME_PALETTES } from "../../types";
import type { RackConfig } from "../../types";
import { UprightFrame, RackBeam } from "./RackParts";
import { PalletCargo } from "./PalletCargo";

const NESTED_POSITIONS = 3;
const RAIL_HEIGHT_OFFSET = 0.12;

export function DriveInRack({ config }: { config: RackConfig }) {
  const palette = THEME_PALETTES[config.colorTheme];
  const bayWidth = config.bayWidthMm / 1000;
  const positionDepth = Math.max(config.bayDepthMm / 1000, 1.0);
  const laneDepth = positionDepth * NESTED_POSITIONS;
  const clearance = config.clearanceHeightMm / 1000;
  const levelHeight = clearance + 0.15;
  const totalHeight = levelHeight * config.tiers + 0.2;

  const levels = useMemo(() => {
    const out: number[] = [];
    for (let t = 0; t < config.tiers; t++) out.push(0.2 + (t + 1) * levelHeight - RAIL_HEIGHT_OFFSET);
    return out;
  }, [config.tiers, levelHeight]);

  const columnLines = config.bays + 1;

  return (
    <group>
      {/* Front and rear structural frames per column line (drive-in bracing) */}
      {Array.from({ length: columnLines }).map((_, i) => (
        <UprightFrame key={`front-${i}`} x={i * bayWidth} depth={0.12} height={totalHeight} color={palette.upright} maxLoadKg={2200} />
      ))}
      {Array.from({ length: columnLines }).map((_, i) => (
        <group key={`rear-${i}`} position={[0, 0, laneDepth - 0.12]}>
          <UprightFrame x={i * bayWidth} depth={0.12} height={totalHeight} color={palette.upright} maxLoadKg={2200} />
        </group>
      ))}

      {/* Continuous rails along the lane depth, one per column line, per tier */}
      {Array.from({ length: columnLines }).map((_, i) =>
        levels.map((y, t) => (
          <group key={`${i}-${t}`} position={[i * bayWidth, 0, 0]} rotation={[0, -Math.PI / 2, 0]}>
            <RackBeam x0={0} length={laneDepth} z={0} y={y} color={palette.beam} maxLoadKg={2200} />
          </group>
        ))
      )}

      {/* Top bracing frame across the width, front and back */}
      {[0.1, laneDepth - 0.1].map((z, i) => (
        <mesh key={i} position={[(columnLines - 1) * bayWidth * 0.5, totalHeight, z]} castShadow>
          <boxGeometry args={[(columnLines - 1) * bayWidth + 0.15, 0.08, 0.08]} />
          <meshStandardMaterial color={palette.connector} roughness={0.5} metalness={0.4} />
        </mesh>
      ))}

      {/* Floor guide rails for the forklift lane */}
      {Array.from({ length: config.bays }).map((_, b) =>
        [0.25, -0.25].map((dx, i) => (
          <mesh key={`${b}-${i}`} position={[b * bayWidth + bayWidth / 2 + dx, 0.025, laneDepth / 2]} castShadow>
            <boxGeometry args={[0.1, 0.05, laneDepth * 0.98]} />
            <meshStandardMaterial color="#2b2f36" roughness={0.6} metalness={0.4} />
          </mesh>
        ))
      )}

      {/* Nested pallets per lane per tier */}
      {config.cargoEnabled &&
        Array.from({ length: config.bays }).map((_, b) =>
          levels.map((y, t) =>
            Array.from({ length: NESTED_POSITIONS }).map((_, p) => (
              <PalletCargo
                key={`${b}-${t}-${p}`}
                position={[b * bayWidth + bayWidth / 2, y + RAIL_HEIGHT_OFFSET, p * positionDepth + positionDepth / 2]}
                seed={b * 191 + t * 17 + p * 5 + 3}
                variant={config.cargoVariant}
                density={config.loadDensity}
              />
            ))
          )
        )}
    </group>
  );
}
