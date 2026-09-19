import { useMemo, useState } from "react";
import { THEME_PALETTES } from "../../types";
import type { RackConfig, PartInfo } from "../../types";
import { useRackConfigStore } from "../../store/useRackConfigStore";
import type { ThreeEvent } from "@react-three/fiber";

const ARM_LENGTH = 0.9;

function CantileverColumn({ x, height, depth, color }: { x: number; height: number; depth: number; color: string }) {
  const setHovered = useRackConfigStore((s) => s.setHovered);
  const setSelected = useRackConfigStore((s) => s.setSelected);
  const [hovered, setHover] = useState(false);
  const info: PartInfo = { label: "Cantilever Column", detail: `${height.toFixed(1)}m, base ${depth.toFixed(1)}m`, maxLoadKg: 1800 };

  const handlers = {
    onPointerOver: (e: ThreeEvent<PointerEvent>) => {
      e.stopPropagation();
      setHover(true);
      setHovered(info, { x: e.clientX, y: e.clientY });
      document.body.style.cursor = "pointer";
    },
    onPointerOut: (e: ThreeEvent<PointerEvent>) => {
      e.stopPropagation();
      setHover(false);
      setHovered(null);
      document.body.style.cursor = "auto";
    },
    onClick: (e: ThreeEvent<MouseEvent>) => {
      e.stopPropagation();
      setSelected(info);
    },
  };

  return (
    <group position={[x, 0, 0]} {...handlers}>
      <mesh position={[0, 0.08, depth / 2]} castShadow receiveShadow>
        <boxGeometry args={[0.22, 0.16, depth]} />
        <meshStandardMaterial color="#2b2f36" roughness={0.5} metalness={0.6} />
      </mesh>
      <mesh position={[0, height / 2, 0]} castShadow receiveShadow>
        <boxGeometry args={[0.16, height, 0.16]} />
        <meshStandardMaterial color={color} emissive={hovered ? color : "#000"} emissiveIntensity={hovered ? 0.5 : 0} roughness={0.4} metalness={0.55} />
      </mesh>
    </group>
  );
}

function CantileverArm({ x, y, color }: { x: number; y: number; color: string }) {
  return (
    <group position={[x, y, 0]}>
      <mesh position={[0, 0, ARM_LENGTH / 2]} rotation={[Math.PI / 2, 0, 0]} castShadow>
        <boxGeometry args={[0.09, ARM_LENGTH, 0.11]} />
        <meshStandardMaterial color={color} roughness={0.45} metalness={0.5} />
      </mesh>
      <mesh position={[0, 0.05, ARM_LENGTH]} rotation={[Math.PI / 5, 0, 0]}>
        <boxGeometry args={[0.08, 0.16, 0.09]} />
        <meshStandardMaterial color={color} roughness={0.45} metalness={0.5} />
      </mesh>
    </group>
  );
}

function PipeBundle({ x0, length, y }: { x0: number; length: number; y: number }) {
  const offsets = [-0.22, -0.07, 0.08, 0.23];
  return (
    <group position={[x0 + length / 2, y, 0.45]}>
      {offsets.map((dz, i) => (
        <mesh key={i} position={[0, 0, dz]} rotation={[0, 0, Math.PI / 2]} castShadow>
          <cylinderGeometry args={[0.09, 0.09, length * 0.96, 16]} />
          <meshStandardMaterial color={i % 2 === 0 ? "#8b8f96" : "#a3a8b0"} metalness={0.6} roughness={0.35} />
        </mesh>
      ))}
    </group>
  );
}

function LumberStack({ x0, length, y }: { x0: number; length: number; y: number }) {
  return (
    <group position={[x0 + length / 2, y, 0.45]}>
      {Array.from({ length: 4 }).map((_, row) => (
        <group key={row} position={[0, row * 0.09, 0]}>
          {[-0.24, -0.08, 0.08, 0.24].map((dz, i) => (
            <mesh key={i} position={[0, 0, dz]} rotation={[0, 0, Math.PI / 2]} castShadow>
              <boxGeometry args={[0.08, length * 0.96, 0.08]} />
              <meshStandardMaterial color="#b8905c" roughness={0.85} />
            </mesh>
          ))}
        </group>
      ))}
    </group>
  );
}

export function CantileverRack({ config }: { config: RackConfig }) {
  const palette = THEME_PALETTES[config.colorTheme];
  const spacing = config.bayWidthMm / 1000;
  const clearance = config.clearanceHeightMm / 1000;
  const armLevelHeight = clearance + 0.2;
  const totalHeight = armLevelHeight * config.tiers + 0.3;
  const baseDepth = Math.max(config.bayDepthMm / 1000, 0.9);

  const levels = useMemo(() => {
    const out: number[] = [];
    for (let t = 0; t < config.tiers; t++) out.push(0.2 + t * armLevelHeight);
    return out;
  }, [config.tiers, armLevelHeight]);

  const uprightCount = config.bays + 1;

  return (
    <group>
      {Array.from({ length: uprightCount }).map((_, i) => (
        <CantileverColumn key={i} x={i * spacing} height={totalHeight} depth={baseDepth} color={palette.upright} />
      ))}
      {Array.from({ length: uprightCount }).map((_, i) =>
        levels.map((y, t) => <CantileverArm key={`${i}-${t}`} x={i * spacing} y={y} color={palette.beam} />)
      )}
      {config.cargoEnabled &&
        Array.from({ length: config.bays }).map((_, b) =>
          levels.map((y, t) =>
            (b + t) % 2 === 0 ? (
              <PipeBundle key={`${b}-${t}`} x0={b * spacing} length={spacing} y={y + 0.2} />
            ) : (
              <LumberStack key={`${b}-${t}`} x0={b * spacing} length={spacing} y={y + 0.18} />
            )
          )
        )}
    </group>
  );
}
