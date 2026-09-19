import * as THREE from "three";

const cache = new Map<string, THREE.Texture>();

/** Perforated-steel look for upright columns: punched oval holes on a painted metal base. */
export function punchedSteelTexture(baseColor: string): THREE.Texture {
  const key = `punch-${baseColor}`;
  const cached = cache.get(key);
  if (cached) return cached;

  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = baseColor;
  ctx.fillRect(0, 0, size, size);

  ctx.fillStyle = "rgba(0,0,0,0.55)";
  const holeW = size * 0.22;
  const holeH = size * 0.34;
  for (const cy of [size * 0.28, size * 0.72]) {
    ctx.beginPath();
    ctx.ellipse(size / 2, cy, holeW / 2, holeH / 2, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 2;
  ctx.strokeRect(1, 1, size - 2, size - 2);

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  cache.set(key, tex);
  return tex;
}

/** Brushed / grooved concrete floor with a faint expansion-joint grid. */
export function concreteFloorTexture(): THREE.Texture {
  const key = "concrete";
  const cached = cache.get(key);
  if (cached) return cached;

  const size = 512;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#3a3f47";
  ctx.fillRect(0, 0, size, size);

  const imgData = ctx.getImageData(0, 0, size, size);
  for (let i = 0; i < imgData.data.length; i += 4) {
    const n = (Math.random() - 0.5) * 14;
    imgData.data[i] += n;
    imgData.data[i + 1] += n;
    imgData.data[i + 2] += n;
  }
  ctx.putImageData(imgData, 0, 0);

  ctx.strokeStyle = "rgba(0,0,0,0.35)";
  ctx.lineWidth = 3;
  const cells = 4;
  for (let i = 1; i < cells; i++) {
    const p = (size / cells) * i;
    ctx.beginPath();
    ctx.moveTo(p, 0);
    ctx.lineTo(p, size);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(0, p);
    ctx.lineTo(size, p);
    ctx.stroke();
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(6, 6);
  cache.set(key, tex);
  return tex;
}

/** Corrugated cardboard look for cargo boxes. */
export function cardboardTexture(shade: number): THREE.Texture {
  const key = `cardboard-${shade}`;
  const cached = cache.get(key);
  if (cached) return cached;

  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const base = 150 + shade * 12;
  ctx.fillStyle = `rgb(${base + 20},${base - 10},${base - 55})`;
  ctx.fillRect(0, 0, size, size);
  ctx.strokeStyle = "rgba(0,0,0,0.12)";
  ctx.lineWidth = 1;
  for (let y = 4; y < size; y += 6) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(size, y);
    ctx.stroke();
  }
  const tex = new THREE.CanvasTexture(canvas);
  cache.set(key, tex);
  return tex;
}
