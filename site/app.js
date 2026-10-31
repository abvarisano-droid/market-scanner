(function () {
  "use strict";
  var HZ = [["mispricing", "Mispricing"], ["short_term", "Short-term"], ["swing", "Swing"]];
  var HZNAME = { mispricing: "Mispricing", short_term: "Short-term", swing: "Swing" };
  var HZHELP = { mispricing: "Valuation vs peers, quality, the analyst consensus gap and recent stretch. Score runs from -100 (looks rich) to +100 (looks cheap).", short_term: "Price vs its 20-day average, 5 and 10 day momentum, RSI and volume. Score 0 to 100.", swing: "50 and 200-day averages, their slope, 3-month strength vs the S&amp;P 500 and distance from the 52-week high. Score 0 to 100." };
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var app = document.getElementById("app");
  var S = { latest: null, track: null, hz: "mispricing", raf: 0 };

  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function pct(x, d) { if (x == null || x !== x) return "n/a"; return (x >= 0 ? "+" : "") + (x * 100).toFixed(d == null ? 1 : d) + "%"; }
  function sgn(v) { v = Math.round(v); return S.hz === "mispricing" ? (v > 0 ? "+" : "") + v : String(v); }
  function cls(l) { return l === "Bullish" ? "" : l === "Bearish" ? "bear" : "neutral"; }
  function load(u) { return fetch(u).then(function (r) { if (!r.ok) throw new Error(u); return r.json(); }); }

  /* ---------- funnel dot field ---------- */
  var CAP = [
    function (v) { return v[0].toLocaleString() + " stocks from the major indexes enter the scan."; },
    function (v) { return v[1].toLocaleString() + " pass the data checks (enough history, fresh, liquid, sane values)."; },
    function (v) { return v[2].toLocaleString() + " get a score from the rules."; },
    function (v) { return v[3].toLocaleString() + " rank at the top as the day's setups."; }
  ];
  function funnel(canvas, f, counters, stages) {
    cancelAnimationFrame(S.raf); if (S.stop) S.stop();
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
    var cur = reduce ? 3 : 0, ts = performance.now(), timer = 0, desktop = window.innerWidth >= 760;
    function go(s, instant) { cur = Math.max(0, Math.min(3, s)); ts = instant ? -1e9 : performance.now(); caption(); }
    function stop() { clearTimeout(timer); timer = 0; }
    function caption() {
      var c = document.getElementById("cap"); if (!c) return;
      c.textContent = (cur + 1) + " of 4. " + CAP[cur](vals);
      for (var q = 0; q < 4; q++) stages[q].setAttribute("aria-current", q === cur ? "step" : "false");
      var nx = document.getElementById("nx"); if (nx) nx.textContent = cur === 3 ? "Replay" : "Next step";
    }
    function tick() { if (cur < 3) { go(cur + 1); timer = setTimeout(tick, 2300); } else timer = 0; }
    stages.forEach(function (el, q) { el.addEventListener("click", function () { stop(); go(q); }); });
    var nx = document.getElementById("nx"), sk = document.getElementById("sk");
    if (nx) nx.addEventListener("click", function () { stop(); go(cur === 3 ? 0 : cur + 1); });
    if (sk) sk.addEventListener("click", function () { stop(); go(3, true); });
    caption();
    if (!reduce && desktop) timer = setTimeout(tick, 1200);
    var seen = true, last = 0;
    if (window.IntersectionObserver) new IntersectionObserver(function (e) { seen = e[0].isIntersecting; }).observe(canvas);
    (function loop(now) {
      var p = Math.min(1, (now - ts) / 1100); p = 1 - Math.pow(1 - p, 3);
      /* idle drift is drawn at about 24 fps and only while the field is on screen */
      if (p < 1 || (seen && !document.hidden && now - last > 40)) { setStage(cur, p); draw(now, cur, p); last = now; }
      if (!reduce || p < 1) S.raf = requestAnimationFrame(loop);
    })(performance.now());
    S.stop = stop;
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

  function heatColor(v, max) {
    if (v == null) return "rgba(141,135,119,.14)";
    var t = Math.max(-1, Math.min(1, v / max)), a = (0.14 + 0.5 * Math.abs(t)).toFixed(2);
    return t >= 0 ? "rgba(212,175,55," + a + ")" : "rgba(194,85,63," + a + ")";
  }
  function relTxt(v) { return v == null ? "n/a" : (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%"; }
  function sectorHtml(secs) {
    if (!secs || !secs.length) return "";
    var mx = 0.01;
    secs.forEach(function (s) { mx = Math.max(mx, Math.abs(s.rel_1w || 0), Math.abs(s.rel_1m || 0)); });
    var tiles = secs.map(function (s, i) {
      var det = "Calls by view (Bullish / Bearish): " + HZ.map(function (h) { var c = s.calls[h[0]]; return h[1] + " " + c.Bullish + " / " + c.Bearish; }).join(", ") + ". " + s.n + " stocks in the scan.";
      return '<button type="button" class="sec" data-i="' + i + '" aria-pressed="false" title="' + esc(s.name + ". " + det) + '">' +
        '<span class="sname">' + esc(s.name) + '</span>' +
        '<span class="cell" style="background:' + heatColor(s.rel_1w, mx) + '"><span class="label">1 week</span><b>' + relTxt(s.rel_1w) + '</b></span>' +
        '<span class="cell" style="background:' + heatColor(s.rel_1m, mx) + '"><span class="label">1 month</span><b>' + relTxt(s.rel_1m) + '</b></span>' +
        '<span class="bb"><span class="pos">' + s.bullish + ' Bullish</span><span class="neg">' + s.bearish + ' Bearish</span></span></button>';
    }).join("");
    return '<section class="heat"><h2>Sector heat</h2><p class="lede">Each sector\'s average move in local currency returns minus the S&amp;P 500 (SPY) over 1 week and 1 month, with how many of its stocks the mispricing view calls Bullish or Bearish. Gold is ahead of the index, red is behind, gray is level. Tap a tile for the other views.</p>' +
      '<div class="twrap"><span class="swipe" id="hsw" aria-hidden="true">Swipe for more &rarr;</span><div class="tw heatrow" id="hrow">' + tiles + '</div></div>' +
      '<p class="note" id="hdet" aria-live="polite">Tap a sector to see its calls in every view.</p></section>';
  }
  function sectorWire(secs) {
    var row = document.getElementById("hrow"), sw = document.getElementById("hsw"), det = document.getElementById("hdet");
    if (!row) return;
    [].forEach.call(row.querySelectorAll(".sec"), function (b) {
      b.addEventListener("click", function () {
        var s = secs[+b.getAttribute("data-i")];
        [].forEach.call(row.querySelectorAll(".sec"), function (o) { o.setAttribute("aria-pressed", o === b ? "true" : "false"); });
        det.textContent = s.name + ", " + s.n + " stocks. 1 week " + relTxt(s.rel_1w) + " and 1 month " + relTxt(s.rel_1m) + " vs SPY. Bullish / Bearish: " + HZ.map(function (h) { var c = s.calls[h[0]]; return h[1] + " " + c.Bullish + " / " + c.Bearish; }).join(", ") + ".";
      });
    });
    var upd = function () {
      tw_more(row);
      if (row.scrollLeft > 8 && sw) sw.hidden = true;
    };
    row.addEventListener("scroll", upd, { passive: true }); window.addEventListener("resize", upd); upd();
  }
  function tw_more(tw) { tw.parentNode.classList.toggle("more", tw.scrollWidth - tw.clientWidth - tw.scrollLeft > 4); }

  function byIndexHtml(f) {
    var st = f.by_index_stages;
    if (!st) return "";
    var names = Object.keys(st.universe).sort(function (a, b) { return st.universe[b] - st.universe[a]; });
    var rows = names.map(function (n) {
      return "<tr><td>" + esc(n) + "</td><td>" + st.universe[n].toLocaleString() + "</td><td>" + (st.with_data[n] || 0).toLocaleString() + "</td><td>" + (st.passed_checks[n] || 0).toLocaleString() + "</td></tr>";
    }).join("");
    return '<details class="byix"><summary class="label">Funnel by index (a stock in two indexes counts in both)</summary><div class="tw" tabindex="0" role="region" aria-label="Funnel by index"><table><thead><tr><th>Index</th><th>In</th><th>With data</th><th>Passed checks</th></tr></thead><tbody>' + rows + "</tbody></table></div></details>";
  }

  function dropNote() {
    var d = (S.latest && S.latest.dropped_baskets) || [];
    return d.map(function (x) { return '<p class="note dropnote" role="status">' + esc(x.name) + " list unavailable on " + esc(x.date) + ", this scan ran without it.</p>"; }).join("");
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
    var chips = L.indexes.map(function (i) { return '<span class="ix"><span class="label">' + esc(i.name) + '</span><b class="' + (i.chg_1d == null ? "" : i.chg_1d < 0 ? "neg" : "pos") + '">' + pct(i.chg_1d) + "</b></span>"; }).join("");
    app.innerHTML =
      '<section class="hero"><span class="label">Daily scan across ' + nIdx + ' indexes &middot; as of ' + esc(L.asof) + "</span>" +
      '<h1>' + f.universe.toLocaleString() + ' stocks in.<br><em>' + f.picks + ' setups out.</em></h1>' +
      '<p class="lede">Every weekday after the close we run each stock from the major indexes through data checks, a valuation model and a handful of plain price rules, then rank the strongest bullish and bearish setups. Every call is logged and graded against the S&amp;P 500, in public.</p>' +
      '<div class="field"><canvas id="cv" aria-label="Animated field of dots. Each dot is a stock, narrowing from the full universe to the final picks." role="img"></canvas>' +
      '<div class="stages">' + ["Universe", "Passed checks", "Scored", "Picks"].map(function (n) { return '<button type="button" class="stage"><span class="k">' + n + '</span><span class="n">0</span></button>'; }).join("") + "</div></div>" +
      '<div class="story"><p id="cap" class="cap" aria-live="polite"></p><div class="ctl"><button type="button" id="nx" class="btn">Next step</button><button type="button" id="sk" class="btn ghost">Skip animation</button></div></div>' + byIndexHtml(L.funnel) + '</section>' + sectorHtml(L.sectors) +
      '<div class="ixs" tabindex="0" role="region" aria-label="Index moves today">' + chips + '</div>' + dropNote() + '<div class="tabs" role="tablist">' + tabs + "</div>" + body;
    sectorWire(L.sectors);
    requestAnimationFrame(function () { app.classList.remove("boot"); app.removeAttribute("aria-busy"); });
    if (window.V5) V5.changes(app);
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
    if (!S.lk) {
      app.classList.add("boot"); /* footer stays below the fold while the ticker file loads */
      app.innerHTML = '<section class="hero"><span class="label">Ticker lookup</span><h1>Look up <em>any</em> name.</h1><p class="lede" role="status">Loading every scored ticker...</p></section>';
      load("data/latest.json").then(function (d) { S.lk = d.lookup; app.classList.remove("boot"); if (/^#\/lookup/.test(location.hash)) lookup(sym); })
        .catch(function () { app.classList.remove("boot"); if (!/^#\/lookup/.test(location.hash)) return; app.innerHTML = '<section class="hero"><h1>Lookup <em>unavailable.</em></h1><p class="lede">The ticker file could not be loaded. Try again later. Not investment advice.</p></section>'; });
      return;
    }
    var LK = S.lk, keys = Object.keys(LK).sort();
    var picks = S.latest.horizons.mispricing.top_bull.slice(0, 4).concat(S.latest.horizons.mispricing.top_bear.slice(0, 3)).map(function (r) { return r.ticker; });
    app.innerHTML = '<section class="hero"><span class="label">Ticker lookup</span><h1>Look up <em>any</em> name.</h1>' +
      '<p class="lede">Type a ticker to see the mispricing score, both technical horizons, the reasons behind each score, and its last 60 closes.</p>' +
      '<form class="search" id="f" autocomplete="off"><input type="search" id="q" list="tl" placeholder="Try ' + esc(picks[0] || "a ticker") + '" aria-label="Ticker" value="' + esc(sym || "") + '"><datalist id="tl">' + keys.map(function (k) { return '<option value="' + esc(k) + '">'; }).join("") + "</datalist></form>" +
      '<div class="sugg">' + picks.map(function (p) { return '<button type="button" data-t="' + esc(p) + '">' + esc(p) + "</button>"; }).join("") + '</div><div id="res"></div></section>';
    var q = document.getElementById("q"), res = document.getElementById("res");
    function show(v) {
      v = (v || "").trim().toUpperCase();
      if (!LK[v] && LK[v.replace(".", "-")]) v = v.replace(".", "-");
      if (!v) { res.innerHTML = ""; return; }
      var r = LK[v];
      if (!r) { res.innerHTML = '<p class="note">No scored data for "' + esc(v) + '" in the latest scan. It may be outside the universe or failed a data check.</p>'; return; }
      res.innerHTML = '<div class="card fade"><span class="label">' + esc((r.ix && r.ix.length > 1 ? r.ix.join(", ") + " | " : r.i ? r.i + " | " : "") + (r.s || "")) + "</span><h2>" + esc(v) + " <span style=\"color:var(--muted);font-size:.5em\">" + esc(r.n) + '</span></h2><div class="meta"><span class="label">Last close ' + (r.c == null ? "n/a" : r.c.toFixed(2) + (r.cur ? " " + esc(r.cur) : "")) + '</span><span class="label">As of ' + esc(S.latest.asof) + "</span></div>" +
        (r.ch && window.V5 ? V5.chartBox(v) : spark(r.spark)) + '<div class="hzs">' + hzCard("Mispricing", r.mp, true) + hzCard("Short-term", r.st) + hzCard("Swing", r.sw) + '</div><p class="note">Mechanical rules on past data, not a forecast. Not investment advice.</p></div>';
      var cb = res.querySelector(".chartbox"); if (cb) V5.chart(cb);
      if (window.V5) V5.link(res, v);
    }
    q.addEventListener("input", function () { show(q.value); });
    document.getElementById("f").addEventListener("submit", function (e) { e.preventDefault(); show(q.value); });
    [].forEach.call(app.querySelectorAll(".sugg button"), function (b) { b.addEventListener("click", function () { q.value = b.getAttribute("data-t"); show(q.value); }); });
    show(sym);
  }

  /* ---------- scroll region with a "more to the side" hint ---------- */
  function scrollRegion(inner, label, id) {
    return '<div class="twrap"><span class="swipe" id="sw-' + id + '" aria-hidden="true">Scroll sideways for more &rarr;</span>' +
      '<div class="tw" id="tw-' + id + '" tabindex="0" role="region" aria-label="' + esc(label) + '">' + inner + "</div></div>";
  }
  function watchScroll(id) {
    var tw = document.getElementById("tw-" + id), sw = document.getElementById("sw-" + id);
    if (!tw) return;
    var upd = function () {
      var more = tw.scrollWidth - tw.clientWidth - tw.scrollLeft > 4;
      tw.parentNode.classList.toggle("more", more);
      if (tw.scrollLeft > 8 && sw) sw.hidden = true;
    };
    tw.addEventListener("scroll", upd, { passive: true }); window.addEventListener("resize", upd); upd();
    if (window.ResizeObserver) new ResizeObserver(upd).observe(tw);
  }

  /* ---------- long-term tab: SEC 10-K quality and valuation ---------- */
  function secUrl(cik, accn) { return "https://www.sec.gov/Archives/edgar/data/" + parseInt(cik, 10) + "/" + String(accn).replace(/-/g, "") + "/"; }
  var LT = { sort: "ck", q: "", n: 60 };
  function ltCell(r, k, fmt) {
    var m = r[k];
    if (!m) return '<td class="num na" title="' + esc((r.nr && r.nr[k]) || "Not reported in a form we can read") + '">n/a</td>';
    return '<td class="num"><a class="fig" target="_blank" rel="noopener" href="' + secUrl(r.cik, m.a || r.a) + '" title="Open the SEC filing for fiscal year ending ' + esc(r.fy) + '">' + fmt(m) + "</a></td>";
  }
  function fp(x, d) { return (x * 100).toFixed(d == null ? 1 : d) + "%"; }
  var LTSORT = {
    ck: function (r) { return r.cm ? r.ck / r.cm + r.cm / 100 : -1; },
    rev_cagr: function (r) { return r.rev_cagr ? r.rev_cagr.v : -9; },
    fcf_margin: function (r) { return r.fcf_margin ? r.fcf_margin.v : -9; },
    roic: function (r) { return r.roic ? r.roic.v : -9; },
    debt_ebitda: function (r) { return r.debt_ebitda ? -r.debt_ebitda.v : -999; },
    t: function (r) { return r.t; }
  };
  function ltRows() {
    var q = LT.q.trim().toLowerCase(), f = LTSORT[LT.sort];
    var rows = S.lt.rows.filter(function (r) { return !q || r.t.toLowerCase().indexOf(q) === 0 || r.n.toLowerCase().indexOf(q) >= 0; });
    rows.sort(function (a, b) { var x = f(a), y = f(b); return LT.sort === "t" ? (x < y ? -1 : 1) : (y - x) || (a.t < b.t ? -1 : 1); });
    return rows;
  }
  function ltBody() {
    var rows = ltRows(), shown = rows.slice(0, LT.n);
    var html = shown.map(function (r) {
      return '<tr><td class="stk"><a class="tk" href="#/lookup/' + encodeURIComponent(r.t) + '">' + esc(r.t) + '</a><span class="nm2">' + esc(r.n) + "</span></td>" +
        '<td class="num" title="' + esc(S.lt.rules.join("; ")) + '">' + r.ck + " of " + r.cm + "</td>" +
        ltCell(r, "rev_cagr", function (m) { return fp(m.v) + " <small>" + m.yrs + "y</small>"; }) +
        ltCell(r, "op_margin", function (m) { return fp(m.v) + " <small>" + (m.d >= 0 ? "+" : "") + (m.d * 100).toFixed(1) + " pts</small>"; }) +
        ltCell(r, "fcf_margin", function (m) { return fp(m.v); }) +
        ltCell(r, "roic", function (m) { return fp(m.v); }) +
        ltCell(r, "shares", function (m) { return (m.v >= 0 ? "+" : "") + fp(m.v); }) +
        ltCell(r, "debt_ebitda", function (m) { return m.v.toFixed(1) + "x"; }) +
        ltCell(r, "fcf_yield", function (m) { return fp(m.v); }) +
        ltCell(r, "ev_ebitda", function (m) { return m.v.toFixed(1) + "x"; }) + "</tr>";
    }).join("");
    return { html: html, total: rows.length, shown: shown.length };
  }
  function longterm() {
    var D = S.lt, c = D.coverage;
    function head(k, label, sortable) { return "<th" + (k && LT.sort === k ? ' aria-sort="descending"' : "") + ">" + label + "</th>"; }
    var tbl = '<table id="lttable"><thead><tr><th>Name</th>' + head("ck", "Checks") + head("rev_cagr", "Revenue CAGR") + head(0, "Op margin, 5y change") + head("fcf_margin", "FCF margin") + head("roic", "ROIC proxy") + head(0, "Shares, 2y") + head("debt_ebitda", "Debt / EBITDA") + head(0, "FCF yield") + head(0, "EV / EBITDA") + "</tr></thead><tbody id=\"ltbody\"></tbody></table>";
    app.innerHTML = '<section class="hero"><span class="label">Long-term</span><h1>Ten years of <em>10-K numbers.</em></h1>' +
      '<p class="label" id="lt-asof">Long-term data as of ' + esc(D.built || "unknown") + "</p>" +
      '<p class="lede">Quality and valuation for ' + D.count + " of " + D.universe + " S&amp;P 500 names, built only from annual SEC filings. Every figure links to the filing it came from. Mechanical rules on reported numbers: not forecasts, and nothing here is a recommendation. <strong>Not investment advice.</strong></p></section>" +
      '<section class="lt"><div class="ltbar"><label class="label" for="ltq">Find a name</label><input id="ltq" type="search" placeholder="Ticker or company" autocomplete="off" value="' + esc(LT.q) + '">' +
      '<label class="label" for="lts">Sort by</label><select id="lts"><option value="ck">Checks passed</option><option value="rev_cagr">Revenue CAGR</option><option value="fcf_margin">FCF margin</option><option value="roic">ROIC proxy</option><option value="debt_ebitda">Lowest debt / EBITDA</option><option value="t">Ticker A to Z</option></select></div>' +
      '<p class="note" id="ltcount" aria-live="polite"></p>' + scrollRegion(tbl, "Long-term SEC 10-K table", "lt") +
      '<p class="center"><button type="button" class="more-btn" id="ltmore">Show more</button></p>' +
      '<details class="how"><summary>How these are computed</summary><ul>' +
      "<li><b>Source:</b> SEC EDGAR XBRL companyfacts. 10-K annual facts only, one fact per period, the latest filing wins if a number was restated. Fiscal year of the latest 10-K is in each link.</li>" +
      "<li><b>Revenue CAGR:</b> compound growth over the longest span up to 10 years that the filings cover (at least 5).</li>" +
      "<li><b>Op margin:</b> operating income over revenue, with the change in points versus 5 years earlier.</li>" +
      "<li><b>FCF margin:</b> operating cash flow minus capital spending, over revenue.</li>" +
      "<li><b>ROIC proxy:</b> operating income after the company's own tax rate (21% if unusable, capped at 35%), over debt plus equity minus cash at year end. A proxy, not the company's own figure.</li>" +
      "<li><b>Shares, 2y:</b> change in diluted weighted shares over two years, both ends from the newest filing so splits line up.</li>" +
      "<li><b>Debt / EBITDA:</b> tagged debt over operating income plus depreciation and amortization. Shown only when EBITDA is positive. Finance leases count only where a company tags them inside its debt line; operating leases are left out.</li>" +
      "<li><b>FCF yield and EV / EBITDA:</b> use the last scan price and the 10-K cover share count (share classes added up). A price is a snapshot, so these move daily.</li>" +
      "<li><b>Checks:</b> six yes or no tests: " + D.rules.map(esc).join("; ") + ". The count is of tests that could be measured. Banks, insurers and others without an operating income line show n/a.</li>" +
      "<li><b>Coverage:</b> revenue CAGR " + c.rev_cagr + ", operating margin " + c.op_margin + ", FCF margin " + c.fcf_margin + ", ROIC proxy " + c.roic + ", share change " + c.shares + ", debt / EBITDA " + c.debt_ebitda + ", FCF yield " + c.fcf_yield + ", EV / EBITDA " + c.ev_ebitda + " of " + D.count + " names. Data built " + esc(D.built) + ".</li></ul></details></section>";
    var q = document.getElementById("ltq"), sel = document.getElementById("lts"), more = document.getElementById("ltmore");
    sel.value = LT.sort;
    function draw() {
      var r = ltBody();
      document.getElementById("ltbody").innerHTML = r.html;
      document.getElementById("ltcount").textContent = "Showing " + r.shown + " of " + r.total + " names" + (LT.q ? " matching your search" : "") + ". Higher check counts are not a forecast.";
      more.hidden = r.shown >= r.total;
    }
    q.addEventListener("input", function () { LT.q = q.value; LT.n = 60; draw(); });
    sel.addEventListener("change", function () { LT.sort = sel.value; LT.n = 60; draw(); });
    more.addEventListener("click", function () { LT.n += 120; draw(); });
    draw(); watchScroll("lt");
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
    var tbl = rows.length ? scrollRegion('<table><thead><tr><th>Called</th><th>Name</th><th>View</th><th>Call</th><th>Window</th><th>Stock</th><th>Vs S&amp;P</th></tr></thead><tbody>' +
      rows.map(function (g) {
        return "<tr><td>" + esc(g.date) + '</td><td><a class="tk" href="#/lookup/' + encodeURIComponent(g.ticker) + '">' + esc(g.ticker) + "</a></td><td>" + esc(HZNAME[g.lens] || g.lens) + "</td><td>" + esc(g.label) + '</td><td class="num">' + g.window + 'd</td><td class="num">' + pct(g.stock_return) + '</td><td class="num ' + (g.excess >= 0 ? "pos" : "neg") + '">' + pct(g.excess) + "</td></tr>";
      }).join("") + "</tbody></table>", "Graded calls table", "graded") : '<p class="note">No graded calls yet. A call is graded from the next trading day\'s close, over 5, 20 and 60 trading days, so the first results appear after a week.</p>';
    app.innerHTML = '<section class="hero"><span class="label">Track record</span><h1>' + (noise ? "Still <em>noise.</em>" : "Enough days <em>to read.</em>") + "</h1>" +
      '<p class="lede">Every published pick is logged with its date, then graded against the S&amp;P 500 from the next trading day\'s close, over 5, 20 and 60 trading days. A Bullish call wins by beating the index, a Bearish call by lagging it. ' + esc(T.note) + "</p>" +
      '<p class="lede sample" id="sample-size"><strong>Sample size:</strong> ' + T.calls_logged.toLocaleString() + " calls logged, " + T.graded.length.toLocaleString() + " graded, across " + T.trading_days + " trading day" + (T.trading_days === 1 ? "" : "s") + ". " + (noise ? "Under " + T.min_days + " trading days this is still noise: do not read skill into it." : "Past " + T.min_days + " trading days, but a few weeks of calls is still a small sample.") + "</p>" +
      '<div class="ringwrap"><div class="ring"><svg viewBox="0 0 220 220" aria-hidden="true"><circle cx="110" cy="110" r="96" fill="none" stroke="#1a1812" stroke-width="8"/><circle class="p" id="pr" cx="110" cy="110" r="96" fill="none" stroke="#d4af37" stroke-width="8" stroke-linecap="round" stroke-dasharray="' + C + '" stroke-dashoffset="' + C + '"/></svg>' +
      '<div class="c" role="img" aria-label="' + esc(noise ? "still noise" : "readable") + ", " + T.trading_days + " of " + T.min_days + ' trading days"><b>' + T.trading_days + '</b><span class="label">of ' + T.min_days + ' trading days</span><span class="label" style="color:var(--gold);margin-top:6px">' + (noise ? "still noise" : "readable") + "</span></div></div>" +
      '<div class="stats">' + stat("mispricing") + stat("short_term") + stat("swing") + '<div class="stat"><span class="label">Calls logged</span><div class="v">' + T.calls_logged.toLocaleString() + '</div><span class="label">' + T.pending + " pending</span></div>" +
      '<div class="stat"><span class="label">Rule</span><div class="v" style="font-size:18px">Nothing is hidden or removed after the fact.</div></div></div></div></section>' +
      '<section><h2>Graded calls</h2><p class="lede" style="margin-top:6px">Most recent 40 of the latest 300 graded calls shown here. <a href="https://github.com/abvarisano-droid/market-scanner/blob/main/data/picks.csv" target="_blank" rel="noopener">Full ledger</a> (every call, logged once and never replaced by a later run). Neutral names are never called. Results this early are not evidence of skill.</p>' + tbl + "</section>";
    watchScroll("graded");
    if (window.V5) V5.report(app);
    var pr = document.getElementById("pr");
    if (reduce) pr.style.strokeDashoffset = C * (1 - p);
    else requestAnimationFrame(function () { requestAnimationFrame(function () { pr.style.strokeDashoffset = C * (1 - p); }); });
  }

  function loadLT() {
    app.innerHTML = '<section class="hero"><span class="label">Long-term</span><p class="lede">Loading SEC filings data...</p></section>';
    load("data/longterm.json").then(function (d) { S.lt = d; if (location.hash.indexOf("#/longterm") === 0) longterm(); })
      .catch(function () { app.innerHTML = '<section class="hero"><h1>Long-term data <em>unavailable.</em></h1><p class="lede">The SEC data file could not be loaded. Not investment advice.</p></section>'; });
  }

  /* ---------- how it works (every number comes from data/method.json, built from the code constants) ---------- */
  var MNAME = { forwardPE: "forward P/E", trailingPE: "trailing P/E", enterpriseToEbitda: "EV/EBITDA", priceToBook: "price to book", fcf_yield: "free cash flow yield", returnOnEquity: "return on equity", profitMargins: "profit margin", revenueGrowth: "revenue growth", debtToEquity: "debt to equity" };
  var RNAME = { ma20: "Price vs its 20-day average", momentum: "5 and 10 day momentum", rsi: "RSI(14)", volume: "Volume vs its 20-day average", ma50: "Price vs its 50-day average", ma200: "Price vs its 200-day average", slope: "Slope of the 50 and 200-day averages", rs: "3-month return vs the S&amp;P 500", high52: "Distance from the 52-week high" };
  function mlist(a) { return a.map(function (k) { return MNAME[k] || k; }).join(", "); }
  function wtable(w) { return "<ul>" + Object.keys(w).sort(function (a, b) { return w[b] - w[a]; }).map(function (k) { return "<li><b>" + w[k] + "%</b> " + RNAME[k] + "</li>"; }).join("") + "</ul>"; }
  function methodology() {
    var M = S.method, U = M.universe, F = M.funnel, P = M.mispricing, T = M.technical, G = M.grading, w = G.windows;
    var live = U.live.join(", "), bk = Object.keys(U.baskets), bn = bk.reduce(function (s, k) { return s + U.baskets[k]; }, 0);
    var wv = P.weights_pct;
    app.innerHTML = '<section class="hero"><span class="label">How it works</span><h1>Rules you can <em>read.</em></h1>' +
      '<p class="lede">Everything below is taken from the scanner\'s own code, and the numbers on this page are read from the same constants the scan uses. Mechanical rules on public price and valuation data: not forecasts, and nothing here is a recommendation. <strong>Not investment advice.</strong></p></section>' +
      '<section class="mx"><h2>1. The universe</h2><p class="lede">Stocks come from the index lists. ' + esc(live) + ' are pulled live from Wikipedia when it is reachable. The other ' + bk.length + ' indexes use a fixed basket of large names (' + bn + ' tickers in total), so global coverage is thin. ' + U.index_levels + ' index levels and ' + esc(U.benchmark) + ' (the S&amp;P 500 fund used as the yardstick) are tracked for context and are not scored as stocks. The Russell 2000 uses its real constituents from the ' + esc(U.russell.source) + ' file (a pull under ' + U.russell.min_equities.toLocaleString() + ' equities is rejected as a bad file). Prices and fundamentals come from Yahoo Finance, which is free and can be delayed or wrong.</p>' + dropNote() + '</section>' +
      '<section class="mx"><h2>2. The funnel</h2><p class="lede">Each stock must clear these data checks before any lens scores it. A stock that fails is dropped, and the site counts why.</p><ul class="mlist">' +
      "<li><b>History:</b> at least " + F.min_bars + " daily bars (about a year).</li>" +
      "<li><b>Fresh:</b> the latest bar is no more than " + F.stale_days + " calendar days older than the newest bar in the scan.</li>" +
      "<li><b>Clean:</b> no zero or negative closes, no missing close or volume.</li>" +
      "<li><b>Liquid:</b> average daily dollar volume (close times volume) over the last 20 days of at least $" + F.min_dollar_vol.toLocaleString() + ".</li>" +
      "<li><b>Mispricing only:</b> at least " + F.min_coverage_pct + "% of its value and quality metrics must exist, or it is not ranked.</li>" +
      "<li><b>Picks:</b> each technical lens lists up to " + F.top_n + " names per side. Mispricing lists the top " + F.mp_top + " and the bottom " + F.mp_low + ".</li></ul></section>" +
      '<section class="mx"><h2>3. The three lenses</h2>' +
      '<h3>Mispricing, -100 to +100</h3><p class="lede">Each metric is compared with sector peers (market-wide if a sector has fewer than 3 usable names), trimmed at the 5th and 95th percentile, and turned into a score. Negative multiples are ignored. The blocks are weighted: <b>' + wv.value + '% value</b> (' + esc(mlist(P.value)) + '), <b>' + wv.quality + '% quality</b> (' + esc(mlist(P.quality)) + '), <b>' + wv.analyst + '% analyst gap</b> (the average analyst estimate vs the last close, scaled by how many analysts cover it, full weight at 10 or more), and <b>' + wv.momentum + '% recent stretch</b> (a deep 3-month drop scores as cheap, a big run-up as stretched, relative to the stock\'s own volatility). A score of ' + P.call_at + ' or more is Bullish and ' + (-P.call_at) + ' or less is Bearish, after a small nudge from headline wording. With an AI key set, a language model can write the thesis and call from the same numbers; otherwise the rules decide.</p>' +
      '<h3>Short-term, 0 to 100</h3><p class="lede">Needs at least ' + T.min_short + ' bars. Weighted rules:</p>' + wtable(T.short_weights_pct) +
      '<h3>Swing, 0 to 100</h3><p class="lede">Needs at least ' + T.min_swing + ' bars plus the S&amp;P 500 on matching dates. Weighted rules:</p>' + wtable(T.swing_weights_pct) +
      '<p class="lede">Each rule scores from 0 (bearish) to 1 (bullish), and the lens score is 100 times the weighted average. The three strongest pulls become the reasons shown.</p></section>' +
      '<section class="mx"><h2>4. How calls are labeled</h2><p class="lede">Short-term and Swing: <b>Bullish</b> at ' + T.bull_at + ' or more, <b>Bearish</b> at ' + T.bear_at + ' or less, <b>Neutral</b> in between. Mispricing uses the +/-' + P.call_at + ' cut above. Only Bullish and Bearish calls are logged; Neutral is never graded. Older logs used other names, which still load and map to these three.</p></section>' +
      '<section class="mx"><h2>5. How calls are graded</h2><ul class="mlist">' +
      "<li><b>Entry</b> is the close of the next trading day after the signal date, never the signal\'s own close. The S&amp;P 500 uses the same entry day.</li>" +
      "<li><b>Windows</b> are " + w.join(", ") + " trading days counted from that entry close.</li>" +
      "<li><b>A win</b> for a Bullish call is beating the S&amp;P 500 over the window. For a Bearish call it is lagging it.</li>" +
      "<li><b>Still noise:</b> until the log covers " + G.min_days + " trading days, the whole record is labeled still noise. Even after that, a few weeks of calls is a small sample.</li>" +
      "<li>Rows logged under an older same-day entry rule keep it, so history is not rewritten.</li></ul></section>" +
      '<section class="mx"><h2>6. The Long-term tab</h2><p class="lede">It uses only annual SEC 10-K filings, not Yahoo data, for S&amp;P 500 names, and links each figure to its filing. Six yes or no checks are counted: ' + M.longterm.rules.map(esc).join("; ") + '. They describe past reported numbers.</p></section>' +
      '<section class="mx"><h2>7. Honest limits</h2><ul class="mlist">' +
      "<li>Free data: Yahoo Finance fundamentals can be stale, missing or restated, and prices are adjusted for splits and dividends by the provider.</li>" +
      "<li>There are no earnings estimate revisions, no insider or options data, and no sector-specific models. The analyst gap uses one average analyst estimate only.</li>" +
      "<li>Banks, insurers and other unusual reporters often lack clean multiples and show gaps.</li>" +
      "<li>Technical rules look only at price and volume, so they say nothing about why a stock moved.</li>" +
      "<li>The track record is short and each lens has few calls, so hit rates swing widely. Calls ignore trading costs and taxes.</li>" +
      "<li>The global baskets are fixed lists, not full index membership.</li></ul>" +
      '<p class="disc" style="margin-top:20px"><strong>Not investment advice.</strong> Read the <a href="#/track">track record</a> before trusting any lens.</p></section>';
    window.scrollTo(0, 0);
  }
  function loadMethod() {
    app.innerHTML = '<section class="hero"><span class="label">How it works</span><p class="lede">Loading...</p></section>';
    load("data/method.json").then(function (d) { S.method = d; if (location.hash.indexOf("#/how") === 0) methodology(); })
      .catch(function () { app.innerHTML = '<section class="hero"><h1>Method <em>unavailable.</em></h1><p class="lede">The method file could not be loaded. Not investment advice.</p></section>'; });
  }

  /* ---------- router ---------- */
  function route() {
    cancelAnimationFrame(S.raf);
    var h = location.hash.replace(/^#\/?/, "").split("?")[0], parts = h.split("/"), pg = parts[0] || "home";
    if (pg !== "home") { app.classList.remove("boot"); app.removeAttribute("aria-busy"); }
    [].forEach.call(document.querySelectorAll("nav a"), function (a) { a.classList.toggle("on", a.getAttribute("data-nav") === pg); });
    try {
      if (pg === "stock" && window.V5) V5.stock(app, decodeURIComponent(parts[1] || ""));
      else if (pg === "lookup") lookup(decodeURIComponent(parts[1] || ""));
      else if (pg === "track") track();
      else if (pg === "how") { if (S.method) methodology(); else loadMethod(); }
      else if (pg === "longterm") { if (S.lt) longterm(); else loadLT(); }
      else home();
    } catch (e) {
      app.classList.remove("boot"); app.removeAttribute("aria-busy");
      if (window.console) console.warn("view failed", pg, e);
      app.innerHTML = '<section class="hero"><h1>This view <em>hit a snag.</em></h1><p class="lede">Something in this page could not be drawn. Use the menu to open another view. Not investment advice.</p></section>';
    }
    window.scrollTo(0, 0);
  }

  Promise.all([load("data/summary.json"), load("data/track.json")]).then(function (r) {
    S.latest = r[0]; S.track = r[1];
    document.getElementById("asof").textContent = "(latest scan " + S.latest.asof + ")";
    if (S.latest.banner) { var b = document.getElementById("banner"); b.textContent = S.latest.banner; b.hidden = false; }
    fetch("data/watchdog.json").then(function (r) { return r.ok ? r.json() : null; }).then(function (w) {
      if (!w || !w.missed || !w.missed.length) return;
      var el = document.getElementById("wd");
      el.textContent = "Scan missed on " + w.missed.join(", ") + ". Results below may be a day behind.";
      el.hidden = false;
    }).catch(function () {});
    window.addEventListener("hashchange", route);
    var rt; window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(function () { if (!location.hash || location.hash === "#/") home(); }, 250); });
    route();
  }).catch(function () {
    app.classList.remove("boot"); app.removeAttribute("aria-busy");
    app.innerHTML = '<section class="hero"><h1>Scan data <em>unavailable.</em></h1><p class="lede">The data files could not be loaded. Try again later. Not investment advice.</p></section>';
  });
})();
