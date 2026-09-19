import { useMemo } from "react";
import * as THREE from "three";
import type { CargoVariant } from "../../types";
import { cardboardTexture } from "../../utils/textures";

function seededRandom(seed: number) {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

const DRUM_COLORS = ["#1e40af", "#b91c1c", "#0f766e", "#374151"];

export function PalletCargo({
  position,
  seed,
  variant,
  density,
}: {
  position: [number, number, number];
  seed: number;
  variant: CargoVariant;
  density: number;
}) {
  const rand = useMemo(() => seededRandom(seed + 1), [seed]);
  const show = rand() * 100 < Math.max(20, density);

  const woodMat = useMemo(
    () => new THREE.MeshStandardMaterial({ color: "#c8a165", roughness: 0.85 }),
    []
  );

  const boxes = useMemo(() => {
    if (variant !== "boxes" || !show) return [];
    const count = 4 + Math.floor(rand() * 4);
    const out: { pos: [number, number, number]; size: [number, number, number]; shade: number }[] = [];
    let y = 0.14;
    let placed = 0;
    let row = 0;
    while (placed < count) {
      const sx = 0.32 + rand() * 0.18;
      const sy = 0.26 + rand() * 0.14;
      const sz = 0.32 + rand() * 0.18;
      const cols = 2;
      const cx = (placed % cols) - 0.5;
      const cz = row % 2 === 0 ? -0.22 : 0.22;
      out.push({ pos: [cx * 0.5, y + sy / 2, cz], size: [sx, sy, sz], shade: Math.floor(rand() * 3) });
      placed++;
      if (placed % cols === 0) {
        y += sy;
        row++;
      }
    }
    return out;
  }, [variant, show, rand]);

  if (!show) {
    return <PalletBase position={position} woodMat={woodMat} />;
  }

  return (
    <group position={position}>
      <PalletBase position={[0, 0, 0]} woodMat={woodMat} />
      {variant === "boxes" &&
        boxes.map((b, i) => (
          <mesh key={i} position={b.pos} castShadow receiveShadow>
            <boxGeometry args={b.size} />
            <meshStandardMaterial map={cardboardTexture(b.shade)} roughness={0.9} />
          </mesh>
        ))}
      {variant === "shrinkwrap" && (
        <group position={[0, 0.14, 0]}>
          <mesh position={[0, 0.35, 0]} castShadow>
            <boxGeometry args={[0.95, 0.7, 0.85]} />
            <meshPhysicalMaterial color="#e6f2f5" roughness={0.25} transmission={0.35} thickness={0.3} opacity={0.75} transparent />
          </mesh>
          {Array.from({ length: 3 }).map((_, i) => (
            <mesh key={i} position={[0, 0.15 + i * 0.22, 0]}>
              <boxGeometry args={[0.75, 0.16, 0.68]} />
              <meshStandardMaterial map={cardboardTexture(i)} roughness={0.9} />
            </mesh>
          ))}
        </group>
      )}
      {variant === "drums" &&
        [-0.28, 0.28].map((dx, i) => (
          <mesh key={i} position={[dx, 0.14 + 0.45, 0]} castShadow>
            <cylinderGeometry args={[0.28, 0.28, 0.9, 20]} />
            <meshStandardMaterial color={DRUM_COLORS[(seed + i) % DRUM_COLORS.length]} roughness={0.5} metalness={0.4} />
          </mesh>
        ))}
    </group>
  );
}

function PalletBase({ position, woodMat }: { position: [number, number, number]; woodMat: THREE.Material }) {
  return (
    <group position={position}>
      {[-0.45, 0, 0.45].map((z, i) => (
        <mesh key={i} position={[0, 0.06, z]} material={woodMat} castShadow receiveShadow>
          <boxGeometry args={[1.1, 0.04, 0.14]} />
        </mesh>
      ))}
      {[-0.5, -0.17, 0.17, 0.5].map((x, i) => (
        <mesh key={i} position={[x, 0.11, 0]} material={woodMat} castShadow receiveShadow>
          <boxGeometry args={[0.1, 0.06, 1.0]} />
        </mesh>
      ))}
    </group>
  );
}
