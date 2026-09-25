const { chromium } = require('playwright');
(async () => {
  const exe = process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
  const b = await chromium.launch({ executablePath: exe, headless: true });
  const p = await b.newPage({ viewport: { width: 1600, height: 1100 } });
  const errs = []; p.on('pageerror', e => errs.push('PAGEERR ' + e.message)); p.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()); });
  const url = process.argv[3] || 'http://127.0.0.1:8004/command-center';
  await p.goto(url, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(2500);
  if (process.argv[4]) await p.click(`#tabs button[data-tab="${process.argv[4]}"]`), await p.waitForTimeout(1500);
  await p.screenshot({ path: process.argv[2], fullPage: true });
  console.log(JSON.stringify({ errs }));
  await b.close();
})();
