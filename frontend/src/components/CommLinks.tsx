import { useEffect, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { AgentState } from "../types";

const LINK_RADIUS = 6.5;
const LINK_Y = 0.09; // LED ring height, not chassis centre

export function CommLinks({ agents }: { agents: AgentState[] }) {
  const pairs = useMemo(() => {
    const out: [AgentState, AgentState, number][] = [];
    for (let i = 0; i < agents.length; i++) {
      for (let j = i + 1; j < agents.length; j++) {
        const a = agents[i];
        const b = agents[j];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d < LINK_RADIUS) out.push([a, b, d]);
      }
    }
    return out;
  }, [agents]);

  return (
    <group>
      {pairs.map(([a, b, d], idx) => (
        <CommLink key={`${a.id}-${b.id}-${idx}`} a={a} b={b} dist={d} />
      ))}
    </group>
  );
}

function CommLink({ a, b, dist }: { a: AgentState; b: AgentState; dist: number }) {
  // Geometry, material, and the Line object are created exactly once per pair
  // and mutated in place thereafter - not recreated on every position update.
  const line = useMemo(() => {
    const geometry = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(0, 0, 0),
    ]);
    const material = new THREE.LineDashedMaterial({
      color: "#4ADE80",
      transparent: true,
      opacity: 0.35,
      dashSize: 0.18,
      gapSize: 0.12,
    });
    return new THREE.Line(geometry, material);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const pos = line.geometry.attributes.position as THREE.BufferAttribute;
    pos.setXYZ(0, a.x, LINK_Y, a.y);
    pos.setXYZ(1, b.x, LINK_Y, b.y);
    pos.needsUpdate = true;
    line.geometry.computeBoundingSphere();
    line.computeLineDistances();
  }, [line, a.x, a.y, b.x, b.y]);

  useFrame(({ clock }) => {
    (line.material as THREE.LineDashedMaterial).opacity = 0.35 + 0.45 * (0.5 + 0.5 * Math.sin(clock.elapsedTime * 3 + dist));
  });

  return <primitive object={line} />;
}
