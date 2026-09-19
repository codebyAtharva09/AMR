import { useMemo } from "react";
import * as THREE from "three";
import { ContactShadows } from "@react-three/drei";
import { concreteFloorTexture } from "../../utils/textures";

export function WarehouseFloor({ width, depth }: { width: number; depth: number }) {
  const texture = concreteFloorTexture();
  const w = Math.max(width + 8, 14);
  const d = Math.max(depth + 8, 14);
  const perimeterGeom = useMemo(() => new THREE.BoxGeometry(width + 0.6, 0.001, depth + 0.6), [width, depth]);

  return (
    <group>
      <mesh position={[width / 2, -0.02, depth / 2]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[w, d]} />
        <meshStandardMaterial map={texture} roughness={0.92} metalness={0.05} />
      </mesh>

      {/* Safety-yellow perimeter line around the rack footprint */}
      <lineSegments position={[width / 2, 0.01, depth / 2]}>
        <edgesGeometry args={[perimeterGeom]} />
        <lineBasicMaterial color="#facc15" />
      </lineSegments>

      <ContactShadows position={[width / 2, 0, depth / 2]} opacity={0.55} scale={Math.max(w, d)} blur={2.2} far={6} />
    </group>
  );
}
