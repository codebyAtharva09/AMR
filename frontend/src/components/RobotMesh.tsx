import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import type { AgentState } from "../types";
import { warehouseBoxTexture, woodPlankTexture } from "./warehouseTextures";

const STATE_LABEL: Record<string, string> = {
  idle: "IDLE",
  bidding: "BIDDING",
  moving_to_pickup: "TO PICKUP",
  moving_to_dropoff: "TO DROPOFF",
  returning_to_charge: "TO CHARGE",
  charging: "CHARGING",
  waiting: "WAITING",
  yielding: "YIELDING",
};

const CHASSIS_W = 0.6;
const CHASSIS_H = 0.18;
const CHASSIS_D = 0.5;
const CHASSIS_Y = 0.15; // center height of chassis above ground

// Lift-table cargo mechanism: a small platform on top of the chassis rises
// a few centimetres and a pallet+box appears when the robot is carrying a
// task (state === "moving_to_dropoff"), then lowers and the box disappears
// on drop-off - this is the part that actually sells "loading/delivering".
const PLATFORM_Y_REST = CHASSIS_Y + CHASSIS_H / 2 + 0.015;
const PLATFORM_LIFT = 0.1;
const LIFT_RATE = 5; // higher = snappier raise/lower
const FLASH_DURATION = 0.5; // seconds

/** Deterministic 0..1 pseudo-random value from an integer seed, used to vary
 * cargo box size/appearance per task without a shared RNG dependency. */
function pseudoRandom01(seed: number): number {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

export function RobotMesh({ agent, selected, onSelect }: { agent: AgentState; selected: boolean; onSelect: () => void }) {
  const group = useRef<THREE.Group>(null);
  const ledRing = useRef<THREE.Mesh>(null);
  const platformRef = useRef<THREE.Mesh>(null);
  const cargoBoxRef = useRef<THREE.Group>(null);
  const flashRef = useRef<THREE.Mesh>(null);
  const target = useRef(new THREE.Vector3(agent.x, 0, agent.y));
  const initialized = useRef(false);
  target.current.set(agent.x, 0, agent.y);

  const heading = Math.atan2(agent.vx, agent.vy);

  // A robot is treated as "carrying" while it's en route to a drop-off - it
  // has already lifted the load at the pickup point by that state.
  const carrying = agent.state === "moving_to_dropoff";
  const liftAmount = useRef(carrying ? 1 : 0);
  const prevCarrying = useRef(carrying);
  const flashElapsed = useRef(FLASH_DURATION);
  const flashColor = useRef(agent.color);
  if (prevCarrying.current !== carrying) {
    prevCarrying.current = carrying;
    flashElapsed.current = 0;
    flashColor.current = carrying ? "#F5C518" : agent.color;
  }

  useFrame((_, delta) => {
    if (!group.current) return;
    // Position is intentionally NOT a reactive JSX prop: R3F applies array props
    // unconditionally on every re-render (no equality check), which would snap the
    // group to the new snapshot position every ~66ms and defeat this lerp entirely.
    if (!initialized.current) {
      group.current.position.copy(target.current);
      initialized.current = true;
      return;
    }
    group.current.position.lerp(target.current, Math.min(1, delta * 10));
    if (Math.hypot(agent.vx, agent.vy) > 0.05) {
      const targetRot = -heading;
      let diff = targetRot - group.current.rotation.y;
      diff = Math.atan2(Math.sin(diff), Math.cos(diff));
      group.current.rotation.y += diff * Math.min(1, delta * 8);
    }
    if (ledRing.current) {
      const mat = ledRing.current.material as THREE.MeshStandardMaterial;
      const pulse = agent.state === "charging" ? 1.4 + Math.sin(Date.now() * 0.006) * 0.6 : 2.0;
      mat.emissiveIntensity = selected ? pulse + 0.6 : pulse;
    }

    // Lift-table raise/lower.
    const liftTarget = carrying ? 1 : 0;
    liftAmount.current = THREE.MathUtils.lerp(liftAmount.current, liftTarget, Math.min(1, delta * LIFT_RATE));
    const lift = liftAmount.current;
    if (platformRef.current) {
      platformRef.current.position.y = PLATFORM_Y_REST + lift * PLATFORM_LIFT;
    }
    if (cargoBoxRef.current) {
      const eased = lift * lift * (3 - 2 * lift); // smoothstep pop-in/out
      cargoBoxRef.current.scale.setScalar(Math.max(eased, 0.001));
      cargoBoxRef.current.position.y = PLATFORM_Y_REST + lift * PLATFORM_LIFT + 0.015;
    }

    // Brief flash ring at the moment cargo is picked up or set down.
    flashElapsed.current += delta;
    if (flashRef.current) {
      const t = Math.min(1, flashElapsed.current / FLASH_DURATION);
      const fade = 1 - t;
      const mat = flashRef.current.material as THREE.MeshBasicMaterial;
      mat.opacity = fade * 0.85;
      mat.color.set(flashColor.current);
      flashRef.current.scale.setScalar(1 + t * 1.8);
    }
  });

  const batteryColor = agent.battery > 40 ? "#34d399" : agent.battery > 20 ? "#f59e0b" : "#f87171";
  const wheelGeom = useMemo(() => new THREE.CylinderGeometry(0.08, 0.08, 0.06, 16), []);
  const casterGeom = useMemo(() => new THREE.SphereGeometry(0.04, 12, 12), []);

  const cargoSeed = agent.task_id ?? 0;
  const boxVariant = cargoSeed % 3;
  const boxTexture = useMemo(() => warehouseBoxTexture(boxVariant), [boxVariant]);
  const woodTex = useMemo(() => woodPlankTexture(), []);
  const boxSize = useMemo<[number, number, number]>(
    () => [
      0.24 + pseudoRandom01(cargoSeed * 3.1) * 0.1,
      0.16 + pseudoRandom01(cargoSeed * 7.7) * 0.12,
      0.24 + pseudoRandom01(cargoSeed * 5.3) * 0.1,
    ],
    [cargoSeed]
  );

  return (
    <group ref={group} onClick={onSelect}>
      {/* Main chassis */}
      <mesh position={[0, CHASSIS_Y, 0]} castShadow receiveShadow>
        <boxGeometry args={[CHASSIS_W, CHASSIS_H, CHASSIS_D]} />
        <meshStandardMaterial color="#1A1A1A" roughness={0.7} metalness={0.2} />
      </mesh>

      {/* Recessed top surface panel */}
      <mesh position={[0, CHASSIS_Y + CHASSIS_H / 2 - 0.005, 0]} castShadow>
        <boxGeometry args={[0.55, 0.02, 0.45]} />
        <meshStandardMaterial color="#2A2A2A" roughness={0.6} metalness={0.25} />
      </mesh>

      {/* Emergency stop button */}
      <mesh position={[0, CHASSIS_Y + CHASSIS_H / 2 + 0.025, 0]} castShadow>
        <cylinderGeometry args={[0.04, 0.04, 0.05, 16]} />
        <meshStandardMaterial color="#CC0000" roughness={0.4} metalness={0.3} />
      </mesh>

      {/* Lift-table platform - rises out of the top deck while carrying a load */}
      <mesh ref={platformRef} position={[0, PLATFORM_Y_REST, 0]} castShadow receiveShadow>
        <boxGeometry args={[0.44, 0.025, 0.38]} />
        <meshStandardMaterial color="#F5C518" roughness={0.5} metalness={0.4} />
      </mesh>

      {/* Cargo: mini pallet board + box, scaled in/out as the lift raises/lowers */}
      <group ref={cargoBoxRef} position={[0, PLATFORM_Y_REST + 0.015, 0]} scale={0.001}>
        <mesh position={[0, 0.015, 0]} castShadow receiveShadow>
          <boxGeometry args={[0.34, 0.03, 0.3]} />
          <meshStandardMaterial map={woodTex} color="#8B6914" roughness={0.9} metalness={0} />
        </mesh>
        <mesh position={[0, 0.03 + boxSize[1] / 2, 0]} castShadow receiveShadow>
          <boxGeometry args={boxSize} />
          <meshStandardMaterial map={boxTexture} roughness={0.8} metalness={0} />
        </mesh>
      </group>

      {/* Pickup/drop-off flash - a quick coloured ring pulse at the lift-table */}
      <mesh ref={flashRef} position={[0, PLATFORM_Y_REST + 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.32, 0.5, 32]} />
        <meshBasicMaterial
          color={agent.color}
          transparent
          opacity={0}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* LED perimeter ring - emissive in the robot's assigned colour */}
      <mesh ref={ledRing} position={[0, 0.09, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.28, 0.015, 8, 32]} />
        <meshStandardMaterial color="#000000" emissive={agent.color} emissiveIntensity={2.0} toneMapped={false} />
      </mesh>

      {/* Drive wheels (differential pair) */}
      {[-1, 1].map((side) => (
        <mesh key={side} geometry={wheelGeom} position={[side * (CHASSIS_W / 2 - 0.03), 0.08, 0]} rotation={[0, 0, Math.PI / 2]} castShadow>
          <meshStandardMaterial color="#333333" roughness={0.8} metalness={0.1} />
        </mesh>
      ))}

      {/* Caster wheels: front pair + rear pair */}
      {[
        [-0.22, -0.18],
        [0.22, -0.18],
        [-0.22, 0.18],
        [0.22, 0.18],
      ].map(([x, z], i) => (
        <mesh key={i} geometry={casterGeom} position={[x, 0.04, z]} castShadow>
          <meshStandardMaterial color="#444444" roughness={0.5} metalness={0.3} />
        </mesh>
      ))}

      {selected && (
        <mesh position={[0, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.36, 0.42, 32]} />
          <meshBasicMaterial color="#e6edf7" transparent opacity={0.6} />
        </mesh>
      )}

      {/* Battery level - a small arc above the robot, separate from the base LED ring */}
      <mesh position={[0, 0.55, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.1, 0.13, 32, 1, 0, (agent.battery / 100) * Math.PI * 2]} />
        <meshBasicMaterial color={batteryColor} transparent opacity={0.9} side={THREE.DoubleSide} />
      </mesh>

      <Html position={[0, 0.75, 0]} center distanceFactor={12} zIndexRange={[0, 0]}>
        <div
          className="pointer-events-none select-none rounded-md border border-white/10 px-1.5 py-0.5 text-[9px] mono whitespace-nowrap shadow-lg"
          style={{ transform: "translateY(-6px)", background: "rgba(10,12,16,0.55)" }}
        >
          <span style={{ color: agent.color }} className="font-semibold">{agent.id}</span>
          <span className="text-white/60"> · {STATE_LABEL[agent.state] ?? agent.state}</span>
          {carrying && <span className="text-amber-300"> · LOADED</span>}
          <div className="mt-0.5 h-1 w-14 rounded bg-white/15 overflow-hidden">
            <div className="h-full rounded" style={{ width: `${agent.battery}%`, background: batteryColor }} />
          </div>
        </div>
      </Html>
    </group>
  );
}
