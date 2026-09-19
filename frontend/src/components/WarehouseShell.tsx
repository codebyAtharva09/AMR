import { useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { corrugatedMetalTexture, safetyStripeTexture, rollerDoorTexture, aisleSignTexture } from "./warehouseTextures";

const WALL_H = 6.5;
const WALL_T = 0.15;
const MARGIN = 1.6; // extra clearance beyond the floor edge
const STRIPE_H = 0.5;
const DOOR_W = 2.1;
const DOOR_H = 3.1;
const DOOR_COUNT = 3;

function cloneWithRepeat(tex: THREE.Texture, rx: number, ry: number): THREE.Texture {
  const t = tex.clone();
  t.needsUpdate = true;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(rx, ry);
  return t;
}

/** One perimeter wall panel: corrugated cladding + a painted hazard-stripe
 * wainscot along the base + a steel parapet cap along the top. */
function WallPanel({
  length,
  position,
  rotationY,
  metalTex,
  stripeTex,
}: {
  length: number;
  position: [number, number, number];
  rotationY: number;
  metalTex: THREE.Texture;
  stripeTex: THREE.Texture;
}) {
  const wallMap = useMemo(() => cloneWithRepeat(metalTex, Math.max(1, Math.round(length / 2.4)), 2), [metalTex, length]);
  const stripeMap = useMemo(() => cloneWithRepeat(stripeTex, Math.max(1, Math.round(length / 1.2)), 1), [stripeTex, length]);

  return (
    <group position={position} rotation={[0, rotationY, 0]}>
      <mesh position={[0, WALL_H / 2, 0]} castShadow receiveShadow>
        <boxGeometry args={[length, WALL_H, WALL_T]} />
        <meshStandardMaterial map={wallMap} roughness={0.75} metalness={0.35} />
      </mesh>
      <mesh position={[0, STRIPE_H / 2, WALL_T / 2 + 0.005]} receiveShadow>
        <boxGeometry args={[length, STRIPE_H, 0.02]} />
        <meshStandardMaterial map={stripeMap} roughness={0.8} />
      </mesh>
      <mesh position={[0, WALL_H + 0.12, 0]} castShadow>
        <boxGeometry args={[length + 0.3, 0.24, WALL_T + 0.15]} />
        <meshStandardMaterial color="#5b6270" roughness={0.5} metalness={0.5} />
      </mesh>
    </group>
  );
}

/** A closed roller-shutter loading-dock door set into the wall face, with a
 * dock bumper curb and a warning-striped frame. */
function DockDoor({ x, doorTex }: { x: number; doorTex: THREE.Texture }) {
  return (
    <group position={[x, 0, WALL_T / 2 + 0.02]}>
      <mesh position={[0, 0, -0.01]}>
        <boxGeometry args={[DOOR_W + 0.16, DOOR_H + 0.16, 0.03]} />
        <meshStandardMaterial color="#f5c518" roughness={0.6} />
      </mesh>
      <mesh position={[0, DOOR_H / 2, 0]} castShadow>
        <boxGeometry args={[DOOR_W, DOOR_H, 0.04]} />
        <meshStandardMaterial map={doorTex} roughness={0.7} metalness={0.15} />
      </mesh>
      {/* dock bumper curb */}
      <mesh position={[0, 0.18, 0.35]} castShadow receiveShadow>
        <boxGeometry args={[DOOR_W + 0.2, 0.36, 0.5]} />
        <meshStandardMaterial color="#3a3d44" roughness={0.9} />
      </mesh>
    </group>
  );
}

/** Perimeter shell around the warehouse footprint: four corrugated-metal
 * walls with a hazard-stripe wainscot, a set of loading-dock roller doors on
 * the south wall, a glowing EXIT sign, wall-pack lights, and an exterior
 * tarmac apron so the building doesn't read as a floor floating in fog. */
export function WarehouseShell({ width, depth, cell }: { width: number; depth: number; cell: number }) {
  const metalTex = useMemo(() => corrugatedMetalTexture(), []);
  const stripeTex = useMemo(() => safetyStripeTexture(), []);
  const doorTex = useMemo(() => rollerDoorTexture(), []);
  const exitSignTex = useMemo(() => aisleSignTexture("EXIT"), []);

  const centerX = width / 2 - cell / 2;
  const centerZ = depth / 2 - cell / 2;
  const halfX = width / 2 + 1 + MARGIN;
  const halfZ = depth / 2 + 1 + MARGIN;
  const lengthX = halfX * 2;
  const lengthZ = halfZ * 2;

  const doorXs = useMemo(() => {
    const spacing = lengthX / (DOOR_COUNT + 1);
    return Array.from({ length: DOOR_COUNT }, (_, i) => -halfX + spacing * (i + 1));
  }, [lengthX, halfX]);

  // Cutaway: any wall the camera is standing outside of would sit between the
  // viewer and the interior, so hide it. Orbit around and the wall you've moved
  // behind disappears while the far walls stay to frame the space.
  const { camera } = useThree();
  const southRef = useRef<THREE.Group>(null);
  const northRef = useRef<THREE.Group>(null);
  const westRef = useRef<THREE.Group>(null);
  const eastRef = useRef<THREE.Group>(null);
  useFrame(() => {
    const rx = camera.position.x - centerX;
    const rz = camera.position.z - centerZ;
    if (southRef.current) southRef.current.visible = !(rz < -halfZ);
    if (northRef.current) northRef.current.visible = !(rz > halfZ);
    if (westRef.current) westRef.current.visible = !(rx < -halfX);
    if (eastRef.current) eastRef.current.visible = !(rx > halfX);
  });

  return (
    <group position={[centerX, 0, centerZ]}>
      {/* south wall (loading dock face) */}
      <group ref={southRef} position={[0, 0, -halfZ]}>
        <WallPanel length={lengthX} position={[0, 0, 0]} rotationY={0} metalTex={metalTex} stripeTex={stripeTex} />
        {doorXs.map((x, i) => (
          <DockDoor key={i} x={x} doorTex={doorTex} />
        ))}
        <mesh position={[0, DOOR_H + 0.55, WALL_T / 2 + 0.03]}>
          <planeGeometry args={[0.7, 0.28]} />
          <meshStandardMaterial map={exitSignTex} emissive="#22c55e" emissiveIntensity={0.5} roughness={0.6} />
        </mesh>
      </group>

      {/* north wall */}
      <group ref={northRef}>
        <WallPanel length={lengthX} position={[0, 0, halfZ]} rotationY={Math.PI} metalTex={metalTex} stripeTex={stripeTex} />
      </group>
      {/* west wall */}
      <group ref={westRef}>
        <WallPanel length={lengthZ} position={[-halfX, 0, 0]} rotationY={-Math.PI / 2} metalTex={metalTex} stripeTex={stripeTex} />
      </group>
      {/* east wall */}
      <group ref={eastRef}>
        <WallPanel length={lengthZ} position={[halfX, 0, 0]} rotationY={Math.PI / 2} metalTex={metalTex} stripeTex={stripeTex} />
      </group>

      {/* wall-pack lights, one per side, aimed down into the floor */}
      {[
        [0, -halfZ + 0.4],
        [0, halfZ - 0.4],
        [-halfX + 0.4, 0],
        [halfX - 0.4, 0],
      ].map(([x, z], i) => (
        <group key={i} position={[x, WALL_H - 0.6, z]}>
          <mesh>
            <boxGeometry args={[0.3, 0.12, 0.12]} />
            <meshStandardMaterial color="#e8e8e8" emissive="#fff6dd" emissiveIntensity={0.8} />
          </mesh>
          <pointLight color="#fff6dd" intensity={2.5} distance={9} decay={2} />
        </group>
      ))}

      {/* exterior tarmac apron - keeps the building from reading as a floor floating in the fog */}
      <mesh position={[0, -0.08, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[lengthX + 30, lengthZ + 30]} />
        <meshStandardMaterial color="#181a1f" roughness={0.95} metalness={0} />
      </mesh>
    </group>
  );
}
