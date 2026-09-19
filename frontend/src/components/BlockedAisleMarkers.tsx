import { useMemo } from "react";
import { useFleetStore } from "../store/useFleetStore";

export function BlockedAisleMarkers({ cellSize }: { cellSize: number }) {
  const snapshot = useFleetStore((s) => s.snapshot);
  const edges = snapshot?.primary.blocked_edges ?? [];

  const nodes = useMemo(() => {
    const set = new Set<string>();
    edges.forEach((edge) => edge.forEach(([row, col]) => set.add(`${row},${col}`)));
    return Array.from(set).map((k) => k.split(",").map(Number) as [number, number]);
  }, [edges]);

  return (
    <group>
      {nodes.map(([row, col]) => (
        <group key={`${row}-${col}`} position={[col * cellSize, 0.03, row * cellSize]}>
          <mesh rotation={[-Math.PI / 2, 0, 0]}>
            <circleGeometry args={[0.95, 24]} />
            <meshBasicMaterial color="#f87171" transparent opacity={0.28} />
          </mesh>
          <mesh position={[0, 0.4, 0]} rotation={[0, Math.PI / 4, 0]}>
            <boxGeometry args={[1.3, 0.06, 0.12]} />
            <meshStandardMaterial color="#f87171" emissive="#f87171" emissiveIntensity={0.6} />
          </mesh>
          <mesh position={[0, 0.4, 0]} rotation={[0, -Math.PI / 4, 0]}>
            <boxGeometry args={[1.3, 0.06, 0.12]} />
            <meshStandardMaterial color="#f87171" emissive="#f87171" emissiveIntensity={0.6} />
          </mesh>
        </group>
      ))}
    </group>
  );
}
