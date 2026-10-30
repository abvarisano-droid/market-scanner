(function () {
  "use strict";
  var HZ = [["mispricing", "Mispricing"], ["short_term", "Short-term"], ["swing", "Swing"]];
  var HZNAME = { mispricing: "Mispricing", short_term: "Short-term", swing: "Swing" };
  var HZHELP = { mispricing: "Valuation vs peers, quality, the Street gap and recent stretch. Score runs from -100 (looks rich) to +100 (looks cheap).", short_term: "Price vs its 20-day average, 5 and 10 day momentum, RSI and volume. Score 0 to 100.", swing: "50 and 200-day averages, their slope, 3-month strength vs the S&amp;P 500 and distance from the 52-week high. Score 0 to 100." };
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var app = document.getElementById("app");
  var S = { latest: null, track: null, hz: "mispricing", raf: 0 };

  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function pct(x, d) { return (x >= 0 ? "+" : "") + (x * 100).toFixed(d == null ? 1 : d) + "%"; }
  function sgn(v) { v = Math.round(v); return S.hz === "mispricing" ? (v > 0 ? "+" : "") + v : String(v); }
  function cls(l) { return l === "Bullish" ? "" : l === "Bearish" ? "bear" : "neutral"; }
  function load(u) { return fetch(u).then(function (r) { if (!r.ok) throw new Error(u); return r.json(); }); }

  /* ---------- funnel dot field ---------- */
  function funnel(canvas, f, counters, stages) {
    cancelAnimationFrame(S.raf);
    var ctx = canvas.getContext("2d");
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var W = canvas.clientWidth, H = canvas.clientHeight;
    canvas.width = W * dpr; canvas.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var N = Math.min(f.universe, W < 600 ? 260 : 460);
    var scale = function (v) { return Math.max(v > 0 ? 1 : 0, Math.round(N * v / f.universe)); };
    var cut = [N, scale(f.passed_checks), scale(f.scored), scale(f.picks)];
    var seed = 7; function rnd() { seed = (seed * 16807) % 2147483647; return seed / 2147483647; }
    var order = []; for (var i = 0; i < N; i++) order.push(i);
    for (var j = N - 1; j > 0; j--) { var k = Math.floor(rnd() * (j + 1)); var t = order[j]; order[j] = order[k]; order[k] = t; }
    var dots = [];
    for (i = 0; i < N; i++) {
      var rank = order[i], lvl = rank < cut[3] ? 3 : rank < cut[2] ? 2 : rank < cut[1] ? 1 : 0;
      dots.push({ x: rnd(), y: rnd(), ph: rnd() * 6.28, lvl: lvl, r: 1.2 + rnd() * 1.4 });
    }
    var vals = [f.universe, f.passed_checks, f.scored, f.picks];
    var DUR = 1.7, HOLD = 0.9;
    function setStage(s, p) {
      for (var q = 0; q < 4; q++) {
        stages[q].classList.toggle("on", q <= s);
        var from = q === 0 ? 0 : vals[q - 1], base = q < s ? 1 : q === s ? p : 0;
        counters[q].textContent = q === 0 && s === 0 ? Math.round(vals[0] * p).toLocaleString() : Math.round(vals[q] * (q <= s ? (q === s ? p : 1) : 0)).toLocaleString();
        void from; void base;
      }
    }
    function draw(time, stage, p) {
      ctx.clearRect(0, 0, W, H);
      var padX = 18, padY = 18, gw = W - padX * 2, gh = H - padY * 2;
      for (var n = 0; n < dots.length; n++) {
        var d = dots[n];
        /* survivors of the current stage gather toward the centre as stages advance */
        var surv = d.lvl >= stage;
        var pull = stage === 0 ? 0 : (surv ? 0.0 : 0);
        var bx = padX + d.x * gw, by = padY + d.y * gh;
        var drift = reduce ? 0 : 3;
        var x = bx + Math.sin(time * 0.0006 + d.ph) * drift, y = by + Math.cos(time * 0.0005 + d.ph * 1.3) * drift;
        var a;
        if (stage === 0) a = 0.28 + 0.55 * p;
        else { var prev = d.lvl >= stage - 1; a = d.lvl >= stage ? 0.85 : (d.lvl === stage - 1 ? 0.85 - 0.77 * p : 0.08); if (!prev) a = 0.08; }
        var picked = d.lvl === 3 && stage === 3;
        var r = d.r * (picked ? 1 + 1.2 * p : 1) + pull;
        if (picked) { ctx.shadowColor = "#d4af37"; ctx.shadowBlur = 14 * p; } else ctx.shadowBlur = 0;
        ctx.fillStyle = picked ? "rgba(236,200,80," + a + ")" : surv ? "rgba(212,175,55," + a * 0.75 + ")" : "rgba(150,142,120," + a + ")";
        ctx.beginPath(); ctx.arc(x, y, r, 0, 6.2832); ctx.fill();
      }
      ctx.shadowBlur = 0;
    }
    if (reduce) { setStage(3, 1); draw(0, 3, 1); return; }
    var t0 = performance.now();
    (function loop(now) {
      var el = (now - t0) / 1000, total = DUR * 4 + HOLD, tt = el % (total + 2.4);
      var s, p;
      if (tt >= total) { s = 3; p = 1; } else { s = Math.min(3, Math.floor(tt / DUR)); p = Math.min(1, (tt - s * DUR) / (DUR * 0.8)); p = 1 - Math.pow(1 - p, 3); }
      if (el < total + 2.4 || true) { setStage(s, p); draw(now, s, p); }
      S.raf = requestAnimationFrame(loop);
    })(t0);
  }

  /* ---------- views ---------- */
  function listHtml(rows, kind) {
    if (!rows.length) return '<p class="note">No names on this list today.</p>';
    return rows.map(function (r, i) {
      return '<div class="row ' + kind + '"><div class="r1"><span class="rank">' + (i + 1) + '</span>' +
        '<a class="tk" href="#/lookup/' + encodeURIComponent(r.ticker) + '">' + esc(r.ticker) + '</a>' +
        '<span class="nm">' + esc(r.name) + '</span><span class="chip">' + esc(r.label) + '</span></div>' +
        '<div class="bar"><div class="track"><div class="fill" style="width:' + (r.bar != null ? r.bar : r.score) + '%"></div></div><span class="sc">' + sgn(r.score) + '</span></div>' +
        '<ul class="why">' + r.reasons.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>" + (r.thesis ? '<p class="note thesis">' + esc(r.thesis) + "</p>" : "") + "</div>";
    }).join("");
  }

  function home() {
    var L = S.latest;
    var f = L.funnel[S.hz];
    var tabs = HZ.map(function (h) {
      return '<button class="tab" role="tab" data-hz="' + h[0] + '" aria-selected="' + (S.hz === h[0]) + '">' + h[1] + "</button>";
    }).join("");
    var h = L.horizons[S.hz];
    var body = '<p class="note">' + HZHELP[S.hz] + '</p><div class="cols fade"><div class="bull"><div class="listhead"><h3>Bullish</h3><span class="label">' + h.counts.Bullish + ' of ' + f.scored + ' scored</span></div>' + listHtml(h.top_bull, "bull") +
      '</div><div class="bear"><div class="listhead"><h3>Bearish</h3><span class="label">' + h.counts.Bearish + ' of ' + f.scored + ' scored</span></div>' + listHtml(h.top_bear, "bear") + "</div></div>";
    var nIdx = Object.keys(L.funnel.by_index).length;
    var chips = L.indexes.map(function (i) { return '<span class="ix"><span class="label">' + esc(i.name) + '</span><b class="' + (i.chg_1d < 0 ? "neg" : "pos") + '">' + pct(i.chg_1d) + "</b></span>"; }).join("");
    app.innerHTML =
      '<section class="hero"><span class="label">Daily scan across ' + nIdx + ' indexes &middot; as of ' + esc(L.asof) + "</span>" +
      '<h1>' + f.universe.toLocaleString() + ' stocks in.<br><em>' + f.picks + ' setups out.</em></h1>' +
      '<p class="lede">Every weekday after the close we run each stock from the major indexes through data checks, a valuation model and a handful of plain price rules, then rank the strongest bullish and bearish setups. Every call is logged and graded against the S&amp;P 500, in public.</p>' +
      '<div class="field"><canvas id="cv" aria-label="Animated field of dots. Each dot is a stock, narrowing from the full universe to the final picks." role="img"></canvas>' +
      '<div class="stages">' + ["Universe", "Passed checks", "Scored", "Picks"].map(function (n) { return '<div class="stage"><div class="k">' + n + '</div><div class="n">0</div></div>'; }).join("") + "</div></div></section>" +
      '<div class="ixs">' + chips + '</div><div class="tabs" role="tablist">' + tabs + "</div>" + body;
    var cv = document.getElementById("cv");
    funnel(cv, f, [].slice.call(app.querySelectorAll(".stage .n")), [].slice.call(app.querySelectorAll(".stage")));
    [].forEach.call(app.querySelectorAll(".tab"), function (b) {
      b.addEventListener("click", function () { S.hz = b.getAttribute("data-hz"); home(); });
    });
  }

  function spark(vals) {
    var w = 600, h = 110, mn = Math.min.apply(null, vals), mx = Math.max.apply(null, vals), sp = mx - mn || 1;
    var pts = vals.map(function (v, i) { return (i / (vals.length - 1) * w).toFixed(1) + "," + (h - 8 - (v - mn) / sp * (h - 16)).toFixed(1); });
    return '<svg class="spark" viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="none" role="img" aria-label="Last ' + vals.length + ' closes"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#d4af37" stop-opacity=".28"/><stop offset="1" stop-color="#d4af37" stop-opacity="0"/></linearGradient></defs>' +
      '<polygon points="0,' + h + " " + pts.join(" ") + " " + w + "," + h + '" fill="url(#g)"/><polyline points="' + pts.join(" ") + '" fill="none" stroke="#d4af37" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>';
  }

  function hzCard(name, r, signed) {
    if (!r) return '<div class="hz"><span class="label">' + name + '</span><p class="note">Not enough data to score this view.</p></div>';
    return '<div class="hz"><span class="label">' + name + '</span><div class="r1" style="margin-top:8px"><span class="big ' + (r.label === "Bearish" ? "neg" : "") + '">' + (signed && r.score > 0 ? "+" : "") + Math.round(r.score) + '</span><span class="chip ' + cls(r.label) + '">' + esc(r.label) + "</span></div>" +
      '<div class="bar" style="margin-left:0"><div class="track"><div class="fill ' + cls(r.label) + '" style="width:' + (signed ? (r.score + 100) / 2 : r.score) + '%"></div></div></div>' +
      '<ul class="why" style="margin-left:0">' + r.reasons.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul></div>";
  }

  function lookup(sym) {
    var keys = Object.keys(S.latest.lookup).sort();
    var picks = S.latest.horizons.mispricing.top_bull.slice(0, 4).concat(S.latest.horizons.mispricing.top_bear.slice(0, 3)).map(function (r) { return r.ticker; });
    app.innerHTML = '<section class="hero"><span class="label">Ticker lookup</span><h1>Look up <em>any</em> name.</h1>' +
      '<p class="lede">Type a ticker to see the mispricing score, both technical horizons, the reasons behind each score, and its last 60 closes.</p>' +
      '<form class="search" id="f" autocomplete="off"><input type="search" id="q" list="tl" placeholder="Try ' + esc(picks[0] || "a ticker") + '" aria-label="Ticker" value="' + esc(sym || "") + '"><datalist id="tl">' + keys.map(function (k) { return '<option value="' + esc(k) + '">'; }).join("") + "</datalist></form>" +
      '<div class="sugg">' + picks.map(function (p) { return '<button type="button" data-t="' + esc(p) + '">' + esc(p) + "</button>"; }).join("") + '</div><div id="res"></div></section>';
    var q = document.getElementById("q"), res = document.getElementById("res");
    function show(v) {
      v = (v || "").trim().toUpperCase();
      if (!S.latest.lookup[v] && S.latest.lookup[v.replace(".", "-")]) v = v.replace(".", "-");
      if (!v) { res.innerHTML = ""; return; }
      var r = S.latest.lookup[v];
      if (!r) { res.innerHTML = '<p class="note">No scored data for "' + esc(v) + '" in the latest scan. It may be outside the universe or failed a data check.</p>'; return; }
      res.innerHTML = '<div class="card fade"><span class="label">' + esc((r.i ? r.i + " | " : "") + (r.s || "")) + "</span><h2>" + esc(v) + " <span style=\"color:var(--muted);font-size:.5em\">" + esc(r.n) + '</span></h2><div class="meta"><span class="label">Last close ' + r.c.toFixed(2) + '</span><span class="label">As of ' + esc(S.latest.asof) + "</span></div>" +
        spark(r.spark) + '<div class="hzs">' + hzCard("Mispricing", r.mp, true) + hzCard("Short-term", r.st) + hzCard("Swing", r.sw) + '</div><p class="note">Mechanical rules on past data, not a forecast. Not investment advice.</p></div>';
    }
    q.addEventListener("input", function () { show(q.value); });
    document.getElementById("f").addEventListener("submit", function (e) { e.preventDefault(); show(q.value); });
    [].forEach.call(app.querySelectorAll(".sugg button"), function (b) { b.addEventListener("click", function () { q.value = b.getAttribute("data-t"); show(q.value); }); });
    show(sym);
  }

  function track() {
    var T = S.track, C = 2 * Math.PI * 96, p = Math.min(1, T.trading_days / T.min_days), noise = T.trading_days < T.min_days;
    function stat(k) {
      var L = T.by_lens[k] || { calls: 0, windows: {} }, best = null;
      Object.keys(L.windows).forEach(function (w) { if (L.windows[w].graded > 0) best = w; });
      var v = best ? L.windows[best] : null;
      return '<div class="stat"><span class="label">' + HZNAME[k] + '</span><div class="v">' + (!v || v.avg_excess_pct == null ? "None yet" : (v.avg_excess_pct >= 0 ? "+" : "") + v.avg_excess_pct.toFixed(2) + "%") + '</div><span class="label">' + (v ? "avg vs S&amp;P 500 over " + best + " days &middot; " + v.hit_rate_pct + "% hit rate &middot; " + v.graded + " graded" : "nothing graded yet") + " &middot; " + L.calls + " logged</span></div>";
    }
    var rows = T.graded.slice().sort(function (a, b) { return a.date < b.date ? 1 : a.date > b.date ? -1 : 0; }).slice(0, 40);
    var tbl = rows.length ? '<div class="tw"><table><thead><tr><th>Called</th><th>Name</th><th>View</th><th>Call</th><th>Window</th><th>Stock</th><th>Vs S&amp;P</th></tr></thead><tbody>' +
      rows.map(function (g) {
        return "<tr><td>" + esc(g.date) + '</td><td><a class="tk" href="#/lookup/' + encodeURIComponent(g.ticker) + '">' + esc(g.ticker) + "</a></td><td>" + esc(HZNAME[g.lens] || g.lens) + "</td><td>" + esc(g.label) + '</td><td class="num">' + g.window + 'd</td><td class="num">' + pct(g.stock_return) + '</td><td class="num ' + (g.excess >= 0 ? "pos" : "neg") + '">' + pct(g.excess) + "</td></tr>";
      }).join("") + "</tbody></table></div>" : '<p class="note">No graded calls yet. A call is graded from the next trading day\'s close, over 5, 20 and 60 trading days, so the first results appear after a week.</p>';
    app.innerHTML = '<section class="hero"><span class="label">Track record</span><h1>' + (noise ? "Still <em>noise.</em>" : "Enough days <em>to read.</em>") + "</h1>" +
      '<p class="lede">Every published pick is logged with its date, then graded against the S&amp;P 500 from the next trading day\'s close, over 5, 20 and 60 trading days. A Bullish call wins by beating the index, a Bearish call by lagging it. ' + esc(T.note) + "</p>" +
      '<div class="ringwrap"><div class="ring"><svg viewBox="0 0 220 220" aria-hidden="true"><circle cx="110" cy="110" r="96" fill="none" stroke="#1a1812" stroke-width="8"/><circle class="p" id="pr" cx="110" cy="110" r="96" fill="none" stroke="#d4af37" stroke-width="8" stroke-linecap="round" stroke-dasharray="' + C + '" stroke-dashoffset="' + C + '"/></svg>' +
      '<div class="c" role="img" aria-label="' + esc(noise ? "still noise" : "readable") + ", " + T.trading_days + " of " + T.min_days + ' trading days"><b>' + T.trading_days + '</b><span class="label">of ' + T.min_days + ' trading days</span><span class="label" style="color:var(--gold);margin-top:6px">' + (noise ? "still noise" : "readable") + "</span></div></div>" +
      '<div class="stats">' + stat("mispricing") + stat("short_term") + stat("swing") + '<div class="stat"><span class="label">Calls logged</span><div class="v">' + T.calls_logged.toLocaleString() + '</div><span class="label">' + T.pending + " pending</span></div>" +
      '<div class="stat"><span class="label">Rule</span><div class="v" style="font-size:18px">Nothing is hidden or removed after the fact.</div></div></div></div></section>' +
      '<section><h2>Graded calls</h2><p class="lede" style="margin-top:6px">Most recent 40. Neutral names are never called. Results this early are not evidence of skill.</p>' + tbl + "</section>";
    var pr = document.getElementById("pr");
    if (reduce) pr.style.strokeDashoffset = C * (1 - p);
    else requestAnimationFrame(function () { requestAnimationFrame(function () { pr.style.strokeDashoffset = C * (1 - p); }); });
  }

  /* ---------- router ---------- */
  function route() {
    cancelAnimationFrame(S.raf);
    var h = location.hash.replace(/^#\/?/, ""), parts = h.split("/"), pg = parts[0] || "home";
    [].forEach.call(document.querySelectorAll("nav a"), function (a) { a.classList.toggle("on", a.getAttribute("data-nav") === pg); });
    if (pg === "lookup") lookup(decodeURIComponent(parts[1] || ""));
    else if (pg === "track") track();
    else home();
    window.scrollTo(0, 0);
  }

  Promise.all([load("data/latest.json"), load("data/track.json")]).then(function (r) {
    S.latest = r[0]; S.track = r[1];
    document.getElementById("asof").textContent = "(latest scan " + S.latest.asof + ")";
    if (S.latest.banner) { var b = document.getElementById("banner"); b.textContent = S.latest.banner; b.hidden = false; }
    window.addEventListener("hashchange", route);
    var rt; window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(function () { if (!location.hash || location.hash === "#/") home(); }, 250); });
    route();
  }).catch(function () {
    app.innerHTML = '<section class="hero"><h1>Scan data <em>unavailable.</em></h1><p class="lede">The data files could not be loaded. Try again later. Not investment advice.</p></section>';
  });
})();
