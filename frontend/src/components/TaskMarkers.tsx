import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { useFleetStore } from "../store/useFleetStore";

export function TaskMarkers({ cellSize }: { cellSize: number }) {
  const snapshot = useFleetStore((s) => s.snapshot);
  const tasks = snapshot?.primary.tasks ?? [];

  return (
    <group>
      {tasks.map((t) => {
        const [row, col] = t.status === "pending" ? t.pickup : t.dropoff;
        return <TaskPulse key={t.id} row={row} col={col} cellSize={cellSize} pending={t.status === "pending"} />;
      })}
    </group>
  );
}

function TaskPulse({ row, col, cellSize, pending }: { row: number; col: number; cellSize: number; pending: boolean }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const s = 0.7 + 0.15 * Math.sin(clock.elapsedTime * 4);
    ref.current.scale.setScalar(s);
  });
  return (
    <mesh ref={ref} position={[col * cellSize, 1.3, row * cellSize]}>
      <octahedronGeometry args={[0.22]} />
      <meshStandardMaterial
        color={pending ? "#facc15" : "#60a5fa"}
        emissive={pending ? "#facc15" : "#60a5fa"}
        emissiveIntensity={1.2}
      />
    </mesh>
  );
}
