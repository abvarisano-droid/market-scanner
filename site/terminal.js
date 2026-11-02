/* Scanner terminal: the landing's top panel. Redesigned 2026-11-02 (grok) to the "candle forecast" reference Ashton sent:
   chart on top ending at a cyan playhead, a fan of simulated paths flowing right, three panels below.
   Every number, path and log line comes from the committed scan files, the chart file and range.js (the same
   bootstrap the replay uses). The fan is a simulated range of typical moves, never a forecast, and the stage says so.
   The only made up part is motion (the slow flow along the paths and the pulse), labeled "Illustrative motion".
   Colors: cyan for paths ending more than 2% up, orange for within 2%, red for more than 2% down. No gold or yellow.
   Canvas 2D, no dependencies. Reduced motion or Pause gets one still frame. */
(function () {
  "use strict";
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var CUR = null, RP = null, BAND = 0.02;
  var C_UP = "0,229,255", C_FLAT = "255,122,69", C_DN = "255,77,109", MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace";
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function pc(v, d) { return v == null || v !== v ? "n/a" : (v >= 0 ? "+" : "") + (v * 100).toFixed(d == null ? 1 : d) + "%"; }
  function money(v) { return v == null || v !== v ? "n/a" : v >= 1000 ? Math.round(v).toLocaleString("en-US") : v.toFixed(2); }
  function range() {
    if (window.RANGE) return Promise.resolve(window.RANGE);
    if (!RP) RP = new Promise(function (ok, no) { var s = document.createElement("script"); s.src = "range.js?v=1"; s.onload = function () { ok(window.RANGE); }; s.onerror = no; document.head.appendChild(s); });
    return RP;
  }
  function bar(id, label, cls) {
    return '<div class="tmpb ' + cls + '"><span class="tml">' + label + '</span><span class="tmpbt"><i id="' + id + 'b"></i></span><b class="tmnum" id="' + id + '">0%</b></div>';
  }
  function shell() {
    return '<div class="tm" id="tm"><div class="tmhead"><span class="tml"><i class="tmdot"></i>Range terminal <span id="tmt">&middot;</span></span>' +
      '<button type="button" class="tmpause" id="tmp" aria-pressed="false">Pause motion</button></div>' +
      '<div class="tmchart"><canvas id="tmc" role="img" aria-label="Recent price candles up to today, then a fan of simulated 20 trading day paths drawn from the stock\'s own past daily moves." aria-describedby="tmdesc"></canvas><span class="sr" id="tmdesc"></span>' +
      '<span class="tmtag tmsim">Simulated range, not a prediction</span><span class="tmtag tmill">Illustrative motion</span></div>' +
      '<div class="tmgrid">' +
      '<div class="tmcol tmmet"><div class="tmrow tmsp"><span class="tml">Last close</span><span class="tmbadge" id="tmreg" aria-live="off">n/a</span></div>' +
      '<b class="tmbig tmnum" id="tmlast">0.00</b>' +
      '<div class="tmhl"><span class="tml">52w low <b class="tmnum" id="tmlo52">n/a</b></span><span class="tmhlt"><i id="tmhlm"></i></span><span class="tml">high <b class="tmnum" id="tmhi52">n/a</b></span></div>' +
      '<span class="tml tmsub">Simulated paths, 20 trading days, by end</span>' +
      bar("tpu", "Up &gt;2%", "up") + bar("tpf", "Within 2%", "flat") + bar("tpd", "Down &gt;2%", "dn") +
      '<span class="tml tmsub" id="tmregh">Regime</span></div>' +
      '<div class="tmcol tmev"><div class="tmhls"><span><span class="tml">20d high</span><b class="tmnum" id="tmh20">n/a</b></span><span><span class="tml">20d low</span><b class="tmnum" id="tml20">n/a</b></span>' +
      '<span><span class="tml">Sim 90th</span><b class="tmnum" id="tm90">n/a</b></span><span><span class="tml">Sim 10th</span><b class="tmnum" id="tm10">n/a</b></span></div>' +
      '<span class="tml">Event log</span><div class="tmlogv" aria-label="Event log" role="region" tabindex="0"><div class="tmlogin" id="tmev"></div></div></div>' +
      '<div class="tmcol tmlog"><span class="tml">Diagnostics</span><div class="tmlogv tmterm" aria-label="Diagnostics" role="region" tabindex="0"><div class="tmlogin" id="tmlog"></div></div></div></div>' +
      '<p class="tmnote">Fan: 1,000 simulated paths that resample the stock\'s own past daily moves for 20 trading days, demeaned so the center is no change. A range of typical moves, not a forecast. The thick orange line is the median path. Not investment advice.</p></div>';
  }
  function kv(o) {
    return "{" + Object.keys(o).map(function (k) { return '<span class="k">"' + esc(k) + '"</span>:<span class="v">' + esc(typeof o[k] === "string" ? '"' + o[k] + '"' : String(o[k])) + "</span>"; }).join(",") + "}";
  }
  function stop() { if (CUR) { CUR.dead = true; cancelAnimationFrame(CUR.raf); clearInterval(CUR.rt); if (CUR.io) CUR.io.disconnect(); window.removeEventListener("resize", CUR.rs); if (CUR.vis) document.removeEventListener("visibilitychange", CUR.vis); CUR = null; } }
  function ymd(ch, i) { var d = new Date(ch.d0 + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + ch.x[i]); return d.toISOString().slice(0, 10); }
  function scroller(el, body, n) { el.innerHTML = body + '<div aria-hidden="true">' + body + "</div>"; el.style.setProperty("--dur", Math.max(24, n * 2.6) + "s"); }

  function mount(host, L, t, ch) {
    stop();
    if (!host.querySelector("#tm")) host.innerHTML = shell();
    var me = { dead: false, raf: 0, paused: false, seen: true }; CUR = me;
    var tm = host.querySelector(".tm");
    document.getElementById("tmt").textContent = "\u00b7 " + t;
    var f = L.funnel.mispricing, hz = L.horizons.mispricing, n = ch.c.length, last = ch.last || ch.c[n - 1];
    document.getElementById("tmlo52").textContent = money(ch.lo52);
    document.getElementById("tmhi52").textContent = money(ch.hi52);
    if (ch.hi52 > ch.lo52) document.getElementById("tmhlm").style.left = (Math.max(0, Math.min(1, (last - ch.lo52) / (ch.hi52 - ch.lo52))) * 100).toFixed(1) + "%";
    var h20 = -Infinity, l20 = Infinity; for (var i = Math.max(0, n - 20); i < n; i++) { h20 = Math.max(h20, ch.h[i]); l20 = Math.min(l20, ch.l[i]); }
    document.getElementById("tmh20").textContent = money(h20); document.getElementById("tml20").textContent = money(l20);
    /* event log: real dated closes from the chart file, newest first, plus the scan itself */
    var ev = ['<p><time>' + esc(L.asof) + '</time> <span class="v">SCAN</span> ' + f.picks + " picks from " + f.scored + " scored</p>"], hi = -Infinity, lo = Infinity, rows = [];
    for (i = Math.max(1, n - 60); i < n; i++) {
      var ch1 = ch.c[i] / ch.c[i - 1] - 1, tag = ch1 >= 0 ? '<span class="v">UP</span>' : '<span class="d">DN</span>', note = "";
      if (ch.h[i] > hi && i > n - 60) { if (hi > -Infinity) note = " new 60d high"; hi = ch.h[i]; }
      if (ch.l[i] < lo && i > n - 60) { if (lo < Infinity) note = " new 60d low"; lo = ch.l[i]; }
      rows.push("<p><time>" + ymd(ch, i) + "</time> " + tag + " " + esc(t) + " " + money(ch.c[i]) + " " + pc(ch1) + esc(note) + "</p>");
    }
    ev = ev.concat(rows.reverse().slice(0, 24));
    scroller(document.getElementById("tmev"), ev.join(""), ev.length);
    function idle() { return new Promise(function (ok) { var go = function () { requestAnimationFrame(function () { setTimeout(ok, 0); }); };
      if (window.requestIdleCallback) requestIdleCallback(go, { timeout: 2500 }); else setTimeout(go, 600); }); }
    idle().then(range).then(function (R) {
      if (me.dead || !document.getElementById("tm10")) return;
      var dc = ch.dc, k = dc.length - 1, sim = R.simulate(dc, k, 20, t + "|today20"), reg = R.regime(dc, k), rounds = [], hits = 0;
      R.roundDays(dc).forEach(function (kk, j) { var r = R.replay(dc, t, j, kk); if (r.hit) hits++; rounds.push(r); });
      var cu = 0, cf = 0, cd = 0;
      for (var p = 0; p < sim.n; p++) { var e = Math.exp(sim.cum[p * sim.w + sim.h]) - 1; if (e > BAND) cu++; else if (e < -BAND) cd++; else cf++; }
      document.getElementById("tm10").textContent = money(sim.p10);
      document.getElementById("tm90").textContent = money(sim.p90);
      document.getElementById("tmdesc").textContent = "Simulated range over 20 trading days from " + sim.n + " paths: 10th percentile " + money(sim.p10) + ", median " + money(sim.p50) + ", 90th percentile " + money(sim.p90) + ". " + Math.round(cu / sim.n * 100) + "% end more than 2% up, " + Math.round(cd / sim.n * 100) + "% more than 2% down. Not a forecast.";
      /* regime badge: steps through the replay rounds' regimes, then holds on today's */
      var rb = document.getElementById("tmreg"), rh = document.getElementById("tmregh"), seq = rounds.map(function (r, j) { return [r.regime.label, "Regime at replay " + (j + 1) + " start"]; }).concat([[reg.label, "Regime today (50d slope and path efficiency)"]]);
      function setReg(s) { rb.textContent = s[0]; rb.classList.toggle("trend", s[0] === "TRENDING"); rh.textContent = s[1]; }
      setReg(seq[seq.length - 1]);
      if (!reduce && seq.length > 1) { var si = 0; me.rt = setInterval(function () { if (me.paused || document.hidden) return; si = (si + 1) % (seq.length + 2); setReg(seq[Math.min(si, seq.length - 1)]); }, 2600); }
      var lines = ["$ scan --asof " + L.asof, kv({ universe: f.universe, passed: f.passed_checks, scored: f.scored, picks: f.picks }),
        "$ range --ticker " + t + " --days 20 --paths " + sim.n, kv({ p10: +sim.p10.toFixed(2), p50: +sim.p50.toFixed(2), p90: +sim.p90.toFixed(2), up: cu, flat: cf, down: cd, regime: reg.label }),
        "$ replay --rounds " + rounds.length];
      rounds.forEach(function (r, j) { lines.push(kv({ round: j + 1, start: +r.start.toFixed(2), p10: +r.p10.toFixed(2), p90: +r.p90.toFixed(2), real: +r.real.toFixed(2), inside: r.hit })); });
      lines.push(kv({ inside_band: hits + "/" + rounds.length, by_chance: "about 8 in 10" }), "$ indexes --1d");
      L.indexes.forEach(function (x) { lines.push(kv({ index: x.name, chg_1d: pc(x.chg_1d) })); });
      lines.push("$ mispricing --top 5");
      hz.top_bull.slice(0, 5).forEach(function (r) { lines.push(kv({ call: "Bullish", ticker: r.ticker, score: Math.round(r.score) })); });
      hz.top_bear.slice(0, 5).forEach(function (r) { lines.push(kv({ call: "Bearish", ticker: r.ticker, score: Math.round(r.score) })); });
      scroller(document.getElementById("tmlog"), lines.map(function (l) { return "<p>" + (l.charAt(0) === "$" ? '<span class="v">' + esc(l) + "</span>" : l) + "</p>"; }).join(""), lines.length);
      var vals = [["tmlast", last, money], ["tpu", cu / sim.n], ["tpf", cf / sim.n], ["tpd", cd / sim.n]], t0 = performance.now();
      function setNums(q) {
        if (me.dead || !document.getElementById("tmlast")) return;
        vals.forEach(function (x) { var v = x[1] * q, el = document.getElementById(x[0]);
          if (x[2]) el.textContent = x[2](v); else { el.textContent = Math.round(v * 100) + "%"; document.getElementById(x[0] + "b").style.transform = "scaleX(" + v.toFixed(3) + ")"; } });
      }
      if (reduce) setNums(1); else (function tick(now) { var q = Math.min(1, (now - t0) / 1400); q = 1 - Math.pow(1 - q, 3); setNums(q); if (q < 1 && !me.dead) requestAnimationFrame(tick); })(t0);
      chart(me, ch, sim, t);
    }).catch(function (e) { if (window.console) console.warn("terminal", e); });
    var pb = document.getElementById("tmp");
    if (reduce) { pb.hidden = true; tm.classList.add("still"); }
    pb.addEventListener("click", function () {
      me.paused = !me.paused; pb.setAttribute("aria-pressed", String(me.paused)); pb.textContent = me.paused ? "Play motion" : "Pause motion";
      tm.classList.toggle("still", me.paused); if (!me.paused && me.go) me.go();
    });
  }

  function chart(me, ch, sim, t) {
    var cv = document.getElementById("tmc"), ctx = cv.getContext("2d"), W, H, dpr, G;
    function layout() {
      dpr = Math.min(window.devicePixelRatio || 1, 2); W = cv.clientWidth; H = cv.clientHeight;
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var narrow = W < 600, nC = Math.min(ch.c.length, narrow ? 22 : 60), o0 = ch.c.length - nC, xNow = Math.round(W * (narrow ? 0.34 : 0.52)), nP = narrow ? 36 : 90;
      var ends = []; for (var p = 0; p < sim.n; p++) ends.push([sim.cum[p * sim.w + sim.h], p]);
      ends.sort(function (a, b) { return a[0] - b[0]; });
      var paths = []; for (var i = 0; i < nP; i++) { var e = ends[Math.round((i + 0.5) / nP * (sim.n - 1))], o = e[1] * sim.w, pts = [], r = Math.exp(e[0]) - 1;
        for (var s = 0; s <= sim.h; s++) pts.push(sim.start * Math.exp(sim.cum[o + s])); paths.push({ pts: pts, c: r > BAND ? C_UP : r < -BAND ? C_DN : C_FLAT, ph: (i * 0.618) % 1 }); }
      var lo = Infinity, hi = -Infinity;
      for (i = o0; i < ch.c.length; i++) { lo = Math.min(lo, ch.l[i] || ch.c[i]); hi = Math.max(hi, ch.h[i] || ch.c[i]); }
      paths.forEach(function (q) { q.pts.forEach(function (v) { lo = Math.min(lo, v); hi = Math.max(hi, v); }); });
      ctx.font = "600 13px " + MONO; var bw = Math.max(ctx.measureText(money(sim.p50)).width, 70) + 20;
      var pad = (hi - lo) * 0.08, top = 40, bot = H - 34;
      G = { narrow: narrow, nC: nC, o0: o0, xNow: xNow, bw: bw, step: (W - xNow - bw - 18) / sim.h, cw: (xNow - 14) / nC, paths: paths, top: top, bot: bot,
        Y: function (v) { return bot - (v - lo + pad) / (hi - lo + 2 * pad) * (bot - top); } };
    }
    function pt(q, s, tt, ph) { var sway = reduce || ph == null ? 0 : Math.sin(tt * 0.0005 + ph * 6.28 + s * 0.3) * 1.8 * (s / sim.h); return [G.xNow + s * G.step, G.Y(q[s]) + sway]; }
    function trace(q, tt, ph) {
      ctx.beginPath(); var a = pt(q, 0, tt, ph); ctx.moveTo(a[0], a[1]);
      for (var s = 1; s <= sim.h; s++) { var b = pt(q, s, tt, ph); ctx.quadraticCurveTo(a[0], a[1], (a[0] + b[0]) / 2, (a[1] + b[1]) / 2); a = b; }
      ctx.lineTo(a[0], a[1]);
    }
    function rr(x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
    function draw(tt) {
      ctx.clearRect(0, 0, W, H);
      /* candles up to today: cyan up, orange down */
      for (var i = 0; i < G.nC; i++) {
        var j = G.o0 + i, x = 14 + (i + 0.5) * G.cw, up = ch.c[j] >= ch.o[j], col = up ? "rgba(" + C_UP + "," : "rgba(" + C_FLAT + ",", fade = 0.35 + 0.55 * i / G.nC;
        ctx.strokeStyle = col + (0.7 * fade).toFixed(2) + ")"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x, G.Y(ch.h[j])); ctx.lineTo(x, G.Y(ch.l[j])); ctx.stroke();
        var y1 = G.Y(Math.max(ch.o[j], ch.c[j])), y2 = G.Y(Math.min(ch.o[j], ch.c[j]));
        ctx.fillStyle = col + (0.75 * fade).toFixed(2) + ")"; ctx.fillRect(x - G.cw * 0.32, y1, G.cw * 0.64, Math.max(1, y2 - y1));
      }
      /* the fan: thin faint strokes, then a slow dashed stream flowing along them */
      ctx.globalCompositeOperation = "lighter"; ctx.lineCap = "round";
      G.paths.forEach(function (q) {
        ctx.setLineDash([]); ctx.strokeStyle = "rgba(" + q.c + ",.16)"; ctx.lineWidth = 1; trace(q.pts, tt, q.ph); ctx.stroke();
        if (!reduce) { ctx.setLineDash([14, 46]); ctx.lineDashOffset = -((tt * 0.018 + q.ph * 60) % 60); ctx.strokeStyle = "rgba(" + q.c + ",.55)"; ctx.lineWidth = 1.2; trace(q.pts, tt, q.ph); ctx.stroke(); }
      });
      ctx.setLineDash([]);
      /* highlighted median path, thick orange glow */
      ctx.strokeStyle = "rgba(" + C_FLAT + ",.18)"; ctx.lineWidth = 9; trace(sim.med, 0); ctx.stroke();
      ctx.strokeStyle = "rgba(" + C_FLAT + ",.95)"; ctx.lineWidth = 2.6; trace(sim.med, 0); ctx.stroke();
      /* playhead beam */
      var beam = reduce ? 0.7 : 0.6 + 0.2 * Math.sin(tt * 0.0012), gb = ctx.createLinearGradient(0, G.top - 30, 0, G.bot + 20);
      gb.addColorStop(0, "rgba(" + C_UP + ",0)"); gb.addColorStop(0.5, "rgba(" + C_UP + "," + (0.35 * beam).toFixed(3) + ")"); gb.addColorStop(1, "rgba(" + C_UP + ",0)");
      ctx.fillStyle = gb; ctx.fillRect(G.xNow - 8, G.top - 30, 16, G.bot - G.top + 50);
      ctx.fillStyle = "rgba(200,250,255," + (0.9 * beam).toFixed(3) + ")"; ctx.fillRect(G.xNow - 0.75, G.top - 30, 1.5, G.bot - G.top + 50);
      var yN = G.Y(sim.start), pu = reduce ? 0 : (tt % 3600) / 3600;
      if (!reduce) { var e = 1 - Math.pow(1 - pu, 3); ctx.strokeStyle = "rgba(" + C_UP + "," + (0.6 * (1 - e)).toFixed(3) + ")"; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.arc(G.xNow, yN, 6 + e * 26, 0, 6.2832); ctx.stroke(); }
      var rg = ctx.createRadialGradient(G.xNow, yN, 0, G.xNow, yN, 26); rg.addColorStop(0, "rgba(" + C_UP + ",.7)"); rg.addColorStop(1, "rgba(" + C_UP + ",0)");
      ctx.fillStyle = rg; ctx.beginPath(); ctx.arc(G.xNow, yN, 26, 0, 6.2832); ctx.fill();
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = "#e9fdff"; ctx.beginPath(); ctx.arc(G.xNow, yN, 4, 0, 6.2832); ctx.fill();
      /* node tooltip */
      ctx.font = "500 12px " + MONO; ctx.textBaseline = "middle";
      var l1 = "NODE " + t + " T0", l2 = "SIMULATED", tw = Math.max(ctx.measureText(l1).width, ctx.measureText(l2).width + 16) + 20, tx = Math.max(6, G.xNow - tw - 14), ty = Math.max(6, yN - 66);
      rr(tx, ty, tw, 46, 8); ctx.fillStyle = "rgba(4,10,16,.88)"; ctx.fill(); ctx.strokeStyle = "rgba(" + C_UP + ",.4)"; ctx.lineWidth = 1; ctx.stroke();
      ctx.fillStyle = "#cfe9ef"; ctx.fillText(l1, tx + 10, ty + 14);
      rr(tx + 10, ty + 24, ctx.measureText(l2).width + 14, 16, 4); ctx.fillStyle = "rgba(" + C_UP + ",.14)"; ctx.fill();
      ctx.fillStyle = "rgb(" + C_UP + ")"; ctx.fillText(l2, tx + 17, ty + 32);
      /* median end box on the right edge */
      var xm = G.xNow + sim.h * G.step, ym = G.Y(sim.p50), bx = Math.min(W - G.bw - 8, xm + 8), by = Math.max(G.top, Math.min(G.bot - 40, ym - 20));
      rr(bx, by, G.bw, 40, 8); ctx.fillStyle = "rgba(20,8,4,.9)"; ctx.fill(); ctx.strokeStyle = "rgba(" + C_FLAT + ",.85)"; ctx.lineWidth = 1.2; ctx.stroke();
      ctx.font = "500 12px " + MONO; ctx.fillStyle = "#c9b3a8"; ctx.fillText("MEDIAN END", bx + 10, by + 12);
      ctx.font = "600 13px " + MONO; ctx.fillStyle = "rgb(" + C_FLAT + ")"; ctx.fillText(money(sim.p50), bx + 10, by + 28);
    }
    layout();
    var lastT = 0;
    function loop(now) {
      me.raf = 0; if (me.dead) return;
      draw(now); lastT = now;
      if (!reduce && !me.paused && me.seen && !document.hidden) me.raf = requestAnimationFrame(loop);
    }
    me.go = function () { if (!me.raf && !me.dead) me.raf = requestAnimationFrame(loop); };
    me.rs = function () { if (me.dead) return; layout(); draw(lastT || performance.now()); };
    window.addEventListener("resize", me.rs);
    if (window.IntersectionObserver) { me.io = new IntersectionObserver(function (en) { me.seen = en[0].isIntersecting; if (me.seen) me.go(); }); me.io.observe(cv); }
    me.vis = function () { if (!document.hidden && CUR === me) me.go(); };
    document.addEventListener("visibilitychange", me.vis);
    me.go();
  }
  window.TERM = { mount: mount, stop: stop, shell: shell };
})();
