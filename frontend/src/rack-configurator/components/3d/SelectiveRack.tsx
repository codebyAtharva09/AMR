import { useMemo } from "react";
import { THEME_PALETTES } from "../../types";
import type { RackConfig } from "../../types";
import { UprightFrame, RackBeam, Decking } from "./RackParts";
import { PalletCargo } from "./PalletCargo";

const BEAM_HEIGHT = 0.1;
const DECK_THICKNESS = 0.04;

export function SelectiveRack({ config }: { config: RackConfig }) {
  const palette = THEME_PALETTES[config.colorTheme];
  const bayWidth = config.bayWidthMm / 1000;
  const depth = config.bayDepthMm / 1000;
  const clearance = config.clearanceHeightMm / 1000;
  const levelHeight = clearance + BEAM_HEIGHT + DECK_THICKNESS;
  const totalHeight = levelHeight * config.tiers + 0.15;

  const levels = useMemo(() => {
    const out: number[] = [];
    for (let t = 0; t < config.tiers; t++) out.push(0.15 + (t + 1) * levelHeight - BEAM_HEIGHT / 2);
    return out;
  }, [config.tiers, levelHeight]);

  return (
    <group>
      {Array.from({ length: config.bays + 1 }).map((_, i) => (
        <UprightFrame key={i} x={i * bayWidth} depth={depth} height={totalHeight} color={palette.upright} maxLoadKg={2500} />
      ))}

      {Array.from({ length: config.bays }).map((_, b) =>
        levels.map((y, t) => (
          <group key={`${b}-${t}`}>
            <RackBeam x0={b * bayWidth} length={bayWidth} z={0} y={y} color={palette.beam} maxLoadKg={2500} />
            <RackBeam x0={b * bayWidth} length={bayWidth} z={depth} y={y} color={palette.beam} maxLoadKg={2500} />
            <Decking x0={b * bayWidth} width={bayWidth} depth={depth} y={y + BEAM_HEIGHT / 2} type={config.decking} />
            {config.cargoEnabled && (
              <>
                <PalletCargo
                  position={[b * bayWidth + bayWidth * 0.28, y + BEAM_HEIGHT / 2 + DECK_THICKNESS, depth * 0.28]}
                  seed={b * 97 + t * 13 + 1}
                  variant={config.cargoVariant}
                  density={config.loadDensity}
                />
                <PalletCargo
                  position={[b * bayWidth + bayWidth * 0.72, y + BEAM_HEIGHT / 2 + DECK_THICKNESS, depth * 0.72]}
                  seed={b * 97 + t * 13 + 2}
                  variant={config.cargoVariant}
                  density={config.loadDensity}
                />
              </>
            )}
          </group>
        ))
      )}
    </group>
  );
}
