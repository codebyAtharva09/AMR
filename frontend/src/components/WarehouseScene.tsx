import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { Suspense, useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { RectAreaLightUniformsLib } from "three/examples/jsm/lights/RectAreaLightUniformsLib.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { FXAAPass } from "three/examples/jsm/postprocessing/FXAAPass.js";
import { useFleetStore } from "../store/useFleetStore";
import { RobotMesh } from "./RobotMesh";
import { CommLinks } from "./CommLinks";
import { TaskMarkers } from "./TaskMarkers";
import { BlockedAisleMarkers } from "./BlockedAisleMarkers";
import { RealisticRackBlock } from "./RealisticRack";
import { concreteFloorTexture } from "./warehouseTextures";
import { WarehouseShell } from "./WarehouseShell";
import { Minimap } from "./Minimap";

RectAreaLightUniformsLib.init();

const CELL = 2.0;
const LANE_COLOR = "#F5C518";
const LANE_WIDTH = 0.08;

/** Groups the flat per-cell rack list into its rectangular rack-zone blocks
 * (4-connected flood fill) so each contiguous zone gets one rack structure
 * instead of one flat box per grid cell. */
function groupRackBlocks(cells: { row: number; col: number }[]) {
  const key = (r: number, c: number) => `${r},${c}`;
  const set = new Set(cells.map((c) => key(c.row, c.col)));
  const visited = new Set<string>();
  const blocks: { rowMin: number; rowMax: number; colMin: number; colMax: number }[] = [];

  for (const c of cells) {
    const start = key(c.row, c.col);
    if (visited.has(start)) continue;
    visited.add(start);
    const stack = [c];
    let rowMin = c.row, rowMax = c.row, colMin = c.col, colMax = c.col;
    while (stack.length) {
      const cur = stack.pop()!;
      rowMin = Math.min(rowMin, cur.row);
      rowMax = Math.max(rowMax, cur.row);
      colMin = Math.min(colMin, cur.col);
      colMax = Math.max(colMax, cur.col);
      for (const [dr, dc] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const nr = cur.row + dr;
        const nc = cur.col + dc;
        const nk = key(nr, nc);
        if (set.has(nk) && !visited.has(nk)) {
          visited.add(nk);
          stack.push({ row: nr, col: nc });
        }
      }
    }
    blocks.push({ rowMin, rowMax, colMin, colMax });
  }
  return blocks;
}

function blockSignLabel(
  b: { rowMin: number; colMin: number },
  rowBands: number[],
  colBands: number[]
) {
  const rowLetter = String.fromCharCode(65 + rowBands.indexOf(b.rowMin));
  const colNumber = colBands.indexOf(b.colMin) + 1;
  return `${rowLetter}${colNumber}`;
}

function Racks() {
  const layout = useFleetStore((s) => s.layout);
  const blocks = useMemo(() => (layout ? groupRackBlocks(layout.racks) : []), [layout]);
  const rowBands = useMemo(() => Array.from(new Set(blocks.map((b) => b.rowMin))).sort((a, b) => a - b), [blocks]);
  const colBands = useMemo(() => Array.from(new Set(blocks.map((b) => b.colMin))).sort((a, b) => a - b), [blocks]);
  if (!layout) return null;
  return (
    <group>
      {blocks.map((b, i) => {
        const centerX = ((b.colMin + b.colMax) / 2) * CELL;
        const centerZ = ((b.rowMin + b.rowMax) / 2) * CELL;
        const width = (b.colMax - b.colMin + 1) * CELL;
        return (
          <RealisticRackBlock
            key={i}
            centerX={centerX}
            centerZ={centerZ}
            width={width}
            signLabel={blockSignLabel(b, rowBands, colBands)}
          />
        );
      })}
    </group>
  );
}

function StationMarkers() {
  const layout = useFleetStore((s) => s.layout);
  if (!layout) return null;
  const render = (pts: [number, number][], color: string, label: string) =>
    pts.map(([row, col], i) => (
      <group key={`${label}-${i}`} position={[col * CELL, 0.02, row * CELL]}>
        <mesh rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.55, 0.85, 24]} />
          <meshBasicMaterial color={color} transparent opacity={0.7} />
        </mesh>
      </group>
    ));
  return (
    <group>
      {render(layout.pickup_stations, "#22d3ee", "pickup")}
      {render(layout.dropoff_stations, "#34d399", "dropoff")}
      {render(layout.charging_stations, "#f59e0b", "charge")}
    </group>
  );
}

/** Derives aisle rows/cols (the lanes with zero rack cells) from the layout's
 * rack list, so the painted lane lines follow the actual layout rather than
 * being hardcoded to one specific warehouse. */
function LaneMarkings() {
  const layout = useFleetStore((s) => s.layout);
  const geom = useMemo(() => {
    if (!layout) return null;
    const rackRows = new Set(layout.racks.map((r) => r.row));
    const rackCols = new Set(layout.racks.map((r) => r.col));
    const aisleRows = Array.from({ length: layout.rows }, (_, r) => r).filter((r) => !rackRows.has(r));
    const aisleCols = Array.from({ length: layout.cols }, (_, c) => c).filter((c) => !rackCols.has(c));
    const w = layout.cols * CELL;
    const d = layout.rows * CELL;
    return { aisleRows, aisleCols, w, d };
  }, [layout]);

  if (!geom) return null;
  return (
    <group position={[0, 0.005, 0]}>
      {geom.aisleRows.map((r) => (
        <mesh key={`row-${r}`} rotation={[-Math.PI / 2, 0, 0]} position={[geom.w / 2 - CELL / 2, 0, r * CELL]}>
          <planeGeometry args={[geom.w, LANE_WIDTH]} />
          <meshStandardMaterial color={LANE_COLOR} roughness={0.7} metalness={0} />
        </mesh>
      ))}
      {geom.aisleCols.map((c) => (
        <mesh key={`col-${c}`} rotation={[-Math.PI / 2, 0, 0]} position={[c * CELL, 0, geom.d / 2 - CELL / 2]}>
          <planeGeometry args={[LANE_WIDTH, geom.d]} />
          <meshStandardMaterial color={LANE_COLOR} roughness={0.7} metalness={0} />
        </mesh>
      ))}
    </group>
  );
}

function Floor() {
  const layout = useFleetStore((s) => s.layout);
  const w = (layout?.cols ?? 13) * CELL;
  const d = (layout?.rows ?? 9) * CELL;
  const texture = useMemo(() => concreteFloorTexture(), []);
  return (
    <group>
      <mesh position={[w / 2 - CELL / 2, -0.05, d / 2 - CELL / 2]} receiveShadow rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[w + 2, d + 2]} />
        <meshStandardMaterial map={texture} color="#B8B4A8" roughness={0.85} metalness={0.05} />
      </mesh>
      <LaneMarkings />
    </group>
  );
}

/** Ceiling fluorescent strip lights - ambient warm light with a directional
 * key light for shadows, sized to the warehouse footprint. */
function WarehouseLighting({ width, depth }: { width: number; depth: number }) {
  // RectAreaLight shading (LTC-based) is notably more expensive per-pixel than a
  // point/directional light; 2 strips still reads as "fluorescent ceiling strips"
  // while keeping headroom on lower-end GPUs.
  const stripCount = 2;
  return (
    <group>
      <ambientLight color="#FFF5E0" intensity={0.4} />
      {Array.from({ length: stripCount }).map((_, i) => (
        <rectAreaLight
          key={i}
          position={[((i + 0.5) / stripCount) * width, 8, depth / 2]}
          rotation={[-Math.PI / 2, 0, 0]}
          width={6}
          height={0.3}
          color="#FFFAF0"
          intensity={8}
        />
      ))}
      <directionalLight
        position={[width * 0.25, 12, depth * 0.15]}
        target-position={[width / 2, 0, depth / 2]}
        color="#ffffff"
        intensity={0.6}
        castShadow
        shadow-mapSize={[1024, 1024]}
        shadow-camera-left={-width}
        shadow-camera-right={width}
        shadow-camera-top={depth}
        shadow-camera-bottom={-depth}
      />
    </group>
  );
}

/** Subtle PMREM room environment for faint floor/steel reflections - fully
 * procedural (three.js's built-in RoomEnvironment), no external HDRI fetch. */
function SceneEnvironment() {
  const { gl, scene } = useThree();
  useEffect(() => {
    const pmrem = new THREE.PMREMGenerator(gl);
    const envTexture = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = envTexture;
    pmrem.dispose();
    return () => {
      envTexture.dispose();
      scene.environment = null;
    };
  }, [gl, scene]);
  return null;
}

/** FXAA antialiasing pass, replacing the default single-pass render. */
function PostFX() {
  const { gl, scene, camera, size } = useThree();
  const composer = useMemo(() => {
    const c = new EffectComposer(gl);
    c.addPass(new RenderPass(scene, camera));
    c.addPass(new FXAAPass());
    return c;
  }, [gl, scene, camera]);

  useEffect(() => {
    composer.setSize(size.width, size.height);
  }, [composer, size]);

  useFrame(() => {
    composer.render();
  }, 1);

  return null;
}

/** Owns the camera outside of what OrbitControls does on its own:
 *  - a cinematic wide-to-operating fly-in the first couple of seconds after load
 *  - a "follow" behaviour that eases the orbit target onto the selected robot,
 *    so picking a robot in the roster or clicking it in-scene keeps it centred
 *    as it drives around, without taking the orbit angle away from the user.
 */
function CameraDirector({ centerX, centerZ, restX, restY, restZ }: { centerX: number; centerZ: number; restX: number; restY: number; restZ: number }) {
  const { camera } = useThree();
  // Typed loosely: drei's OrbitControls ref is the underlying three-stdlib
  // instance, which isn't a direct project dependency to import a type from.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const controlsRef = useRef<any>(null);
  const selectedAgentId = useFleetStore((s) => s.selectedAgentId);
  const snapshot = useFleetStore((s) => s.snapshot);

  const introProgress = useRef(0);
  const introFrom = useRef(new THREE.Vector3());
  const introTo = useRef(new THREE.Vector3());

  useEffect(() => {
    introTo.current.set(restX, restY, restZ);
    introFrom.current.set(centerX - 4, restY + 30, centerZ + 18);
    camera.position.copy(introFrom.current);
    introProgress.current = 0;
    // Runs once on mount, and again the one time the real layout dimensions
    // replace the pre-layout fallback footprint.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restX, restY, restZ, centerX, centerZ]);

  useFrame((_, delta) => {
    if (introProgress.current < 1) {
      introProgress.current = Math.min(1, introProgress.current + delta / 2.4);
      const ease = 1 - Math.pow(1 - introProgress.current, 3);
      camera.position.lerpVectors(introFrom.current, introTo.current, ease);
    }

    const controls = controlsRef.current;
    if (!controls) return;
    const agent = selectedAgentId ? snapshot?.primary.agents.find((a) => a.id === selectedAgentId) ?? null : null;
    const desiredX = agent ? agent.x : centerX;
    const desiredY = agent ? 0.4 : 0.5;
    const desiredZ = agent ? agent.y : centerZ;
    const rate = Math.min(1, delta * (agent ? 2.5 : 2));
    controls.target.x = THREE.MathUtils.lerp(controls.target.x, desiredX, rate);
    controls.target.y = THREE.MathUtils.lerp(controls.target.y, desiredY, rate);
    controls.target.z = THREE.MathUtils.lerp(controls.target.z, desiredZ, rate);
    controls.update();
  });

  return (
    <OrbitControls
      ref={controlsRef}
      maxPolarAngle={Math.PI / 2.2}
      minDistance={5}
      maxDistance={60}
      makeDefault
    />
  );
}

export function WarehouseScene() {
  const snapshot = useFleetStore((s) => s.snapshot);
  const layout = useFleetStore((s) => s.layout);
  const selectedAgentId = useFleetStore((s) => s.selectedAgentId);
  const setSelectedAgentId = useFleetStore((s) => s.setSelectedAgentId);

  const agents = snapshot?.primary.agents ?? [];
  const w = (layout?.cols ?? 13) * CELL;
  const d = (layout?.rows ?? 9) * CELL;

  return (
    <div className="relative h-full w-full">
      <Canvas
        shadows={{ type: THREE.PCFShadowMap }}
        camera={{ position: [w * 0.5 + 10, 10, d * 0.7 + 10], fov: 45 }}
        gl={{ antialias: false }}
      >
        <Suspense fallback={null}>
          <color attach="background" args={["#14161b"]} />
          <fog attach="fog" args={["#14161b", 42, 95]} />

          <WarehouseLighting width={w} depth={d} />
          <SceneEnvironment />

          <Floor />
          <WarehouseShell width={w} depth={d} cell={CELL} />
          <Racks />
          <StationMarkers />
          <BlockedAisleMarkers cellSize={CELL} />
          <TaskMarkers cellSize={CELL} />
          <CommLinks agents={agents} />
          {agents.map((agent) => (
            <RobotMesh
              key={agent.id}
              agent={agent}
              selected={selectedAgentId === agent.id}
              onSelect={() => setSelectedAgentId(selectedAgentId === agent.id ? null : agent.id)}
            />
          ))}

          <CameraDirector centerX={w / 2} centerZ={d / 2} restX={w * 0.5 + 10} restY={10} restZ={d * 0.7 + 10} />
          <PostFX />
        </Suspense>
      </Canvas>

      <Minimap width={w} depth={d} cell={CELL} />

      {selectedAgentId && (
        <div className="pointer-events-none absolute bottom-4 left-4 rounded-lg border border-white/10 bg-black/50 px-3 py-1.5 text-[11px] text-white/70 backdrop-blur">
          Following <span className="mono font-semibold text-white">{selectedAgentId}</span> · click it again to release
        </div>
      )}
    </div>
  );
}
