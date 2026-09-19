import * as THREE from "three";

const cache = new Map<string, THREE.Texture>();

/** Light grey concrete with subtle aggregate grain - procedurally painted on a
 * canvas, no external image assets. */
export function concreteFloorTexture(): THREE.Texture {
  const key = "warehouse-concrete";
  const cached = cache.get(key);
  if (cached) return cached;

  const size = 512;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#b8b4a8";
  ctx.fillRect(0, 0, size, size);

  const img = ctx.getImageData(0, 0, size, size);
  for (let i = 0; i < img.data.length; i += 4) {
    const n = (Math.random() - 0.5) * 10;
    img.data[i] += n;
    img.data[i + 1] += n;
    img.data[i + 2] += n * 0.8;
  }
  ctx.putImageData(img, 0, 0);

  // sparse darker aggregate speckles
  ctx.fillStyle = "rgba(90,86,78,0.35)";
  for (let i = 0; i < 900; i++) {
    const x = Math.random() * size;
    const y = Math.random() * size;
    const r = 0.4 + Math.random() * 1.1;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }

  // faint expansion-joint grid
  ctx.strokeStyle = "rgba(60,58,52,0.25)";
  ctx.lineWidth = 2;
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
  tex.repeat.set(8, 8);
  tex.colorSpace = THREE.SRGBColorSpace;
  cache.set(key, tex);
  return tex;
}

/** Powder-coated steel: a base colour with faint brushed streaks and a couple
 * of punched mounting holes, tileable along the column length. */
export function powderCoatSteelTexture(baseColor: string): THREE.Texture {
  const key = `powdercoat-${baseColor}`;
  const cached = cache.get(key);
  if (cached) return cached;

  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = baseColor;
  ctx.fillRect(0, 0, size, size);

  ctx.strokeStyle = "rgba(0,0,0,0.06)";
  ctx.lineWidth = 1;
  for (let y = 0; y < size; y += 3) {
    ctx.beginPath();
    ctx.moveTo(0, y + Math.random() * 2);
    ctx.lineTo(size, y + Math.random() * 2);
    ctx.stroke();
  }

  ctx.fillStyle = "rgba(0,0,0,0.5)";
  const holeW = size * 0.2;
  const holeH = size * 0.3;
  for (const cy of [size * 0.28, size * 0.72]) {
    ctx.beginPath();
    ctx.ellipse(size / 2, cy, holeW / 2, holeH / 2, 0, 0, Math.PI * 2);
    ctx.fill();
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  cache.set(key, tex);
  return tex;
}

/** Aged wooden pallet-board grain. */
export function woodPlankTexture(): THREE.Texture {
  const key = "warehouse-wood";
  const cached = cache.get(key);
  if (cached) return cached;

  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#8b6914";
  ctx.fillRect(0, 0, size, size);
  ctx.strokeStyle = "rgba(60,40,10,0.25)";
  for (let i = 0; i < 14; i++) {
    ctx.lineWidth = 0.5 + Math.random();
    ctx.beginPath();
    const y = Math.random() * size;
    ctx.moveTo(0, y);
    ctx.bezierCurveTo(size * 0.3, y + (Math.random() - 0.5) * 6, size * 0.7, y + (Math.random() - 0.5) * 6, size, y);
    ctx.stroke();
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  cache.set(key, tex);
  return tex;
}

const BOX_COLORS = ["#8B7355", "#6B8E6B", "#4A5568"];

/** Cardboard / wrapped / crate box texture, one of three mixed-load colours. */
export function warehouseBoxTexture(variant: number): THREE.Texture {
  const color = BOX_COLORS[variant % BOX_COLORS.length];
  const key = `warehouse-box-${color}`;
  const cached = cache.get(key);
  if (cached) return cached;

  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = color;
  ctx.fillRect(0, 0, size, size);
  ctx.strokeStyle = "rgba(0,0,0,0.15)";
  ctx.lineWidth = 1;
  for (let y = 4; y < size; y += 7) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(size, y);
    ctx.stroke();
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  cache.set(key, tex);
  return tex;
}

/** Simple black-on-white aisle sign texture, e.g. "A1". */
export function aisleSignTexture(label: string): THREE.Texture {
  const key = `sign-${label}`;
  const cached = cache.get(key);
  if (cached) return cached;

  const w = 256, h = 192;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#f7f7f5";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#111";
  ctx.lineWidth = 4;
  ctx.strokeRect(4, 4, w - 8, h - 8);
  ctx.fillStyle = "#111";
  ctx.font = "bold 110px Helvetica, Arial, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, w / 2, h / 2 + 6);

  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  cache.set(key, tex);
  return tex;
}

/** Corrugated sheet-metal cladding for exterior/perimeter walls - vertical
 * ribs with a soft light/shadow gradient per rib, tileable horizontally. */
export function corrugatedMetalTexture(baseColor = "#9aa1ac"): THREE.Texture {
  const key = `corrugated-${baseColor}`;
  const cached = cache.get(key);
  if (cached) return cached;

  const size = 256;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = baseColor;
  ctx.fillRect(0, 0, size, size);

  const ribs = 16;
  const ribW = size / ribs;
  for (let i = 0; i < ribs; i++) {
    const x = i * ribW;
    const grad = ctx.createLinearGradient(x, 0, x + ribW, 0);
    grad.addColorStop(0, "rgba(0,0,0,0.22)");
    grad.addColorStop(0.35, "rgba(255,255,255,0.18)");
    grad.addColorStop(0.65, "rgba(255,255,255,0.05)");
    grad.addColorStop(1, "rgba(0,0,0,0.22)");
    ctx.fillStyle = grad;
    ctx.fillRect(x, 0, ribW, size);
  }
  // faint horizontal panel seams
  ctx.strokeStyle = "rgba(0,0,0,0.15)";
  ctx.lineWidth = 2;
  for (let y = size * 0.33; y < size; y += size * 0.33) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(size, y);
    ctx.stroke();
  }
  // light streaks of grime
  ctx.fillStyle = "rgba(40,40,35,0.08)";
  for (let i = 0; i < 40; i++) {
    const x = Math.random() * size;
    const y = Math.random() * size;
    ctx.fillRect(x, y, 1 + Math.random() * 2, 8 + Math.random() * 30);
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  cache.set(key, tex);
  return tex;
}

/** Black/yellow hazard chevron stripe, for wall base wainscots and floor
 * hazard zones. */
export function safetyStripeTexture(): THREE.Texture {
  const key = "safety-stripe";
  const cached = cache.get(key);
  if (cached) return cached;

  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#111111";
  ctx.fillRect(0, 0, size, size);
  ctx.fillStyle = "#F5C518";
  ctx.save();
  ctx.translate(size / 2, size / 2);
  ctx.rotate(Math.PI / 4);
  ctx.translate(-size, -size);
  for (let x = 0; x < size * 4; x += 32) {
    ctx.fillRect(x, 0, 16, size * 2);
  }
  ctx.restore();

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  cache.set(key, tex);
  return tex;
}

/** Roller shutter loading-dock door: horizontal slat lines, off-white. */
export function rollerDoorTexture(): THREE.Texture {
  const key = "roller-door";
  const cached = cache.get(key);
  if (cached) return cached;

  const w = 256, h = 256;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#d8d6cf";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "rgba(0,0,0,0.22)";
  ctx.lineWidth = 2;
  const slats = 14;
  for (let i = 0; i <= slats; i++) {
    const y = (h / slats) * i;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }
  ctx.fillStyle = "rgba(0,0,0,0.08)";
  for (let i = 0; i < slats; i++) {
    const y = (h / slats) * i;
    ctx.fillRect(0, y, w, 3);
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  cache.set(key, tex);
  return tex;
}
