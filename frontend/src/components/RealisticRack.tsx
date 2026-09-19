import { useMemo } from "react";
import * as THREE from "three";
import { powderCoatSteelTexture, woodPlankTexture, warehouseBoxTexture, aisleSignTexture } from "./warehouseTextures";

const UPRIGHT_COLOR = "#C0390B";
const BEAM_COLOR = "#D4420D";
const TIERS = 3;
const TIER_HEIGHT = 0.85;
const RACK_DEPTH = 1.3;
const BEAM_H = 0.09;

/** One realistic pallet-rack run: ladder-frame uprights, step beams, wooden
 * pallet-board decking, and boxed loads - powder-coated steel look via a
 * procedural canvas texture, same technique as the Rack Studio configurator
 * but fully decoupled from it (separate texture module). */
function RackRow({ x0, z, width, bays, signLabel }: { x0: number; z: number; width: number; bays: number; signLabel: string }) {
  const steelTex = useMemo(() => powderCoatSteelTexture(UPRIGHT_COLOR), []);
  const woodTex = useMemo(() => woodPlankTexture(), []);
  const signTex = useMemo(() => aisleSignTexture(signLabel), [signLabel]);
  const bayWidth = width / bays;
  const totalHeight = TIERS * TIER_HEIGHT + 0.15;

  const levels = useMemo(() => {
    const out: number[] = [];
    for (let t = 0; t < TIERS; t++) out.push(0.15 + (t + 1) * TIER_HEIGHT - BEAM_H / 2);
    return out;
  }, []);

  const signGeom = useMemo(() => new THREE.PlaneGeometry(0.4, 0.3), []);
  const wireLine = useMemo(() => {
    const geometry = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, totalHeight, 0),
      new THREE.Vector3(0, totalHeight + 0.35, 0),
    ]);
    return new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: "#888888" }));
  }, [totalHeight]);

  return (
    <group position={[x0, 0, z]}>
      {Array.from({ length: bays + 1 }).map((_, i) => (
        <group key={i} position={[i * bayWidth, 0, 0]}>
          {[-RACK_DEPTH / 2, RACK_DEPTH / 2].map((dz, j) => (
            <mesh key={j} position={[0, totalHeight / 2, dz]} castShadow receiveShadow>
              <boxGeometry args={[0.08, totalHeight, 0.08]} />
              <meshStandardMaterial map={steelTex} roughness={0.6} metalness={0.3} />
            </mesh>
          ))}
          {Array.from({ length: TIERS }).map((_, t) => (
            <mesh key={`brace${t}`} position={[0, (t + 0.5) * TIER_HEIGHT, 0]} rotation={[Math.PI / 2, 0, 0]} castShadow>
              <boxGeometry args={[0.03, RACK_DEPTH, 0.03]} />
              <meshStandardMaterial color={UPRIGHT_COLOR} roughness={0.6} metalness={0.3} />
            </mesh>
          ))}
        </group>
      ))}

      {Array.from({ length: bays }).map((_, b) =>
        levels.map((y, t) => (
          <group key={`${b}-${t}`}>
            {[-RACK_DEPTH / 2, RACK_DEPTH / 2].map((dz, j) => (
              <mesh key={j} position={[b * bayWidth + bayWidth / 2, y, dz]} castShadow receiveShadow>
                <boxGeometry args={[bayWidth * 0.94, BEAM_H, 0.05]} />
                <meshStandardMaterial color={BEAM_COLOR} roughness={0.55} metalness={0.4} />
              </mesh>
            ))}
            <PalletBoards x={b * bayWidth + bayWidth / 2} y={y + BEAM_H / 2} width={bayWidth * 0.9} woodTex={woodTex} />
            <PalletRow x={b * bayWidth + bayWidth / 2} y={y + BEAM_H / 2 + 0.03} bayWidth={bayWidth} seed={b * 13 + t * 7} />
          </group>
        ))
      )}

      {/* Hanging aisle sign, suspended from the rack top on a thin wire */}
      <group position={[width / 2, 0, RACK_DEPTH / 2 + 0.05]}>
        <primitive object={wireLine} />
        <mesh position={[0, totalHeight + 0.35, 0]} geometry={signGeom} castShadow>
          <meshStandardMaterial map={signTex} roughness={0.7} side={THREE.DoubleSide} />
        </mesh>
      </group>
    </group>
  );
}

function PalletBoards({ x, y, width, woodTex }: { x: number; y: number; width: number; woodTex: THREE.Texture }) {
  const planks = 4;
  return (
    <group position={[x, y + 0.025, 0]}>
      {Array.from({ length: planks }).map((_, i) => (
        <mesh key={i} position={[0, 0, (i - (planks - 1) / 2) * (RACK_DEPTH * 0.85 / planks)]} castShadow receiveShadow>
          <boxGeometry args={[width, 0.04, RACK_DEPTH * 0.85 / planks - 0.01]} />
          <meshStandardMaterial map={woodTex} color="#8B6914" roughness={0.9} metalness={0} />
        </mesh>
      ))}
    </group>
  );
}

function seededRandom(seed: number) {
  let s = (seed % 2147483647) || 1;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

function PalletRow({ x, y, bayWidth, seed }: { x: number; y: number; bayWidth: number; seed: number }) {
  const rand = useMemo(() => seededRandom(seed + 1), [seed]);
  const woodMat = useMemo(() => new THREE.MeshStandardMaterial({ color: "#a9853f", roughness: 0.85 }), []);
  const boxes = useMemo(
    () =>
      Array.from({ length: 3 + Math.floor(rand() * 2) }).map(() => ({
        size: [0.22 + rand() * 0.1, 0.14 + rand() * 0.14, 0.22 + rand() * 0.1] as [number, number, number],
        dx: (rand() - 0.5) * bayWidth * 0.6,
        variant: Math.floor(rand() * 3),
      })),
    [rand, bayWidth]
  );

  return (
    <group position={[x, y, 0]}>
      <mesh position={[0, 0.03, 0]} material={woodMat} castShadow receiveShadow>
        <boxGeometry args={[bayWidth * 0.85, 0.05, RACK_DEPTH * 0.75]} />
      </mesh>
      {boxes.map((b, i) => (
        <mesh key={i} position={[b.dx, 0.06 + b.size[1] / 2, 0]} castShadow receiveShadow>
          <boxGeometry args={b.size} />
          <meshStandardMaterial map={warehouseBoxTexture(b.variant)} roughness={0.8} metalness={0} />
        </mesh>
      ))}
    </group>
  );
}

/** A single realistic rack run centered within a rectangular rack-zone footprint. */
export function RealisticRackBlock({
  centerX,
  centerZ,
  width,
  signLabel,
}: {
  centerX: number;
  centerZ: number;
  width: number;
  signLabel: string;
}) {
  const bays = Math.max(1, Math.round(width / 3));
  return <RackRow x0={centerX - width / 2} z={centerZ} width={width} bays={bays} signLabel={signLabel} />;
}
