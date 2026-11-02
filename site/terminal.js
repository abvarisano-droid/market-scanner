/* Scanner terminal: the landing's top panel (2026-11-01, grok). UI only, no engine changes.
   Every number, path and log line comes from the committed scan files and range.js (the same bootstrap the
   replay uses). The only made up part is motion: the gentle sway of the paths, the pulse and the particles.
   That is labeled "Illustrative motion" on screen. Canvas 2D, no dependencies. Reduced motion gets one still frame. */
(function () {
  "use strict";
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var CUR = null, RP = null;
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function pc(v, d) { return v == null || v !== v ? "n/a" : (v >= 0 ? "+" : "") + (v * 100).toFixed(d == null ? 1 : d) + "%"; }
  function money(v) { return v == null ? "n/a" : v >= 1000 ? v.toFixed(0) : v.toFixed(2); }
  function range() {
    if (window.RANGE) return Promise.resolve(window.RANGE);
    if (!RP) RP = new Promise(function (ok, no) { var s = document.createElement("script"); s.src = "range.js?v=1"; s.onload = function () { ok(window.RANGE); }; s.onerror = no; document.head.appendChild(s); });
    return RP;
  }
  function gauge(id, label) {
    return '<div class="tmg"><svg viewBox="0 0 120 66" aria-hidden="true"><path class="tmgt" d="M10 60a50 50 0 0 1 100 0"/><path class="tmgv" id="' + id + 'a" pathLength="100" d="M10 60a50 50 0 0 1 100 0"/></svg>' +
      '<b class="tmnum" id="' + id + '">0%</b><span class="tml">' + label + "</span></div>";
  }
  function shell() {
    return '<div class="tm" id="tm"><div class="tmhead"><span class="tml"><i class="tmdot"></i>Range terminal <span id="tmt">&middot;</span></span>' +
      '<button type="button" class="tmpause" id="tmp" aria-pressed="false">Pause motion</button></div>' +
      '<div class="tmchart"><canvas id="tmc" role="img" aria-label="Recent price candles, then a fan of 20 trading day paths drawn from the stock\'s own past daily moves." aria-describedby="tmdesc"></canvas><span class="sr" id="tmdesc"></span>' +
      '<span class="tmtag tmnow">Now</span><span class="tmtag tmill">Illustrative motion, not market data</span></div>' +
      '<div class="tmgrid"><div class="tmcol tmmet"><span class="tml">Last close</span><b class="tmbig tmnum" id="tmlast">0.00</b>' +
      '<span class="tmrng">Range, 20d (bootstrap)</span><div class="tmq"><span><span class="tml">10th</span><b class="tmnum" id="tm10">n/a</b></span><span><span class="tml">Median</span><b class="tmnum" id="tm50">n/a</b></span><span><span class="tml">90th</span><b class="tmnum" id="tm90">n/a</b></span></div>' +
      '<div class="tmeq" id="tmeq" aria-label="Index moves on the latest scan day" role="img"></div><div class="tmrow"><span class="tml">Regime</span><span class="tmbadge" id="tmreg">n/a</span></div></div>' +
      '<div class="tmcol tmgau"><div class="tmgs">' + gauge("tmg1", "Paths ending up") + gauge("tmg2", "Replay hits") + gauge("tmg3", "Passed checks") + "</div>" +
      '<div class="tmfr" id="tmfr"></div></div>' +
      '<div class="tmcol tmlog"><span class="tml">Scan log</span><div class="tmlogv" aria-label="Scan log" role="region" tabindex="0"><div class="tmlogin" id="tmlog"></div></div></div></div>' +
      '<p class="tmnote">Paths: a bootstrap of the stock\'s own past daily moves over 20 trading days, demeaned. A range of typical moves, not a forecast. Not investment advice.</p></div>';
  }
  function kv(o) {
    return "{" + Object.keys(o).map(function (k) { return '<span class="k">"' + esc(k) + '"</span>:<span class="v">' + esc(typeof o[k] === "string" ? '"' + o[k] + '"' : String(o[k])) + "</span>"; }).join(",") + "}";
  }
  function stop() { if (CUR) { CUR.dead = true; cancelAnimationFrame(CUR.raf); if (CUR.io) CUR.io.disconnect(); window.removeEventListener("resize", CUR.rs); if (CUR.vis) document.removeEventListener("visibilitychange", CUR.vis); CUR = null; } }

  function mount(host, L, t, ch) {
    stop();
    if (!host.querySelector('#tm')) host.innerHTML = shell();
    var me = { dead: false, raf: 0, paused: false, seen: true }; CUR = me;
    document.getElementById("tmt").textContent = "\u00b7 " + t;
    var f = L.funnel.mispricing, hz = L.horizons.mispricing;
    /* equalizer: real 1 day index moves, scaled to the largest */
    var mx = 0.0001; L.indexes.forEach(function (i) { if (i.chg_1d != null) mx = Math.max(mx, Math.abs(i.chg_1d)); });
    document.getElementById("tmeq").innerHTML = L.indexes.map(function (i) {
      var v = i.chg_1d || 0; return '<i class="' + (v < 0 ? "dn" : "up") + '" style="--s:' + Math.max(0.04, Math.abs(v) / mx).toFixed(3) + '" title="' + esc(i.name + " " + pc(i.chg_1d)) + '"></i>';
    }).join("");
    document.getElementById("tmfr").innerHTML = [["Picks", f.picks + "/" + f.scored], ["Bullish", hz.counts.Bullish + "/" + f.scored], ["Bearish", hz.counts.Bearish + "/" + f.scored], ["Indexes", String(Object.keys(L.funnel.by_index).length)]]
      .map(function (x) { return '<span><span class="tml">' + x[0] + '</span><b class="tmnum">' + x[1] + "</b></span>"; }).join("");
    function idle() { return new Promise(function (ok) { var go = function () { requestAnimationFrame(function () { setTimeout(ok, 0); }); };
      if (window.requestIdleCallback) requestIdleCallback(go, { timeout: 2500 }); else setTimeout(go, 600); }); }
    idle().then(range).then(function (R) {
      if (me.dead || !document.getElementById("tm10")) return;
      var dc = ch.dc, k = dc.length - 1, sim = R.simulate(dc, k, 20, t + "|today20"), reg = R.regime(dc, k), sm = { hits: 0, rounds: [] };
      /* same rounds and seeds as RANGE.summary, without its 252 day run that this panel does not use */
      R.roundDays(dc).forEach(function (kk, j) { var r = R.replay(dc, t, j, kk); if (r.hit) sm.hits++; sm.rounds.push(r); });
      var nR = sm.rounds.length, hitPct = nR ? sm.hits / nR : 0, passPct = f.passed_checks / f.universe;
      document.getElementById("tm10").textContent = money(sim.p10);
      document.getElementById("tm50").textContent = money(sim.p50);
      document.getElementById("tm90").textContent = money(sim.p90);
      document.getElementById("tmdesc").textContent = "Range over 20 trading days from " + sim.n + " bootstrap paths: 10th percentile " + money(sim.p10) + ", median " + money(sim.p50) + ", 90th percentile " + money(sim.p90) + ". " + sim.upPct + "% of paths end up.";
      var rb = document.getElementById("tmreg"); rb.textContent = reg.label; rb.classList.toggle("trend", reg.label === "TRENDING");
      /* log: real scan facts as JSON lines */
      var lines = [kv({ scan: L.asof, universe: f.universe, passed: f.passed_checks, scored: f.scored, picks: f.picks })];
      lines.push(kv({ range: t, days: 20, paths: sim.n, p10: +sim.p10.toFixed(2), p50: +sim.p50.toFixed(2), p90: +sim.p90.toFixed(2), up: sim.upPct + "%", regime: reg.label }));
      sm.rounds.forEach(function (r, j) { lines.push(kv({ replay: j + 1, start: +r.start.toFixed(2), p10: +r.p10.toFixed(2), p90: +r.p90.toFixed(2), real: +r.real.toFixed(2), inside: r.hit })); });
      L.indexes.forEach(function (i) { lines.push(kv({ index: i.name, chg_1d: pc(i.chg_1d) })); });
      hz.top_bull.slice(0, 5).forEach(function (r) { lines.push(kv({ lens: "mispricing", call: "Bullish", ticker: r.ticker, score: Math.round(r.score) })); });
      hz.top_bear.slice(0, 5).forEach(function (r) { lines.push(kv({ lens: "mispricing", call: "Bearish", ticker: r.ticker, score: Math.round(r.score) })); });
      (L.sectors || []).forEach(function (s) { lines.push(kv({ sector: s.name, n: s.n, rel_1w: pc(s.rel_1w) })); });
      var body = lines.map(function (l) { return "<p>" + l + "</p>"; }).join("");
      var lg = document.getElementById("tmlog"); lg.innerHTML = body + '<div aria-hidden="true">' + body + "</div>";
      lg.style.setProperty("--dur", Math.max(20, lines.length * 2.2) + "s");
      /* count up once to the real values, then hold */
      var targets = [["tmlast", ch.last || dc[k], money], ["tmg1", sim.upPct / 100, null, "tmg1a"], ["tmg2", hitPct, null, "tmg2a", sm.hits + "/" + nR], ["tmg3", passPct, null, "tmg3a"]];
      var t0 = performance.now();
      function setNums(p) {
        if (me.dead || !document.getElementById("tmlast")) return;
        targets.forEach(function (x) {
          var v = x[1] * p, el = document.getElementById(x[0]);
          if (x[2]) el.textContent = x[2](v);
          else { el.textContent = (p >= 1 && x[4]) ? x[4] : Math.round(v * 100) + "%"; document.getElementById(x[3]).style.strokeDashoffset = (100 - v * 100).toFixed(1); }
        });
      }
      if (reduce) setNums(1); else (function tick(now) { var p = Math.min(1, (now - t0) / 1400); p = 1 - Math.pow(1 - p, 3); setNums(p); if (p < 1 && !me.dead) requestAnimationFrame(tick); })(t0);
      chart(me, ch, sim);
    }).catch(function (e) { if (window.console) console.warn("terminal", e); });
    var pb = document.getElementById("tmp");
    if (reduce) { pb.hidden = true; host.querySelector(".tm").classList.add("still"); }
    pb.addEventListener("click", function () {
      me.paused = !me.paused; pb.setAttribute("aria-pressed", String(me.paused)); pb.textContent = me.paused ? "Play motion" : "Pause motion";
      host.querySelector(".tm").classList.toggle("still", me.paused); if (!me.paused && me.go) me.go();
    });
  }

  function chart(me, ch, sim) {
    var cv = document.getElementById("tmc"), ctx = cv.getContext("2d"), W, H, dpr, G;
    var nC = Math.min(ch.c.length, 44), o0 = ch.c.length - nC;
    function layout() {
      dpr = Math.min(window.devicePixelRatio || 1, 2); W = cv.clientWidth; H = cv.clientHeight;
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var narrow = W < 600, xNow = Math.round(W * (narrow ? 0.46 : 0.5)), nP = narrow ? 14 : 26;
      /* pick paths at evenly spaced end ranks so the fan shows the whole spread */
      var ends = []; for (var p = 0; p < sim.n; p++) ends.push([sim.cum[p * sim.w + sim.h], p]);
      ends.sort(function (a, b) { return a[0] - b[0]; });
      var paths = []; for (var i = 0; i < nP; i++) { var e = ends[Math.round((i + 0.5) / nP * (sim.n - 1))], o = e[1] * sim.w, pts = [];
        for (var s = 0; s <= sim.h; s++) pts.push(sim.start * Math.exp(sim.cum[o + s])); paths.push({ pts: pts, up: e[0] >= 0, ph: i * 1.7 }); }
      var lo = Infinity, hi = -Infinity;
      for (i = o0; i < ch.c.length; i++) { lo = Math.min(lo, ch.l[i] || ch.c[i]); hi = Math.max(hi, ch.h[i] || ch.c[i]); }
      paths.forEach(function (q) { q.pts.forEach(function (v) { lo = Math.min(lo, v); hi = Math.max(hi, v); }); });
      var pad = (hi - lo) * 0.08, top = 34, bot = H - 26;
      G = { xNow: xNow, step: (W - xNow - 52 - (ctx.font = "12px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace", Math.max(ctx.measureText(money(sim.p90)).width, ctx.measureText(money(sim.p10)).width))) / sim.h, cw: (xNow - 16) / nC, paths: paths, Y: function (v) { return bot - (v - lo + pad) / (hi - lo + 2 * pad) * (bot - top); }, top: top, bot: bot };
    }
    function pathXY(q, s, t) {
      var sway = reduce ? 0 : Math.sin(t * 0.0009 + q.ph + s * 0.35) * 2.2 * (s / sim.h);
      return [G.xNow + s * G.step, G.Y(q.pts[s]) + sway];
    }
    function stroke(q, t) {
      ctx.beginPath(); var a = pathXY(q, 0, t); ctx.moveTo(a[0], a[1]);
      for (var s = 1; s <= sim.h; s++) { var b = pathXY(q, s, t), m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]; ctx.quadraticCurveTo(a[0], a[1], m[0], m[1]); a = b; }
      ctx.lineTo(a[0], a[1]); ctx.stroke();
    }
    function draw(t) {
      ctx.clearRect(0, 0, W, H);
      /* past candles, faint */
      for (var i = 0; i < nC; i++) {
        var j = o0 + i, x = 16 + (i + 0.5) * G.cw, up = ch.c[j] >= ch.o[j], col = up ? "rgba(52,224,214," : "rgba(255,122,69,";
        ctx.strokeStyle = col + ".35)"; ctx.beginPath(); ctx.moveTo(x, G.Y(ch.h[j])); ctx.lineTo(x, G.Y(ch.l[j])); ctx.stroke();
        var y1 = G.Y(Math.max(ch.o[j], ch.c[j])), y2 = G.Y(Math.min(ch.o[j], ch.c[j]));
        ctx.fillStyle = col + ".28)"; ctx.fillRect(x - G.cw * 0.3, y1, G.cw * 0.6, Math.max(1, y2 - y1));
      }
      var cyc = reduce ? 0.3 : (t % 4200) / 4200, beamA = reduce ? 0.7 : 0.6 + 0.25 * Math.sin(t * 0.002);
      /* paths: wide faint glow then a thin core */
      ctx.globalCompositeOperation = "lighter"; ctx.lineCap = "round";
      G.paths.forEach(function (q) {
        var c = q.up ? "52,224,214" : "255,122,69";
        ctx.strokeStyle = "rgba(" + c + ",.07)"; ctx.lineWidth = 5; stroke(q, t);
        ctx.strokeStyle = "rgba(" + c + ",.5)"; ctx.lineWidth = 1.1; stroke(q, t);
      });
      /* particles with fading trails travel the paths after each pulse */
      if (!reduce && cyc > 0.14 && cyc < 0.96) {
        var u = (cyc - 0.14) / 0.82;
        G.paths.forEach(function (q, n) {
          var c = q.up ? "120,245,236" : "255,160,110";
          for (var k = 0; k < 7; k++) { var uu = u - k * 0.022; if (uu <= 0) break; var sf = uu * sim.h, s0 = Math.floor(sf), fr = sf - s0, a = pathXY(q, s0, t), b = pathXY(q, Math.min(sim.h, s0 + 1), t);
            ctx.fillStyle = "rgba(" + c + "," + (0.9 * (1 - k / 7) * (1 - Math.max(0, u - 0.85) / 0.15)).toFixed(3) + ")";
            ctx.beginPath(); ctx.arc(a[0] + (b[0] - a[0]) * fr, a[1] + (b[1] - a[1]) * fr, 1.8 - k * 0.18, 0, 6.2832); ctx.fill(); }
        });
      }
      /* the now beam, fading top and bottom */
      var yN = G.Y(sim.start), gb = ctx.createLinearGradient(0, G.top - 20, 0, G.bot + 10);
      gb.addColorStop(0, "rgba(52,224,214,0)"); gb.addColorStop(0.5, "rgba(52,224,214," + (0.55 * beamA).toFixed(3) + ")"); gb.addColorStop(1, "rgba(52,224,214,0)");
      ctx.fillStyle = gb; ctx.fillRect(G.xNow - 7, G.top - 20, 14, G.bot - G.top + 30);
      gb = ctx.createLinearGradient(0, G.top - 20, 0, G.bot + 10); gb.addColorStop(0, "rgba(200,255,250,0)"); gb.addColorStop(0.5, "rgba(200,255,250," + beamA.toFixed(3) + ")"); gb.addColorStop(1, "rgba(200,255,250,0)");
      ctx.fillStyle = gb; ctx.fillRect(G.xNow - 0.75, G.top - 20, 1.5, G.bot - G.top + 30);
      /* pulse ring (ease out) and node flash */
      if (!reduce && cyc < 0.5) { var e = 1 - Math.pow(1 - cyc / 0.5, 3); ctx.strokeStyle = "rgba(120,245,236," + (0.7 * (1 - e)).toFixed(3) + ")"; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.arc(G.xNow, yN, 6 + e * 70, 0, 6.2832); ctx.stroke(); }
      var fl = reduce ? 0 : Math.max(0, 1 - cyc / 0.12);
      var rg = ctx.createRadialGradient(G.xNow, yN, 0, G.xNow, yN, 22 + 14 * fl); rg.addColorStop(0, "rgba(160,255,248," + (0.55 + 0.4 * fl).toFixed(3) + ")"); rg.addColorStop(1, "rgba(52,224,214,0)");
      ctx.fillStyle = rg; ctx.beginPath(); ctx.arc(G.xNow, yN, 36, 0, 6.2832); ctx.fill();
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = "#eafffd"; ctx.beginPath(); ctx.arc(G.xNow, yN, 3.4 + 1.6 * fl, 0, 6.2832); ctx.fill();
      /* real end labels: 90th, median, 10th of all 1000 paths */
      ctx.font = "12px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"; ctx.textBaseline = "middle";
      var lw = Math.max.apply(null, [sim.p90, sim.p50, sim.p10].map(function (v) { return ctx.measureText(money(v)).width; })), xe = Math.min(G.xNow + sim.h * G.step + 6, W - 34 - lw - 6), ys = [[sim.p90, "90th "], [sim.p50, "Med "], [sim.p10, "10th "]].map(function (r) { return [G.Y(r[0]), r]; });
      for (var m = 1; m < 3; m++) if (ys[m][0] - ys[m - 1][0] < 14) ys[m][0] = ys[m - 1][0] + 14;
      ys.forEach(function (r) { ctx.fillStyle = "rgba(160,170,180,.85)"; ctx.fillText(r[1][1], xe, r[0]); ctx.fillStyle = "#e9c46a"; ctx.fillText(money(r[1][0]), xe + 34, r[0]); });
    }
    layout();
    var last = 0;
    function loop(now) {
      me.raf = 0; if (me.dead) return;
      draw(now); last = now;
      if (!reduce && !me.paused && me.seen && !document.hidden) me.raf = requestAnimationFrame(loop);
    }
    me.go = function () { if (!me.raf && !me.dead) me.raf = requestAnimationFrame(loop); };
    me.rs = function () { if (me.dead) return; layout(); draw(last || performance.now()); };
    window.addEventListener("resize", me.rs);
    if (window.IntersectionObserver) { me.io = new IntersectionObserver(function (en) { me.seen = en[0].isIntersecting; if (me.seen) me.go(); }); me.io.observe(cv); }
    me.vis = function () { if (!document.hidden && CUR === me) me.go(); };
    document.addEventListener("visibilitychange", me.vis);
    me.go();
  }
  window.TERM = { mount: mount, stop: stop, shell: shell };
})();
