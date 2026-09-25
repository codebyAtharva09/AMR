const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', headless: true, args:['--use-gl=swiftshader','--enable-webgl'] });
  const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
  const errs=[]; p.on('pageerror', e=>errs.push('PAGEERR '+e.message)); p.on('console', m=>{ if(m.type()==='error') errs.push('CONSOLE '+m.text())});
  await p.goto('http://127.0.0.1:8004/', { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(4000);
  await p.screenshot({ path: process.argv[2] || '/tmp/claude-0/dash.png', fullPage: false });
  const ids = await p.evaluate(()=>Array.from(document.querySelectorAll('[id]')).map(e=>e.id).slice(0,400));
  console.log(JSON.stringify({errs, n: ids.length, ids: ids.join(' ')}));
  await b.close();
})();
