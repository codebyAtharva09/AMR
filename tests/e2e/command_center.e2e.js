// Dashboard E2E for the Fleet Command Center and the classic dashboard.
// Start the server first:  python3 main.py --mode dashboard   (or start_dashboard(port=8004))
// Run:  BASE_URL=http://127.0.0.1:8004 CHROMIUM_PATH=/path/to/chrome node tests/e2e/command_center.e2e.js
const { chromium } = require('playwright');

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8004';
const exe = process.env.CHROMIUM_PATH || undefined;
const IGNORED = [/fonts\.googleapis/, /favicon/, /ERR_TUNNEL_CONNECTION_FAILED/, /status of 404/];

function assert(cond, msg) { if (!cond) throw new Error('ASSERTION FAILED: ' + msg); }
async function post(page, body) {
  return page.evaluate(async (b) => (await fetch('/api/swarm/command', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) })).json(), body);
}
async function state(page) { return page.evaluate(async () => (await fetch('/api/swarm/state')).json()); }

(async () => {
  const browser = await chromium.launch({ executablePath: exe, headless: true, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !IGNORED.some(r => r.test(m.text()))) errors.push('console: ' + m.text()); });
  const results = {};

  // ---------------------------------------------------------------- Command Center
  await page.goto(BASE + '/command-center', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelectorAll('#fleetTbl tr[data-r]').length > 0 && document.querySelectorAll('#cPreset option').length > 0, null, { timeout: 15000 });
  for (const n of [3, 5, 10, 15]) {
    await page.click('#tabs button[data-tab="controls"]');
    await page.selectOption('#cRobots', String(n));
    await page.selectOption('#cPreset', 'NORMAL');
    await page.click('#cApply');
    await page.click('#tabs button[data-tab="fleet"]');
    await page.waitForFunction((k) => document.querySelectorAll('#fleetTbl tr[data-r]').length === k, n, { timeout: 15000 });
    results[`fleet_${n}`] = await page.locator('#fleetTbl tr[data-r]').count();
  }
  // start -> tick advances, pause -> tick stops
  await page.click('[data-cmd="start"]');
  await page.waitForTimeout(1500);
  const t1 = (await state(page)).tick;
  assert(t1 > 0, 'tick advances after start');
  await page.click('[data-cmd="pause"]');
  await page.waitForTimeout(600);
  const t2 = (await state(page)).tick;
  await page.waitForTimeout(900);
  const t3 = (await state(page)).tick;
  assert(t3 === t2, 'tick frozen while paused');
  results.tick_after_start = t1;
  // 3D digital twin (default view): WebGL canvas rendered, one robot model per AMR, click selects a cell
  const has3d = await page.evaluate(() => !!(window.SwarmTwin3D && window.SwarmTwin3D.supported));
  results.webgl = has3d;
  if (has3d) {
    await page.waitForFunction(() => window.twin3d && window.twin3d.robots.size > 0, null, { timeout: 15000 });
    results.twin3d_robots = await page.evaluate(() => window.twin3d.robots.size);
    assert(results.twin3d_robots === (await state(page)).robots.length, '3D twin shows every robot');
    const b3 = await page.locator('#twin3dCanvas').boundingBox();
    assert(b3 && b3.width > 300 && b3.height > 300, '3D canvas sized');
    await page.mouse.click(b3.x + b3.width * 0.5, b3.y + b3.height * 0.55);
    await page.waitForFunction(() => /Selected cell/.test(document.getElementById('cellInfo').textContent), null, { timeout: 10000 });
    results.cell_3d = await page.locator('#cellInfo').textContent();
    // camera presets and sensor toggle do not throw
    await page.click('[data-cam="top"]'); await page.click('#camSensors'); await page.click('[data-cam="iso"]');
  }
  // 2D view still works
  await page.click('#v2d');
  const canvasOk = await page.evaluate(() => { const c = document.getElementById('twin'); return c.width > 100 && c.height > 100 && getComputedStyle(c).display !== 'none'; });
  assert(canvasOk, '2D digital twin canvas sized');
  // disruption: block an aisle at a clicked cell
  const box = await page.locator('#twin').boundingBox();
  await page.mouse.click(box.x + box.width * 0.45, box.y + box.height * 0.40);
  await page.click('#tabs button[data-tab="controls"]');
  await page.click('[data-ev="block"]');
  await page.waitForTimeout(500);
  const sBlock = await state(page);
  assert(sBlock.blockages.length >= 1 || sBlock.events.some(e => e.kind === 'AISLE_BLOCKED'), 'blockage injected');
  // dead zone + resume
  await page.click('[data-ev="dead_zone"]');
  await page.click('[data-cmd="start"]');
  await page.waitForTimeout(2500);
  const sDz = await state(page);
  assert(sDz.dead_zones.length >= 1, 'dead zone visible in state');
  results.comm_modes = [...new Set(sDz.robots.map(r => r.comm_mode))];
  // AI tab and robot tab render
  await page.click('#tabs button[data-tab="ai"]');
  await page.waitForSelector('#riskTbl tr');
  const rid = sDz.robots[0].id;
  await page.click(`#tabs button[data-tab="fleet"]`);
  await page.click(`#fleetTbl tr[data-r="${rid}"]`);
  await page.click('#tabs button[data-tab="robot"]');
  await page.waitForFunction(() => document.getElementById('robotDetail').textContent.includes('Why this task'));
  // scenario builder
  await page.click('#tabs button[data-tab="builder"]');
  await page.selectOption('#bBase', 'blank');
  await page.fill('#bR', '4'); await page.fill('#bT', '8'); await page.fill('#bS', '3');
  await page.click('#bRun');
  await page.click('#tabs button[data-tab="fleet"]');
  await page.waitForFunction(() => document.querySelectorAll('#fleetTbl tr[data-r]').length === 4, null, { timeout: 15000 });
  results.builder_robots = 4;
  // benchmark panel
  await page.click('#tabs button[data-tab="bench"]');
  await page.waitForTimeout(1500);
  results.bench_bars = await page.locator('#benchSvg path').count();
  // guided demo starts
  await page.click('#tabs button[data-tab="controls"]');
  await page.click('#demoBtn');
  await page.waitForFunction(() => document.getElementById('demo').classList.contains('on'), null, { timeout: 15000 });
  results.demo_title = await page.locator('#demoTitle').textContent();
  await post(page, { action: 'stop_demo' });
  await post(page, { action: 'pause' });
  await page.click('#v3d');
  await page.screenshot({ path: process.env.SHOT || '/tmp/command_center_e2e.png' });

  // ---------------------------------------------------------------- root redirects to the Command Center
  results.root_redirect = await page.evaluate(async () => new URL((await fetch('/')).url).pathname);
  assert(results.root_redirect === '/command-center', '/ redirects to /command-center');
  results.classic_link = await page.locator('a.link').count();
  assert(results.classic_link === 0, 'no classic dashboard link');

  await browser.close();
  if (errors.length) { console.error(JSON.stringify({ results, errors }, null, 1)); process.exit(1); }
  console.log(JSON.stringify({ ok: true, results }, null, 1));
})().catch(e => { console.error(e); process.exit(1); });
