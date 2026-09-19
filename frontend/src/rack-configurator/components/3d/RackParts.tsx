import { useMemo, useState } from "react";
import type { ThreeEvent } from "@react-three/fiber";
import { punchedSteelTexture } from "../../utils/textures";
import { useRackConfigStore } from "../../store/useRackConfigStore";
import type { PartInfo } from "../../types";

function useHoverSelect(info: PartInfo) {
  const setHovered = useRackConfigStore((s) => s.setHovered);
  const setSelected = useRackConfigStore((s) => s.setSelected);
  const [hovered, setLocalHover] = useState(false);

  const onPointerOver = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    setLocalHover(true);
    setHovered(info, { x: e.clientX, y: e.clientY });
    document.body.style.cursor = "pointer";
  };
  const onPointerMove = (e: ThreeEvent<PointerEvent>) => {
    if (hovered) setHovered(info, { x: e.clientX, y: e.clientY });
  };
  const onPointerOut = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    setLocalHover(false);
    setHovered(null);
    document.body.style.cursor = "auto";
  };
  const onClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    setSelected(info);
  };

  return { hovered, onPointerOver, onPointerMove, onPointerOut, onClick };
}

/** A single ladder-style upright frame: two vertical columns (front/back) laced
 * with horizontal + diagonal cross-bracing, standing on floor baseplates. */
export function UprightFrame({
  x,
  depth,
  height,
  color,
  maxLoadKg,
}: {
  x: number;
  depth: number;
  height: number;
  color: string;
  maxLoadKg: number;
}) {
  const texture = useMemo(() => punchedSteelTexture(color), [color]);
  const info: PartInfo = { label: "Upright Frame", detail: `${height.toFixed(1)}m tall, ${depth.toFixed(2)}m deep`, maxLoadKg };
  const { hovered, ...handlers } = useHoverSelect(info);

  const braceCount = Math.max(2, Math.floor(height / 0.9));
  const braces = useMemo(() => {
    const out: { y: number; diagonal: boolean }[] = [];
    for (let i = 0; i < braceCount; i++) {
      const y = (i + 0.5) * (height / braceCount);
      out.push({ y, diagonal: i % 2 === 0 });
    }
    return out;
  }, [braceCount, height]);

  const columnMat = (
    <meshStandardMaterial map={texture} emissive={hovered ? color : "#000000"} emissiveIntensity={hovered ? 0.5 : 0} roughness={0.55} metalness={0.35} />
  );

  return (
    <group position={[x, 0, 0]} {...handlers}>
      {[0, depth].map((z, i) => (
        <group key={i}>
          <mesh position={[0, height / 2, z]} castShadow receiveShadow>
            <boxGeometry args={[0.09, height, 0.09]} />
            {columnMat}
          </mesh>
          <mesh position={[0, 0.015, z]}>
            <boxGeometry args={[0.22, 0.03, 0.22]} />
            <meshStandardMaterial color="#2b2f36" roughness={0.7} />
          </mesh>
        </group>
      ))}
      {braces.map((b, i) =>
        b.diagonal ? (
          <mesh key={i} position={[0, b.y, depth / 2]} rotation={[Math.atan2(depth, height / braceCount) - Math.PI / 2, 0, 0]}>
            <boxGeometry args={[0.035, Math.hypot(depth, height / braceCount) * 1.05, 0.035]} />
            <meshStandardMaterial color={color} roughness={0.6} metalness={0.3} />
          </mesh>
        ) : (
          <mesh key={i} position={[0, b.y, depth / 2]} rotation={[Math.PI / 2, 0, 0]}>
            <boxGeometry args={[0.035, depth, 0.035]} />
            <meshStandardMaterial color={color} roughness={0.6} metalness={0.3} />
          </mesh>
        )
      )}
    </group>
  );
}

/** A single load beam spanning between two upright frames at one tier, with
 * step-connector end plates and a safety pin. */
export function RackBeam({
  x0,
  length,
  z,
  y,
  color,
  maxLoadKg,
}: {
  x0: number;
  length: number;
  z: number;
  y: number;
  color: string;
  maxLoadKg: number;
}) {
  const info: PartInfo = { label: "Step Beam", detail: `${(length * 1000).toFixed(0)}mm span`, maxLoadKg };
  const { hovered, ...handlers } = useHoverSelect(info);

  return (
    <group position={[x0 + length / 2, y, z]} {...handlers}>
      <mesh castShadow receiveShadow>
        <boxGeometry args={[length, 0.1, 0.06]} />
        <meshStandardMaterial color={color} emissive={hovered ? color : "#000"} emissiveIntensity={hovered ? 0.6 : 0} roughness={0.4} metalness={0.5} />
      </mesh>
      {[-length / 2, length / 2].map((dx, i) => (
        <group key={i} position={[dx, 0, 0]}>
          <mesh position={[dx < 0 ? 0.04 : -0.04, 0, 0]}>
            <boxGeometry args={[0.08, 0.13, 0.09]} />
            <meshStandardMaterial color="#20242b" roughness={0.5} metalness={0.6} />
          </mesh>
          <mesh position={[dx < 0 ? 0.09 : -0.09, 0.02, 0]} rotation={[0, 0, Math.PI / 2]}>
            <cylinderGeometry args={[0.012, 0.012, 0.06, 8]} />
            <meshStandardMaterial color="#e5e7eb" metalness={0.8} roughness={0.3} />
          </mesh>
        </group>
      ))}
    </group>
  );
}

/** Decking resting on a pair of beams: wire mesh, flush steel plate, wood
 * planks, or nothing (open frame). */
export function Decking({
  x0,
  width,
  depth,
  y,
  type,
}: {
  x0: number;
  width: number;
  depth: number;
  y: number;
  type: "wire_mesh" | "flush_steel" | "wood_panel" | "open_frame";
}) {
  if (type === "open_frame") return null;

  if (type === "flush_steel") {
    return (
      <mesh position={[x0 + width / 2, y + 0.015, depth / 2]} receiveShadow>
        <boxGeometry args={[width * 0.97, 0.02, depth * 0.95]} />
        <meshStandardMaterial color="#9aa3ad" roughness={0.4} metalness={0.6} />
      </mesh>
    );
  }

  if (type === "wood_panel") {
    const planks = 3;
    return (
      <group position={[x0 + width / 2, y + 0.02, depth / 2]}>
        {Array.from({ length: planks }).map((_, i) => (
          <mesh key={i} position={[0, 0, (i - (planks - 1) / 2) * (depth / planks)]} receiveShadow castShadow>
            <boxGeometry args={[width * 0.96, 0.025, depth / planks - 0.02]} />
            <meshStandardMaterial color="#b8905c" roughness={0.85} />
          </mesh>
        ))}
      </group>
    );
  }

  // wire_mesh: a real 3D rod grid, not a flat texture
  const longRods = 6;
  const crossRods = 3;
  return (
    <group position={[x0 + width / 2, y + 0.02, depth / 2]}>
      {Array.from({ length: longRods }).map((_, i) => (
        <mesh key={`l${i}`} position={[(i / (longRods - 1) - 0.5) * width * 0.94, 0, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.008, 0.008, depth * 0.95, 6]} />
          <meshStandardMaterial color="#c7ccd3" metalness={0.6} roughness={0.4} />
        </mesh>
      ))}
      {Array.from({ length: crossRods }).map((_, i) => (
        <mesh key={`c${i}`} position={[0, 0.002, (i / (crossRods - 1) - 0.5) * depth * 0.9]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.008, 0.008, width * 0.94, 6]} />
          <meshStandardMaterial color="#c7ccd3" metalness={0.6} roughness={0.4} />
        </mesh>
      ))}
    </group>
  );
}
