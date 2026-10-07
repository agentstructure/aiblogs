// Read-only health check of the live sites: crawls every internal page, checks every link,
// clicks every on-page button, and records page errors, failed requests and broken links.
// Signup endpoints are only sent an invalid address, so nothing is written to subscriber lists.
//
//   node scripts/sitecheck.mjs > report.md

import { chromium } from 'playwright';

const SITES = ['https://defensestocks.org/', 'https://capitalraising.org/',
               'https://gamingstocks.org/', 'https://beforethebreakout.net/'];
const MAX_PAGES = 80;
const PAUSE_MS = 3000;   // Hostinger rate-limits fast crawlers (HTTP 429), so go slowly
const sleep = ms => new Promise(r => setTimeout(r, ms));
const SIGNUP = {
  'defensestocks.org': ['/subscribers-api.php'],
  'capitalraising.org': ['/subscribe.php'],
  'gamingstocks.org': ['/subscribe.php'],
  'beforethebreakout.net': ['/subscribers-api.php', '/api/subscribe.php'],
};

const out = [];
const log = (s = '') => out.push(s);

async function status(url, method = 'HEAD') {
  try {
    const r = await fetch(url, { method, redirect: 'follow', headers: { 'User-Agent': 'aiblogs-sitecheck/1.0' },
                                 signal: AbortSignal.timeout(20000) });
    if (method === 'HEAD' && (r.status === 405 || r.status === 403)) return status(url, 'GET');
    return r.status;
  } catch (e) { return `error: ${e.cause?.code || e.name}`; }
}

async function checkSite(browser, start) {
  const origin = new URL(start).origin, host = new URL(start).host;
  const queue = [start], seen = new Set(), problems = [], external = new Map(), pages = [];
  const ctx = await browser.newContext({ userAgent: 'Mozilla/5.0 aiblogs-sitecheck/1.0' });
  while (queue.length && seen.size < MAX_PAGES) {
    const url = queue.shift().split('#')[0];
    if (seen.has(url)) continue;
    seen.add(url);
    await sleep(PAUSE_MS);
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', e => errs.push(`JS error: ${e.message.slice(0, 160)}`));
    page.on('console', m => { if (m.type() === 'error') errs.push(`console: ${m.text().slice(0, 160)}`); });
    page.on('requestfailed', r => errs.push(`failed request: ${r.url().slice(0, 120)} (${r.failure()?.errorText})`));
    page.on('response', r => { if (r.status() >= 400 && r.url().startsWith(origin)) errs.push(`HTTP ${r.status()}: ${r.url().slice(0, 120)}`); });
    page.on('dialog', d => { errs.push(`popup: "${d.message().slice(0, 100)}"`); d.dismiss().catch(() => {}); });
    let code;
    for (let attempt = 0; attempt < 3; attempt++) {
      errs.length = 0;
      try {
        const resp = await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
        code = resp?.status();
      } catch (e) { code = `load failed: ${e.message.split('\n')[0].slice(0, 100)}`; }
      if (code !== 429) break;
      await sleep(60000);
    }
    pages.push([url, code]);
    if (code !== 200) problems.push(`${url} → ${code}`);
    if (code === 200 && /html/.test(await page.evaluate(() => document.contentType).catch(() => ''))) {
      const links = await page.$$eval('a[href]', as => as.map(a => [a.href, (a.textContent || '').trim().slice(0, 40)]));
      for (const [href, text] of links) {
        if (!/^https?:/.test(href)) continue;
        const u = new URL(href);
        if (u.origin === origin) {
          if (!/\.(pdf|png|jpe?g|webp|svg|zip|xml|json|txt)$/i.test(u.pathname)) queue.push(u.href);
          else if (!external.has(u.href)) external.set(u.href, { text, from: url });
        } else if (!external.has(u.href)) external.set(u.href, { text, from: url });
      }
      // Click every visible button / onclick element that doesn't submit a form or leave the page.
      const count = await page.$$eval('button, [onclick], [role=button]', els => els.length);
      let clicked = 0;
      for (let i = 0; i < count && clicked < 40; i++) {
        const el = (await page.$$('button, [onclick], [role=button]'))[i];
        if (!el) continue;
        const info = await el.evaluate(e => ({
          visible: !!(e.offsetWidth || e.offsetHeight), submit: (e.type === 'submit') || !!e.closest('form'),
          text: (e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 30) }));
        if (!info.visible || info.submit) continue;
        clicked++;
        const before = page.url();
        try { await el.click({ timeout: 3000 }); await page.waitForTimeout(400); }
        catch (e) { errs.push(`button "${info.text}" could not be clicked`); }
        if (page.url().split('#')[0] !== before.split('#')[0]) {
          queue.push(page.url());
          await page.goto(before, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});
        }
      }
      // Signup forms present on this page
      const forms = await page.$$eval('input[type=email], input[name*=email i]', els => els.length);
      if (forms) pages[pages.length - 1].push(`${forms} email field(s)`);
    }
    for (const e of new Set(errs)) if (!/ 429|status of 429/.test(e)) problems.push(`${url}: ${e}`);
    await page.close();
  }
  await ctx.close();
  // Links to files and other sites
  const broken = [];
  for (const [href, { text, from }] of external) {
    await sleep(href.startsWith(origin) ? PAUSE_MS : 200);
    const s = await status(href);
    if (typeof s !== 'number' || s >= 400) broken.push(`"${text}" → ${href} (${s}) on ${from}`);
  }
  // Signup endpoints: invalid address only
  const signup = [];
  for (const path of SIGNUP[host] || []) {
    await sleep(PAUSE_MS);
    try {
      const r = await fetch(origin + path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'User-Agent': 'aiblogs-sitecheck/1.0' },
                                             body: JSON.stringify({ email: 'not-an-email', source: 'sitecheck' }), signal: AbortSignal.timeout(20000) });
      const body = (await r.text()).slice(0, 120).replace(/\s+/g, ' ');
      signup.push(`${path}: HTTP ${r.status} ${body}`);
    } catch (e) { signup.push(`${path}: ${e.name}`); }
  }

  log(`## ${host}`);
  log(`Pages checked: ${pages.length}, external/file links checked: ${external.size}`);
  log('');
  log('### Pages');
  for (const p of pages) log(`- ${p[1]} ${p[0]}${p[2] ? ' (' + p[2] + ')' : ''}`);
  log('');
  log(`### Problems on pages (${problems.length})`);
  for (const p of problems) log(`- ${p}`);
  log('');
  log(`### Broken links (${broken.length})`);
  for (const b of broken) log(`- ${b}`);
  log('');
  log('### Signup endpoint (sent an invalid address)');
  for (const s of signup) log(`- ${s}`);
  log('');
}

const browser = await chromium.launch();
for (const s of SITES) { await checkSite(browser, s); await sleep(60000); }
await browser.close();
console.log(out.join('\n'));
