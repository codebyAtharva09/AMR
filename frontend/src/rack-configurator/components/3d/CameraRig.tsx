import { useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import type { CameraPreset } from "../../types";

function presetFor(preset: CameraPreset, width: number, depth: number, height: number) {
  const cx = width / 2;
  const cz = depth / 2;
  switch (preset) {
    case "front":
      return { pos: new THREE.Vector3(cx, height * 0.55, depth + Math.max(width, height) * 1.1), target: new THREE.Vector3(cx, height * 0.45, cz) };
    case "top":
      return { pos: new THREE.Vector3(cx, Math.max(width, depth) * 1.6 + 3, cz + 0.01), target: new THREE.Vector3(cx, 0, cz) };
    case "side":
      return { pos: new THREE.Vector3(width + Math.max(depth, height) * 1.3, height * 0.5, cz), target: new THREE.Vector3(cx, height * 0.4, cz) };
    case "walkthrough":
      return { pos: new THREE.Vector3(cx, 1.1, -0.5), target: new THREE.Vector3(cx, 1.0, depth * 0.6) };
    case "isometric":
    default:
      return {
        pos: new THREE.Vector3(cx + Math.max(width, 4) * 0.75, height * 0.95 + 2, depth + Math.max(width, depth, 4) * 0.95),
        target: new THREE.Vector3(cx, height * 0.35, cz),
      };
  }
}

export function CameraRig({
  preset,
  width,
  depth,
  height,
}: {
  preset: CameraPreset;
  width: number;
  depth: number;
  height: number;
}) {
  const controls = useRef<OrbitControlsImpl>(null);
  const { camera } = useThree();
  const targetPos = useRef(new THREE.Vector3());
  const targetLook = useRef(new THREE.Vector3());
  const animating = useRef(true);

  const { pos, target } = presetFor(preset, width, depth, height);
  targetPos.current.copy(pos);
  targetLook.current.copy(target);
  animating.current = true;

  useFrame((_, delta) => {
    const t = Math.min(1, delta * 3.5);
    camera.position.lerp(targetPos.current, t);
    if (controls.current) {
      controls.current.target.lerp(targetLook.current, t);
      controls.current.update();
    }
  });

  return (
    <OrbitControls
      ref={controls}
      makeDefault
      enableDamping
      dampingFactor={0.12}
      minDistance={1.5}
      maxDistance={40}
      maxPolarAngle={Math.PI / 2.02}
    />
  );
}
