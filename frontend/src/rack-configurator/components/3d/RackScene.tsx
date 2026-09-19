import { Canvas } from "@react-three/fiber";
import { Suspense, forwardRef } from "react";
import { WarehouseFloor } from "./WarehouseFloor";
import { SelectiveRack } from "./SelectiveRack";
import { CantileverRack } from "./CantileverRack";
import { DriveInRack } from "./DriveInRack";
import { CameraRig } from "./CameraRig";
import { useRackConfigStore } from "../../store/useRackConfigStore";

export const RackScene = forwardRef<HTMLCanvasElement>(function RackScene(_, canvasRef) {
  const config = useRackConfigStore((s) => s.config);
  const cameraPreset = useRackConfigStore((s) => s.cameraPreset);
  const setSelected = useRackConfigStore((s) => s.setSelected);

  const width = (config.bays * config.bayWidthMm) / 1000;
  const depth =
    config.rackType === "drive_in" ? (config.bayDepthMm / 1000) * 3 : config.bayDepthMm / 1000;
  const rackHeight =
    (config.clearanceHeightMm / 1000 + 0.2) * config.tiers + 0.3;

  return (
    <Canvas
      shadows
      gl={{ preserveDrawingBuffer: true, antialias: true }}
      camera={{ fov: 45 }}
      onCreated={({ gl }) => {
        if (canvasRef && typeof canvasRef === "object") canvasRef.current = gl.domElement;
      }}
      onPointerMissed={() => setSelected(null)}
    >
      <Suspense fallback={null}>
        <color attach="background" args={["#151a22"]} />
        <fog attach="fog" args={["#151a22", 18, 45]} />
        <ambientLight intensity={0.5} />
        <hemisphereLight args={["#dbeafe", "#1a1f28", 0.55]} />
        <directionalLight
          position={[width * 0.6 + 4, 10, depth + 6]}
          intensity={1.3}
          castShadow
          shadow-mapSize={[2048, 2048]}
          shadow-camera-left={-12}
          shadow-camera-right={12}
          shadow-camera-top={12}
          shadow-camera-bottom={-12}
        />
        <pointLight position={[width / 2, rackHeight + 3, depth / 2]} intensity={0.6} color="#fef3c7" />

        <WarehouseFloor width={width} depth={depth} />

        {config.rackType === "selective" && <SelectiveRack config={config} />}
        {config.rackType === "cantilever" && <CantileverRack config={config} />}
        {config.rackType === "drive_in" && <DriveInRack config={config} />}

        <CameraRig preset={cameraPreset} width={width} depth={depth} height={rackHeight} />
      </Suspense>
    </Canvas>
  );
});
