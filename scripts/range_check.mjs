/* Browser checks for "Play the range" and the landing hero. Not part of CI (needs Playwright and a browser).
   Measures with no video recording running (a screencast costs main-thread time of its own).
   Usage: python3 -m http.server 8123 --directory site &  then  node scripts/range_check.mjs http://127.0.0.1:8123 [outdir]
   Checks: console errors, horizontal overflow, CLS, idle main thread after the run (ms of task time per s),
   reduced motion, keyboard reach, and that the panel numbers match a Node recomputation with site/range.js. */
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
const require = createRequire(import.meta.url);
let pw; try { pw = require("playwright"); } catch { pw = require("/opt/node22/lib/node_modules/playwright"); }
const R = require("../site/range.js");
const BASE = process.argv[2] || "http://127.0.0.1:8123", OUT = process.argv[3] || "";
const fmt = v => { const a = Math.abs(v), d = a >= 10000 ? 0 : a >= 1000 ? 1 : 2; return v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }); };
const results = [], fail = [];
const ok = (c, m) => { if (!c) fail.push(m); };
async function page(br, w, h, opts = {}) {
  const ctx = await br.newContext({ viewport: { width: w, height: h }, reducedMotion: opts.rm ? "reduce" : "no-preference", ...(opts.video ? { recordVideo: { dir: opts.video, size: { width: w, height: h } } } : {}) });
  const pg = await ctx.newPage(), errs = [];
  pg.on("console", m => { if (m.type() === "error") errs.push(m.text()); }); pg.on("pageerror", e => errs.push(e.message));
  const cdp = await ctx.newCDPSession(pg);
  await cdp.send("Performance.enable");
  if (opts.throttle) await cdp.send("Emulation.setCPUThrottlingRate", { rate: opts.throttle });
  await pg.addInitScript(() => {
    window.__cls = 0; window.__live = [];
    new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: "layout-shift", buffered: true });
    new MutationObserver(ms => { for (const m of ms) { const t = m.target.closest ? m.target.closest(".rg [role=status]") : m.target.parentElement && m.target.parentElement.closest(".rg [role=status]"); if (t && t.textContent) window.__live.push(t.textContent); } })
      .observe(document, { subtree: true, childList: true, characterData: true });
  });
  return { ctx, pg, errs, cdp };
}
async function idle(cdp, pg, ms = 3000) {
  const m = async () => Object.fromEntries((await cdp.send("Performance.getMetrics")).metrics.map(x => [x.name, x.value]));
  const a = await m(); await pg.waitForTimeout(ms); const b = await m();
  return (b.TaskDuration - a.TaskDuration) * 1000 / (ms / 1000);
}
const overflow = pg => pg.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
function expected(t, dc) { return R.summary(dc, t); }
const br = await pw.chromium.launch();
for (const [w, h, th] of [[390, 844, 4], [1280, 900, 0]]) {
  /* landing: one round autoplays */
  { const { ctx, pg, errs, cdp } = await page(br, w, h, { throttle: th });
    await pg.goto(BASE + "/#/"); await pg.waitForSelector(".rg .rgring.hit, .rg .rgring.miss", { timeout: 30000, state: "attached" });
    await pg.waitForTimeout(2500);
    const it = await idle(cdp, pg), cls = await pg.evaluate(() => window.__cls), ov = await overflow(pg);
    const t = await pg.evaluate(() => V5.data().then(d => V5.featured(d)));
    const dc = JSON.parse(readFileSync(new URL(`../site/data/charts/${t}.json`, import.meta.url))).dc, ex = expected(t, dc), r5 = ex.rounds[4];
    const fr = await pg.textContent(".rgfr"), live = await pg.evaluate(() => window.__live.join(" | "));
    ok(fr === (r5.hit ? "1/1" : "0/1"), `landing ${w} fraction ${fr}`);
    ok(live.includes(`${fmt(r5.p10)} to ${fmt(r5.p90)}`) && live.includes(r5.hit ? "HIT" : "MISS"), `landing ${w} live ${live}`);
    ok(errs.length === 0, `landing ${w} errors ${errs}`); ok(!ov, `landing ${w} overflow`); ok(cls < 0.001, `landing ${w} cls ${cls}`); ok(it < 20, `landing ${w} idle ${it}`);
    if (OUT) await pg.screenshot({ path: `${OUT}/landing-${w}.png` });
    results.push({ view: "landing", w, ticker: t, round5: r5.hit ? "HIT" : "MISS", cls: +cls.toFixed(4), idle_ms_per_s: +it.toFixed(1), errors: errs.length });
    await ctx.close(); }
  /* stock pages: full run on the first ticker, Next to the end on the others */
  for (const [i, t] of ["ABBV", "AJG", "0700.HK"].entries()) {
    const full = i === 0, { ctx, pg, errs, cdp } = await page(br, w, h, { throttle: th });
    await pg.goto(BASE + "/#/stock/" + encodeURIComponent(t)); await pg.waitForSelector(".cplot svg", { timeout: 30000 });
    await pg.locator(".tgplay").scrollIntoViewIfNeeded(); await pg.waitForTimeout(300);
    await pg.focus(".tgplay"); await pg.keyboard.press("Enter");
    await pg.waitForSelector(".rg .rgpill", { state: "attached" });
    const ex = expected(t, JSON.parse(readFileSync(new URL(`../site/data/charts/${t}.json`, import.meta.url))).dc);
    if (!full) { await pg.waitForSelector(".rg .rgring.hit, .rg .rgring.miss", { timeout: 30000, state: "attached" }); for (let k = 0; k < 5; k++) { await pg.click(".rgnext"); await pg.waitForTimeout(150); } }
    await pg.waitForFunction(() => /^TODAY/.test(document.querySelector(".rgpill").textContent) && document.querySelector(".rglog").textContent.includes("12-month range"), null, { timeout: 120000 });
    /* settle: a one-off garbage collection can land a few seconds after a long throttled run */
    await pg.waitForTimeout(6000);
    const it = await idle(cdp, pg), cls = await pg.evaluate(() => window.__cls), ov = await overflow(pg);
    const fr = await pg.textContent(".rgfr"), live = await pg.evaluate(() => window.__live.join(" | "));
    ok(fr === `${ex.hits}/5`, `${t} ${w} fraction ${fr} vs ${ex.hits}/5`);
    ex.rounds.forEach((r, j) => ok(live.includes(`Round ${j + 1} of 5: ${r.hit ? "HIT" : "MISS"}`) && live.includes(`(${fmt(r.p10)} to ${fmt(r.p90)})`), `${t} ${w} round ${j + 1}`));
    ok(live.includes(`12-month range ${fmt(ex.today.p10)} to ${fmt(ex.today.p90)}`), `${t} ${w} today`);
    /* keyboard: the stage buttons come next in tab order after the play pill */
    const tabs = []; await pg.focus(".tgplay"); for (let k = 0; k < 14; k++) { await pg.keyboard.press("Tab"); tabs.push(await pg.evaluate(() => document.activeElement.className)); }
    ok(tabs.some(c => /rgnext/.test(c)), `${t} ${w} keyboard ${tabs}`);
    ok(errs.length === 0, `${t} ${w} errors ${errs}`); ok(!ov, `${t} ${w} overflow`); ok(cls < 0.001, `${t} ${w} cls ${cls}`); ok(it < 20, `${t} ${w} idle ${it}`);
    if (OUT && full) await pg.locator(".chartbox").screenshot({ path: `${OUT}/stock-${t}-${w}.png` });
    results.push({ view: "stock", w, ticker: t, hits: fr, expected: `${ex.hits}/5`, cls: +cls.toFixed(4), idle_ms_per_s: +it.toFixed(1), errors: errs.length });
    await ctx.close();
  }
  /* reduced motion: final frame of each round, Next steps, nothing animates */
  { const { ctx, pg, errs, cdp } = await page(br, w, h, { rm: true });
    await pg.goto(BASE + "/#/stock/ABBV"); await pg.waitForSelector(".cplot svg"); await pg.click(".tgplay");
    await pg.waitForSelector(".rg .rgring.hit, .rg .rgring.miss", { state: "attached" });
    const anims = await pg.evaluate(() => document.getAnimations().length), pause = await pg.$(".rgpause");
    const f1 = await pg.textContent(".rgfr"); await pg.click(".rgnext"); await pg.waitForTimeout(200); const f2 = await pg.textContent(".rgfr");
    const it = await idle(cdp, pg, 2000);
    ok(anims === 0 && !pause && f1 === "1/1" && f2 === "2/2" && errs.length === 0 && it < 20, `reduced ${w} anims ${anims} ${f1} ${f2} idle ${it}`);
    if (OUT) await pg.locator(".chartbox").screenshot({ path: `${OUT}/stock-reduced-${w}.png` });
    results.push({ view: "reduced", w, anims, after_next: f2, idle_ms_per_s: +it.toFixed(1) });
    await ctx.close(); }
}
/* navigation: landing to scan and back must not break the router (regression for the S.hero clash), and
   leaving a page with an open replay must leave no listeners or observers behind (10 cycles) */
{ const { ctx, pg, errs } = await page(br, 1280, 900);
  await pg.addInitScript(() => {
    window.__vis = 0; window.__io = 0;
    const add = Document.prototype.addEventListener, rem = Document.prototype.removeEventListener;
    Document.prototype.addEventListener = function (t, f, o) { if (t === "visibilitychange") window.__vis++; return add.call(this, t, f, o); };
    Document.prototype.removeEventListener = function (t, f, o) { if (t === "visibilitychange") window.__vis--; return rem.call(this, t, f, o); };
    const IO = window.IntersectionObserver;
    window.IntersectionObserver = class extends IO { constructor(cb, o) { super(cb, o); window.__io++; this.__on = true; } disconnect() { if (this.__on) { window.__io--; this.__on = false; } return super.disconnect(); } };
  });
  const h1 = () => pg.waitForFunction(() => { const a = document.getElementById("app"); return a && !a.classList.contains("boot") && a.querySelector("h1"); }, null, { timeout: 15000 });
  await pg.goto(BASE + "/#/"); await pg.waitForSelector(".rg .rgpill", { state: "attached" }); await pg.waitForTimeout(800);
  for (const hsh of ["#/scan", "#/", "#/track", "#/scan", "#/lookup", "#/"]) { await pg.evaluate(x => { location.hash = x; }, hsh); await h1(); await pg.waitForTimeout(400); }
  ok(await pg.isVisible(".lcards"), "nav: landing did not render after scan round trips");
  await pg.click('nav a[href="#/track"]'); await h1(); ok(/track/.test(await pg.evaluate(() => location.hash)) && await pg.evaluate(() => !document.querySelector(".lcards")), "nav: clicks dead after leaving scan");
  const base = await pg.evaluate(() => [window.__vis, window.__io]);
  for (let k = 0; k < 10; k++) {
    await pg.evaluate(() => { location.hash = "#/stock/ABBV"; }); await pg.waitForSelector(".cplot svg"); await pg.click(".tgplay"); await pg.waitForSelector(".rg .rgpill", { state: "attached" }); await pg.waitForTimeout(300);
    await pg.evaluate(() => { location.hash = "#/track"; }); await h1(); await pg.waitForTimeout(200);
  }
  const after = await pg.evaluate(() => [window.__vis, window.__io, document.querySelectorAll(".rg").length]);
  ok(after[0] === base[0] && after[1] === base[1] && after[2] === 0, `leak: visibilitychange/IO/stages ${base} -> ${after}`);
  ok(errs.length === 0, `nav errors ${errs}`);
  results.push({ view: "nav+leak", listeners_before: base, after_10_cycles: after, errors: errs.length });
  await ctx.close(); }
await br.close();
console.log(JSON.stringify(results, null, 1));
console.log(fail.length ? "FAIL\n" + fail.join("\n") : "ALL CHECKS PASS");
process.exit(fail.length ? 1 : 0);
