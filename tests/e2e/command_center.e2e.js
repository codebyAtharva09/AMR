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
  const browser = await chromium.launch({ executablePath: exe, headless: true });
  const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !IGNORED.some(r => r.test(m.text()))) errors.push('console: ' + m.text()); });
  const results = {};

  // ---------------------------------------------------------------- Command Center
  await page.goto(BASE + '/command-center', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelectorAll('#fleetTbl tr[data-r]').length > 0, null, { timeout: 15000 });
  for (const n of [3, 5, 10, 15]) {
    await page.selectOption('#cRobots', String(n));
    await page.selectOption('#cPreset', 'NORMAL');
    await page.click('#tabs button[data-tab="controls"]');
    await page.click('#cApply');
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
  // canvas drawn with robots
  const canvasOk = await page.evaluate(() => { const c = document.getElementById('twin'); return c.width > 100 && c.height > 100; });
  assert(canvasOk, 'digital twin canvas sized');
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
  await page.screenshot({ path: process.env.SHOT || '/tmp/command_center_e2e.png' });

  // ---------------------------------------------------------------- classic dashboard (baseline checklist, current UI)
  const p2 = await browser.newPage();
  p2.on('pageerror', e => errors.push('classic pageerror: ' + e.message));
  await p2.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await p2.waitForFunction(() => document.querySelectorAll('#fleet .robot-card, #fleet > *').length >= 1, null, { timeout: 15000 });
  results.classic_fleet_cards = await p2.locator('#fleet > *').count();
  results.classic_cmd_link = await p2.locator('#navCommandCenter').count();
  assert(results.classic_cmd_link === 1, 'classic dashboard links to command center');

  await browser.close();
  if (errors.length) { console.error(JSON.stringify({ results, errors }, null, 1)); process.exit(1); }
  console.log(JSON.stringify({ ok: true, results }, null, 1));
})().catch(e => { console.error(e); process.exit(1); });
