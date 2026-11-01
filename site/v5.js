(function () {
  "use strict";
  var NAMES = { mispricing: "Mispricing", short_term: "Short-term", swing: "Swing" };
  var ORDER = ["mispricing", "short_term", "swing"];
  var data = null, pending = null;
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function get() {
    if (data) return Promise.resolve(data);
    if (!pending) pending = fetch("data/v5.json").then(function (r) { if (!r.ok) throw new Error("v5"); return r.json(); }).then(function (d) { data = d; return d; });
    return pending;
  }
  function chip(l) { return '<span class="chip ' + (l === "Bearish" ? "bear" : l === "Bullish" ? "" : "neutral") + '">' + esc(l) + "</span>"; }
  function stockLink(t) { return '<a class="tk" href="#/stock/' + encodeURIComponent(t) + '">' + esc(t) + "</a>"; }
  function pctTxt(v) { return v == null ? "n/a" : (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%"; }

  /* ---------- what changed strip (home) ---------- */
  function changes(root) {
    get().then(function (d) {
      var anchor = root.querySelector(".ixs"); if (!anchor || root.querySelector("#v5-changes")) return;
      var c = d.changes, el = document.createElement("section");
      el.id = "v5-changes"; el.className = "v5strip"; el.setAttribute("aria-label", "What changed since the previous scan");
      var body;
      if (c.empty) body = '<p class="note" style="margin-top:6px">First scan, nothing to compare yet. Once a second day is logged, new and flipped calls show up here.</p>';
      else {
        var nb = c["new"].map(function (x) { return '<li>' + stockLink(x.ticker) + " " + chip(x.call) + ' <span class="label">' + esc(NAMES[x.lens]) + "</span></li>"; }).join("");
        var fl = c.flipped.map(function (x) { return '<li>' + stockLink(x.ticker) + " " + chip(x.from) + " &rarr; " + chip(x.to) + ' <span class="label">' + esc(NAMES[x.lens]) + "</span></li>"; }).join("");
        body = '<div class="v5cols"><div><h3>New calls <span class="label">' + c["new"].length + '</span></h3><ul class="v5list">' + (nb || '<li class="note">None.</li>') + "</ul></div>" +
          '<div><h3>Flipped <span class="label">' + c.flipped.length + '</span></h3><ul class="v5list">' + (fl || '<li class="note">None.</li>') + "</ul></div></div>";
      }
      el.innerHTML = '<h2>What changed</h2><p class="label">' + (c.empty ? "Latest log " + esc(c.date || "") : esc(c.previous) + " to " + esc(c.date)) + "</p>" + body;
      anchor.parentNode.insertBefore(el, anchor);
    }).catch(function () {});
  }

  /* ---------- lens report card (track) ---------- */
  function report(root) {
    get().then(function (d) {
      if (root.querySelector("#v5-report")) return;
      var r = d.report, rows = "";
      ORDER.forEach(function (k) {
        var L = r.lenses[k];
        ["5", "20", "60"].forEach(function (w, i) {
          var x = L.windows[w];
          rows += "<tr>" + (i === 0 ? '<td rowspan="3"><b>' + NAMES[k] + '</b><br><span class="label">' + L.calls + " calls</span></td>" : "") +
            '<td class="num">' + w + 'd</td><td class="num">' + x.graded + '</td><td class="num">' + (x.hit_rate_pct == null ? "n/a" : x.hit_rate_pct.toFixed(1) + "%") +
            '</td><td class="num">' + (x.avg_excess_pct == null ? "n/a" : (x.avg_excess_pct >= 0 ? "+" : "") + x.avg_excess_pct.toFixed(2) + "%") + "</td></tr>";
        });
      });
      var el = document.createElement("section"); el.id = "v5-report";
      el.innerHTML = "<h2>Lens report card</h2>" +
        '<p class="lede" style="margin-top:6px">' + (r.still_noise ? "<strong>Still noise.</strong> " : "") + r.trading_days + " of " + r.min_days + " trading days logged. " +
        (r.still_noise ? "Under " + r.min_days + " trading days, nothing below says how any lens will do. " : "") +
        'Graded count is calls with a finished window. Hit rate is the share that beat the S&amp;P 500 (SPY) for a Bullish call or lagged it for a Bearish call. Average excess is the return gap versus SPY, signed so a Bearish call scores positive when the stock lagged.</p>' +
        '<div class="twrap"><div class="tw" tabindex="0" role="region" aria-label="Lens report card table"><table><thead><tr><th>Lens</th><th>Window</th><th>Graded</th><th>Hit rate</th><th>Avg excess</th></tr></thead><tbody>' + rows + "</tbody></table></div></div>" +
        '<p class="note">A small graded count can swing hard on one name. Not investment advice.</p>';
      root.appendChild(el);
    }).catch(function () {});
  }


  /* ---------- price chart: 3 years of candles, chosen layers, volatility cone ----------
     Spec: main plot 320px (<760) / 460px (>=760); RSI and MACD panels 84px / 110px each.
     The box height is set from the layer state before data arrives, so loading never shifts layout.
     Palette: up #5fa97c, down #cb5d46, 50d #d4af37, 200d #9c8fd0, Bollinger #6fa8c8, grid #1c1a14.
     Type: mono 10px axis (11px desktop), mono 11px cone labels (12px desktop).
     Motion: cone fades in, opacity only, 700ms cubic-bezier(.2,.8,.2,1), 250ms delay. Reduced motion: none.
     Static fallback: the visually hidden table and the role=img summary carry the key numbers.
     Layer state lives in the URL hash (?on=...), never in storage. */
  var CH = {}, IND = null, indP = null, MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var LAYERS = [["vol", "Volume"], ["ma50", "50-day SMA"], ["ma200", "200-day SMA"], ["bb", "Bollinger Bands (20, 2)"], ["rsi", "RSI (14)"],
    ["macd", "MACD (12, 26, 9)"], ["hl", "52-week range"], ["fan", "Volatility cone (\u00b11\u03c3)"], ["earn", "Next earnings"]];
  var DEF = ["ma50", "ma200", "fan"], STATS = ["Last close", "1 year", "52-week range", "Yearly volatility", "Next event"];
  var COL = { up: "#5fa97c", dn: "#cb5d46", m50: "#d4af37", m200: "#9c8fd0", bb: "#6fa8c8", up1: "#5fa97c", flat: "#ebe6d8", dn1: "#cb5d46" };
  function getChart(t) {
    if (!CH[t]) CH[t] = fetch("data/charts/" + encodeURIComponent(t) + ".json").then(function (r) { if (!r.ok) throw new Error("chart"); return r.json(); });
    return CH[t];
  }
  function getInd() {
    if (IND) return Promise.resolve(IND);
    if (!indP) indP = new Promise(function (ok, no) { var sc = document.createElement("script"); sc.src = "indicators.js?v=7"; sc.onload = function () { IND = window.IND; ok(IND); }; sc.onerror = no; document.head.appendChild(sc); });
    return indP;
  }
  function state() {
    var q = (location.hash.split("?")[1] || ""), m = /(?:^|&)on=([^&]*)/.exec(q), mode = /(?:^|&)view=line/.test(q) ? "line" : "candles";
    var on = m ? decodeURIComponent(m[1]).split(",").filter(function (k) { return LAYERS.some(function (l) { return l[0] === k; }); }) : DEF.slice();
    return { mode: mode, on: on, has: function (k) { return on.indexOf(k) >= 0; } };
  }
  function saveState(st) {
    var base = location.hash.split("?")[0], q = [];
    if (st.mode === "line") q.push("view=line");
    if (st.on.slice().sort().join(",") !== DEF.slice().sort().join(",")) q.push("on=" + st.on.join(","));
    var h = base + (q.length ? "?" + q.join("&") : "");
    if (h !== location.hash) history.replaceState(null, "", h);
  }
  function dims(st) {
    var wide = window.innerWidth >= 760, main = window.innerWidth >= 1440 ? 540 : wide ? 460 : 320, sub = wide ? 110 : 84;
    return { main: main, sub: sub, total: main + sub * ((st.has("rsi") ? 1 : 0) + (st.has("macd") ? 1 : 0)) };
  }
  function fmt(v) {
    if (v == null) return "n/a";
    var a = Math.abs(v), d = a >= 10000 ? 0 : a >= 1000 ? 1 : 2;
    return v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function big(v) { if (v == null) return "n/a"; var a = Math.abs(v); return a >= 1e12 ? (v / 1e12).toFixed(2) + "T" : a >= 1e9 ? (v / 1e9).toFixed(1) + "B" : a >= 1e6 ? (v / 1e6).toFixed(1) + "M" : a >= 1e3 ? (v / 1e3).toFixed(0) + "K" : String(Math.round(v)); }
  function sp(v) { return v == null ? "n/a" : (v >= 0 ? "+" : "") + v.toFixed(1) + "%"; }
  function day(p, i) { var d = new Date(p.d0 + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + p.x[i]); return d; }
  function longDate(s) { var d = new Date(s + "T00:00:00Z"); return MON[d.getUTCMonth()] + " " + d.getUTCDate() + ", " + d.getUTCFullYear(); }
  function niceTicks(lo, hi, n) {
    var raw = (hi - lo) / n, mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10)), st = [1, 2, 2.5, 5, 10].map(function (k) { return k * mag; }).filter(function (k) { return k >= raw; })[0];
    var out = []; for (var v = Math.ceil(lo / st) * st; v <= hi; v += st) out.push(+v.toFixed(8)); return out;
  }
  function spread(items, gap, lo, hi) { /* keep labels at least gap px apart, inside [lo, hi] */
    items.sort(function (a, b) { return a.y - b.y; });
    for (var k = 0; k < 6; k++) {
      for (var i = 1; i < items.length; i++) if (items[i].y - items[i - 1].y < gap) { var m = (items[i].y + items[i - 1].y) / 2; items[i - 1].y = m - gap / 2; items[i].y = m + gap / 2; }
      items.forEach(function (it) { it.y = Math.max(lo, Math.min(hi, it.y)); });
    }
    return items;
  }
  function hit(a, b) { return a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1; }
  function place(cands, boxes, xlo, xhi) { /* first candidate box that touches nothing already placed (and stays inside xlo..xhi); it joins boxes */
    var ok = cands.filter(function (c) { return c.x0 >= xlo && c.x1 <= xhi; }), pick = null;
    for (var i = 0; i < ok.length && !pick; i++) if (!boxes.some(function (b) { return hit(ok[i], b); })) pick = ok[i];
    if (!pick) { /* nothing is fully clear: take the candidate with the least overlap */
      var area = function (c) { return boxes.reduce(function (s, b) { return s + Math.max(0, Math.min(c.x1, b.x1) - Math.max(c.x0, b.x0)) * Math.max(0, Math.min(c.y1, b.y1) - Math.max(c.y0, b.y0)); }, 0); };
      pick = (ok.length ? ok : cands).slice().sort(function (a, b) { return area(a) - area(b); })[0];
    }
    boxes.push(pick); return pick;
  }
  function calc(p) {
    if (p._ind) return p._ind;
    var dc = p.dc, ix = p.ix, P = IND.pick;
    var bb = IND.bollinger(dc, 20, 2), md = IND.macd(dc, 12, 26, 9);
    p._ind = { m50: P(IND.sma(dc, 50), ix), m200: P(IND.sma(dc, 200), ix), bbu: P(bb.up, ix), bbl: P(bb.lo, ix), bbm: P(bb.mid, ix),
      rsi: P(IND.rsi(dc, 14), ix), macd: P(md.macd, ix), sig: P(md.signal, ix), hist: P(md.hist, ix) };
    return p._ind;
  }
  function svgChart(p, W, st) {
    var D = dims(st), wide = W >= 700, n = p.c.length, f = st.has("fan") ? p.fan : null, I = calc(p);
    var padL = wide ? 8 : 6, padR = wide ? 168 : 8, padT = 18, padB = 28, gapP = 10;
    var pw = W - padL - padR, ph = D.main - padT - 6;
    var futW = wide ? pw * 0.2 : pw * 0.34, histW = pw - futW, slot = histW / n;
    var X = function (i) { return padL + (i + 0.5) * slot; }, xNow = X(n - 1), xEnd = padL + pw;
    var vals = p.l.concat(p.h).filter(function (v) { return v != null && v > 0; }), keep = function (arr) { arr.forEach(function (v) { if (v != null && v > 0) vals.push(v); }); };
    if (st.has("ma50")) keep(I.m50); if (st.has("ma200")) keep(I.m200); if (st.has("bb")) { keep(I.bbu); keep(I.bbl); } if (st.has("hl")) keep([p.hi52, p.lo52]);
    var paths = [];
    if (f) [["up", 1, "+1\u03c3", "up1"], ["flat", 0, "No change", "flat"], ["down", -1, "-1\u03c3", "dn1"]].forEach(function (s) {
      /* zero drift: the cone is centered on the last close, plus and minus one yearly standard deviation */
      var pts = []; for (var i = 0; i <= 12; i++) { var t = i / 12; pts.push(p.last * Math.exp(s[1] * f.sigma * Math.sqrt(t))); }
      keep(pts); paths.push({ name: s[2], col: COL[s[3]], pts: pts, pct: f[s[0] + "_pct"], lvl: f[s[0]], k: s[1] });
    });
    var lo = Math.log(Math.min.apply(null, vals)), hi = Math.log(Math.max.apply(null, vals)), pad = (hi - lo) * 0.06 || 0.05;
    lo -= pad; hi += pad;
    var vh = st.has("vol") ? ph * 0.18 : 0, pph = ph - vh;
    var Y = function (v) { return padT + (hi - Math.log(v)) / (hi - lo) * pph; };
    var o = [], fs = wide ? 11 : 10, lf = wide ? 12 : 11;
    var subs = [], y0 = D.main; if (st.has("rsi")) { subs.push(["rsi", y0]); y0 += D.sub; } if (st.has("macd")) { subs.push(["macd", y0]); y0 += D.sub; }
    var H = D.total + padB, axisY = H - 9, plotBottom = D.total - (subs.length ? 4 : 6);
    function hline(y, cls) { return '<line x1="' + padL + '" x2="' + xEnd.toFixed(1) + '" y1="' + y.toFixed(1) + '" y2="' + y.toFixed(1) + '" class="' + cls + '"/>'; }
    /* price grid */
    var tk = niceTicks(Math.exp(lo), Math.exp(hi), wide ? 6 : 4);
    if (tk.length > 7) tk = tk.filter(function (_, i) { return i % 2 === 0; });
    tk.forEach(function (v) { var y = Y(v); if (y < padT + 8 || y > padT + pph - 4) return;
      o.push(hline(y, "cg") + '<text x="' + (padL + 2) + '" y="' + (y - 4).toFixed(1) + '" class="ct" font-size="' + fs + '">' + (v % 1 ? fmt(v) : v.toLocaleString("en-US")) + "</text>"); });
    /* time axis: years, plus months in the daily section */
    var lastLab = -99, prevM = null;
    for (var i = 0; i < n; i++) {
      var d = day(p, i), m = d.getUTCMonth();
      if (prevM !== null && m !== prevM) {
        var isYear = m === 0, daily = i >= p.daily_from, x = X(i) - slot / 2;
        if ((isYear || (daily && (wide ? m % 2 === 0 : m % 3 === 0))) && x - lastLab > (wide ? 44 : 34)) {
          o.push('<line x1="' + x.toFixed(1) + '" x2="' + x.toFixed(1) + '" y1="' + padT + '" y2="' + plotBottom + '" class="' + (isYear ? "cy" : "cg") + '"/><text x="' + (x + 3).toFixed(1) + '" y="' + axisY + '" class="ct" font-size="' + fs + '">' + (isYear ? d.getUTCFullYear() : MON[m]) + "</text>");
          lastLab = x;
        }
      }
      prevM = m;
    }
    var xd = X(p.daily_from) - slot / 2;
    o.push('<text x="' + (xd - 4).toFixed(1) + '" y="' + (padT - 6) + '" class="ct" font-size="' + (fs - 1) + '" text-anchor="end">WEEKLY</text><text x="' + (xd + 4).toFixed(1) + '" y="' + (padT - 6) + '" class="ct" font-size="' + (fs - 1) + '">DAILY</text>' +
      '<line x1="' + xd.toFixed(1) + '" x2="' + xd.toFixed(1) + '" y1="' + (padT - 14) + '" y2="' + plotBottom + '" class="cdiv"/>');
    o.push('<text x="' + (wide ? padL : xEnd) + '" y="' + (padT - 6) + '" class="ct" font-size="' + (fs - 1) + '"' + (wide ? "" : ' text-anchor="end"') + '>AS OF ' + esc(longDate(p.asof).toUpperCase()) + "</text>");
    o.push('<rect x="' + (xNow + slot).toFixed(1) + '" y="' + padT + '" width="' + (xEnd - xNow - slot).toFixed(1) + '" height="' + ph.toFixed(1) + '" class="cfut"/>' +
      '<text x="' + (xEnd - 2).toFixed(1) + '" y="' + axisY + '" class="ct" font-size="' + fs + '" text-anchor="end">+12 MO</text>');
    /* earnings marker in the future zone */
    if (st.has("earn") && p.event) {
      var days = (new Date(p.event.date + "T00:00:00Z") - new Date(p.asof + "T00:00:00Z")) / 864e5;
      if (days > 0 && days <= 366) { var xe = xNow + (xEnd - xNow) * days / 365;
        o.push('<line x1="' + xe.toFixed(1) + '" x2="' + xe.toFixed(1) + '" y1="' + padT + '" y2="' + (padT + ph).toFixed(1) + '" class="cev"/><text x="' + (xe + 4).toFixed(1) + '" y="' + (padT + 12) + '" font-size="' + fs + '" class="ct cev-t">EARNINGS ' + MON[new Date(p.event.date + "T00:00:00Z").getUTCMonth()].toUpperCase() + " " + (+p.event.date.slice(8)) + "</text>"); }
    }
    /* line-end tags for the averages and the last close: placed first so every other label can keep clear of them */
    var yNow = Y(p.last), lt = [], boxes = [];
    if (st.has("ma50") && I.m50[n - 1] != null) lt.push({ y: Y(I.m50[n - 1]), t: "50d " + fmt(I.m50[n - 1]), c: COL.m50 });
    if (st.has("ma200") && I.m200[n - 1] != null) lt.push({ y: Y(I.m200[n - 1]), t: "200d " + fmt(I.m200[n - 1]), c: COL.m200 });
    lt.push({ y: yNow, t: fmt(p.last), now: 1 });
    spread(lt, wide ? 20 : 17, padT + 10, padT + pph - 8).forEach(function (t) {
      t.tw = t.t.length * fs * 0.62 + 10; t.xr = xNow - (wide ? 12 : 9);
      boxes.push({ x0: t.xr - t.tw - 3, x1: xNow + 10, y0: t.y - 10, y1: t.y + 10 });
    });
    /* 52-week references: label above (high) or below (low) the line, slid left of the end tags if they would touch */
    if (st.has("hl")) [[p.hi52, wide ? "52-week high reference " : "52w high "], [p.lo52, wide ? "52-week low reference " : "52w low "]].forEach(function (r, k) {
      var y = Y(r[0]), txt = r[1] + fmt(r[0]), w = txt.length * fs * 0.62, ty = k ? y + 13 : y - 5, x0 = X(p.daily_from) + 2;
      var xs = [x0, x0 - w * 0.5, padL + 34].concat(boxes.map(function (b) { return b.x0 - 6 - w; }), [xNow + slot + 6]), cands = [];
      [ty, k ? y - 5 : y + 13].forEach(function (yy) { xs.forEach(function (x) { cands.push({ x0: x, x1: x + w, y0: yy - fs, y1: yy + 3 }); }); });
      var b = place(cands, boxes, padL + 30, xEnd);
      o.push(hline(y, "cref") + '<text x="' + b.x0.toFixed(1) + '" y="' + (b.y1 - 3).toFixed(1) + '" class="ct cref-t ch" font-size="' + fs + '">' + txt + "</text>");
    });
    /* Bollinger band */
    function line(arr, cls, attr) {
      var dd = "", pen = false;
      arr.forEach(function (v, j) { if (v == null) { pen = false; return; } dd += (pen ? "L" : "M") + X(j).toFixed(1) + " " + Y(v).toFixed(1); pen = true; });
      return '<path d="' + dd + '" class="' + cls + '"' + (attr || "") + "/>";
    }
    if (st.has("bb")) {
      var ub = "", lb = []; I.bbu.forEach(function (v, j) { if (v == null) return; ub += (ub ? "L" : "M") + X(j).toFixed(1) + " " + Y(v).toFixed(1); lb.unshift("L" + X(j).toFixed(1) + " " + Y(I.bbl[j]).toFixed(1)); });
      o.push('<path d="' + ub + lb.join("") + 'Z" class="cbbf"/>' + line(I.bbu, "cbb") + line(I.bbl, "cbb") + line(I.bbm, "cbb", ' stroke-dasharray="2 3"'));
    }
    /* volume */
    if (vh) {
      var vmax = Math.max.apply(null, p.v.filter(function (v) { return v != null; })) || 1, vb = padT + ph, vu = "", vd = "", vw = Math.max(0.6, slot * 0.7);
      p.v.forEach(function (v, j) { if (v == null) return; var hgt = v / vmax * (vh - 4), seg = "M" + (X(j) - vw / 2).toFixed(2) + " " + vb.toFixed(1) + "h" + vw.toFixed(2) + "v" + (-hgt).toFixed(1) + "h" + (-vw).toFixed(2) + "Z";
        if (p.c[j] >= p.o[j]) vu += seg; else vd += seg; });
      o.push('<path d="' + vu + '" fill="' + COL.up + '" opacity=".35"/><path d="' + vd + '" fill="' + COL.dn + '" opacity=".35"/><text x="' + (padL + 2) + '" y="' + (vb - vh + 10).toFixed(1) + '" class="ct" font-size="' + (fs - 1) + '">VOLUME</text>');
    }
    /* price: candles or a close line */
    if (st.mode === "line") {
      o.push(line(p.c, "cline"));
    } else {
      var up = [], dn = [], bw = Math.max(0.6, slot * 0.66), thin = slot < 2.2 ? Math.max(0.7, slot * 0.8) : 1;
      for (i = 0; i < n; i++) {
        var O = p.o[i], C = p.c[i]; if (C == null) continue;
        var x0 = X(i), yt = Y(Math.max(O, C)), yb = Y(Math.min(O, C));
        (C >= O ? up : dn).push({ w: "M" + x0.toFixed(2) + " " + Y(p.h[i]).toFixed(1) + "V" + Y(p.l[i]).toFixed(1),
          b: slot >= 2.2 ? "M" + (x0 - bw / 2).toFixed(2) + " " + yt.toFixed(1) + "h" + bw.toFixed(2) + "v" + Math.max(0.8, yb - yt).toFixed(1) + "h" + (-bw).toFixed(2) + "Z" : "" });
      }
      [[up, COL.up], [dn, COL.dn]].forEach(function (g) {
        o.push('<path d="' + g[0].map(function (c) { return c.w; }).join("") + '" stroke="' + g[1] + '" stroke-width="' + thin.toFixed(2) + '" fill="none"/>');
        var b = g[0].map(function (c) { return c.b; }).join(""); if (b) o.push('<path d="' + b + '" fill="' + g[1] + '"/>');
      });
    }
    if (st.has("ma200")) o.push(line(I.m200, "cma2"));
    if (st.has("ma50")) o.push(line(I.m50, "cma1"));
    /* fan */
    if (paths.length) {
      var fo = [], tags = [];
      paths.forEach(function (s) {
        fo.push('<path d="' + s.pts.map(function (v, j) { return (j ? "L" : "M") + (xNow + (xEnd - xNow) * j / 12).toFixed(1) + " " + Y(v).toFixed(1); }).join("") + '" stroke="' + s.col + '" class="cfan"/>' +
          '<circle cx="' + xEnd.toFixed(1) + '" cy="' + Y(s.pts[12]).toFixed(1) + '" r="2.5" fill="' + s.col + '"/>');
        tags.push({ y: Y(s.pts[12]), s: s });
      });
      spread(tags, wide ? 34 : 28, padT + 12, padT + pph - 16).forEach(function (t) {
        var s = t.s, xt = wide ? xEnd + 10 : xEnd - 6, anc = wide ? "" : ' text-anchor="end"';
        var w = Math.max((s.k ? s.name + " " + sp(s.pct) : s.name).length * lf * 0.64, fmt(s.lvl).length * fs * 0.62), up = lf + 2, dn = wide ? 16 : 14;
        var cands = []; for (var dy = 0; dy <= 72; dy += 4) [dy, -dy].forEach(function (d, q) { if (q && !dy) return; var y = t.y + d; if (y - up < padT - 4 || y + dn > padT + pph + 8) return;
          cands.push({ x0: wide ? xt : xt - w, x1: wide ? xt + w : xt, y0: y - up, y1: y + dn, ty: y }); });
        var b = cands.length ? place(cands, boxes, -1e9, 1e9) : { ty: t.y }, ty = b.ty;
        fo.push('<text x="' + xt.toFixed(1) + '" y="' + (ty - 2).toFixed(1) + '" font-size="' + lf + '" class="cfl ch" fill="' + s.col + '"' + anc + ">" + (s.k ? s.name + " " + sp(s.pct) : wide ? s.name.toUpperCase() : s.name) + "</text>" +
          '<text x="' + xt.toFixed(1) + '" y="' + (ty + (wide ? 13 : 11)).toFixed(1) + '" font-size="' + fs + '" class="ct ch"' + anc + ">" + fmt(s.lvl) + "</text>");
      });
      o.push('<g class="cfang">' + fo.join("") + "</g>");
    }
    /* draw the line-end tags (positions set above) */
    lt.forEach(function (t) {
      var tw = t.tw, xr = t.xr;
      o.push('<rect x="' + (xr - tw).toFixed(1) + '" y="' + (t.y - 8).toFixed(1) + '" width="' + tw.toFixed(1) + '" height="16" rx="3" fill="' + (t.now ? COL.m50 : "#0b0a08") + '"' + (t.now ? "" : ' stroke="' + t.c + '" stroke-opacity=".7"') + "/>" +
        '<text x="' + (xr - tw / 2).toFixed(1) + '" y="' + (t.y + 3.5).toFixed(1) + '" font-size="' + fs + '" text-anchor="middle" class="ctag" fill="' + (t.now ? "#050505" : t.c) + '">' + esc(t.t) + "</text>");
    });
    o.push('<circle cx="' + xNow.toFixed(1) + '" cy="' + yNow.toFixed(1) + '" r="9" fill="#d4af37" opacity=".18"/><circle cx="' + xNow.toFixed(1) + '" cy="' + yNow.toFixed(1) + '" r="4" fill="#d4af37" stroke="#050505" stroke-width="1.5"/>');
    /* sub panels */
    subs.forEach(function (sb) {
      var top = sb[1] + gapP, h = D.sub - gapP - 4, xr0 = padL, xr1 = xNow + slot / 2;
      o.push('<rect x="' + xr0 + '" y="' + top + '" width="' + (xr1 - xr0).toFixed(1) + '" height="' + h + '" class="cpan"/>');
      if (sb[0] === "rsi") {
        var R = function (v) { return top + (100 - v) / 100 * h; };
        o.push('<rect x="' + xr0 + '" y="' + R(70).toFixed(1) + '" width="' + (xr1 - xr0).toFixed(1) + '" height="' + (R(30) - R(70)).toFixed(1) + '" class="crsib"/>');
        [70, 30].forEach(function (v) { o.push('<line x1="' + xr0 + '" x2="' + xr1.toFixed(1) + '" y1="' + R(v).toFixed(1) + '" y2="' + R(v).toFixed(1) + '" class="cg"/><text x="' + (xr1 + 4).toFixed(1) + '" y="' + (R(v) + 3).toFixed(1) + '" class="ct" font-size="' + (fs - 1) + '">' + v + "</text>"); });
        var dd = "", pen = false; I.rsi.forEach(function (v, j) { if (v == null) { pen = false; return; } dd += (pen ? "L" : "M") + X(j).toFixed(1) + " " + R(v).toFixed(1); pen = true; });
        var lr = I.rsi[n - 1];
        o.push('<path d="' + dd + '" class="crsi"/><text x="' + (xr0 + 4) + '" y="' + (top + 12) + '" class="ct" font-size="' + (fs - 1) + '">RSI (14)' + (lr == null ? "" : " " + lr.toFixed(0)) + "</text>");
      } else {
        var mv = I.macd.concat(I.sig, I.hist).filter(function (v) { return v != null; }), mm = Math.max.apply(null, mv.map(Math.abs)) || 1;
        var M = function (v) { return top + h / 2 - v / mm * (h / 2 - 3); }, hu = "", hd = "", hw = Math.max(0.6, slot * 0.7);
        I.hist.forEach(function (v, j) { if (v == null) return; var y1 = M(0), y2 = M(v), seg = "M" + (X(j) - hw / 2).toFixed(2) + " " + y1.toFixed(1) + "h" + hw.toFixed(2) + "V" + y2.toFixed(1) + "h" + (-hw).toFixed(2) + "Z"; if (v >= 0) hu += seg; else hd += seg; });
        var lm = I.macd[n - 1];
        o.push('<line x1="' + xr0 + '" x2="' + xr1.toFixed(1) + '" y1="' + M(0).toFixed(1) + '" y2="' + M(0).toFixed(1) + '" class="cg"/><path d="' + hu + '" fill="' + COL.up + '" opacity=".5"/><path d="' + hd + '" fill="' + COL.dn + '" opacity=".5"/>');
        var pm = "", ps = "", a1 = false, a2 = false;
        I.macd.forEach(function (v, j) { if (v == null) { a1 = false; return; } pm += (a1 ? "L" : "M") + X(j).toFixed(1) + " " + M(v).toFixed(1); a1 = true; });
        I.sig.forEach(function (v, j) { if (v == null) { a2 = false; return; } ps += (a2 ? "L" : "M") + X(j).toFixed(1) + " " + M(v).toFixed(1); a2 = true; });
        o.push('<path d="' + pm + '" class="cmacd"/><path d="' + ps + '" class="cmsig"/><text x="' + (xr0 + 4) + '" y="' + (top + 12) + '" class="ct" font-size="' + (fs - 1) + '">MACD (12, 26, 9)' + (lm == null ? "" : " " + fmt(lm)) + "</text>");
      }
    });
    return { svg: o.join(""), H: H };
  }
  function summary(p, st) {
    var f = p.fan, I = calc(p), n = p.c.length, L = [p.t + " price from " + longDate(p.d0) + " to " + longDate(p.asof) + ", shown as " + (st.mode === "line" ? "a closing price line" : "weekly candles, then daily candles for the last six months") +
      ". Last close " + fmt(p.last) + (p.cur ? " " + p.cur : "") + (p.chg_1y == null ? "" : ", " + sp(p.chg_1y) + " over one year") + "."];
    if (st.has("ma50")) L.push("50-day SMA " + fmt(I.m50[n - 1]) + ".");
    if (st.has("ma200")) L.push("200-day SMA " + fmt(I.m200[n - 1]) + ".");
    if (st.has("bb")) L.push("Bollinger Bands " + fmt(I.bbl[n - 1]) + " to " + fmt(I.bbu[n - 1]) + ".");
    if (st.has("hl")) L.push("52-week high " + fmt(p.hi52) + ", low " + fmt(p.lo52) + ".");
    if (st.has("rsi") && I.rsi[n - 1] != null) L.push("RSI 14 at " + I.rsi[n - 1].toFixed(0) + ".");
    if (st.has("macd") && I.macd[n - 1] != null) L.push("MACD " + fmt(I.macd[n - 1]) + ", signal " + fmt(I.sig[n - 1]) + ".");
    if (st.has("earn") && p.event) L.push("Next earnings " + longDate(p.event.date) + ".");
    if (st.has("fan") && f) L.push("Volatility cone, an illustration from past volatility, not a forecast: centered on no change at " + fmt(p.last) + ", plus one standard deviation " + sp(f.up_pct) + " (" + fmt(f.up) + "), minus one standard deviation " + sp(f.down_pct) + " (" + fmt(f.down) + ").");
    return L.join(" ");
  }
  function table(p) {
    var rows = "", I = calc(p);
    for (var i = 0; i < p.c.length; i++) { var d = day(p, i); if (i < p.c.length - 1 && day(p, i + 1).getUTCMonth() === d.getUTCMonth()) continue;
      rows += "<tr><td>" + MON[d.getUTCMonth()] + " " + d.getUTCFullYear() + "</td><td>" + fmt(p.c[i]) + "</td><td>" + fmt(I.m50[i]) + "</td><td>" + fmt(I.m200[i]) + "</td></tr>"; }
    return '<table class="sr"><caption>' + esc(p.t) + " month-end closes and averages</caption><thead><tr><th>Month</th><th>Close</th><th>50 day average</th><th>200 day average</th></tr></thead><tbody>" + rows + "</tbody></table>";
  }
  function drawChart(box, p) {
    if (box._rg) rgClose(box);
    var plot = box.querySelector(".cplot"), st = state(), D = dims(st), W = Math.round(plot.clientWidth);
    plot.style.height = (D.total + 28) + "px";
    if (!W) return;
    var r = svgChart(p, W, st);
    box.setAttribute("data-w", W);
    plot.innerHTML = '<svg viewBox="0 0 ' + W + " " + r.H + '" width="' + W + '" height="' + r.H + '" role="img" aria-label="' + esc(summary(p, st)) + '">' + r.svg + "</svg>";
  }
  /* phones show the short part of each chip label; the .lx part is visually hidden there, so the accessible name stays the full name */
  var SHORT = { "50-day SMA": ["50-day", " SMA"], "200-day SMA": ["200-day", " SMA"], "Bollinger Bands (20, 2)": ["Bollinger", " Bands (20, 2)"], "RSI (14)": ["RSI", " (14)"],
    "MACD (12, 26, 9)": ["MACD", " (12, 26, 9)"], "52-week range": ["52-week", " range"], "Volatility cone (\u00b11\u03c3)": ["Volatility cone", " (\u00b11\u03c3)"], "Next earnings": ["earnings", "Next ", 1] };
  function chipLabel(name) {
    var s = SHORT[name], sig = function (x) { return x.replace("\u03c3", '<span style="text-transform:none">\u03c3</span>'); };
    if (!s) return sig(name);
    return s[2] ? '<span class="lx">' + s[1] + "</span>" + s[0] : s[0] + '<span class="lx">' + sig(s[1]) + "</span>";
  }
  function chipRow(st) {
    var seg = [["candles", "Candlesticks"], ["line", "Line"]].map(function (m) { return '<button type="button" class="tg seg" data-mode="' + m[0] + '" aria-pressed="' + (st.mode === m[0]) + '">' + m[1] + "</button>"; }).join("");
    return '<div class="tgs" role="group" aria-label="Chart layers"><button type="button" class="tgplay" aria-pressed="false"><span>Play the range</span></button><span class="tgseg" role="group" aria-label="Price style">' + seg + "</span>" +
      LAYERS.map(function (l) { return '<button type="button" class="tg" data-k="' + l[0] + '" aria-pressed="' + st.has(l[0]) + '"><span>' + chipLabel(l[1]) + "</span></button>"; }).join("") + "</div>";
  }
  function chartBox(t) {
    var st = state();
    return '<div class="chartbox" data-t="' + esc(t) + '"><div class="cstats">' + STATS.map(function (l) { return '<div class="cs"><span class="label">' + l + "</span><b>&nbsp;</b></div>"; }).join("") + "</div>" + chipRow(st) +
      '<div class="cplot" style="height:' + (dims(st).total + 28) + 'px"></div><p class="ccap"><strong>Illustration from past volatility, not a forecast.</strong> The volatility cone is centered on no change from the last close. Its edges are plus and minus one standard deviation of the stock\u2019s own yearly moves (daily volatility over up to three years times the square root of 252), so it widens with time. It is a range of typical moves, not an expected price. Candles are weekly, then daily for the last six months; indicators are computed on daily closes. Prices from Yahoo Finance daily bars, split and dividend adjusted. Play the range replays five past dates: each draws 1,000 paths from the stock\u2019s own earlier daily moves, centered on no change, and checks the 10th to 90th band against the real close 20 trading days later. Replay on past data. A range of typical moves, not a forecast. Not investment advice.</p><div class="cdata"></div></div>';
  }
  function wire(box) {
    var pb = box.querySelector(".tgplay");
    if (pb) pb.addEventListener("click", function () { if (box._rg) rgClose(box); else if (box._p) rgOpen(box); });
    [].forEach.call(box.querySelectorAll(".tg"), function (b) {
      b.addEventListener("click", function () {
        var st = state();
        if (b.hasAttribute("data-mode")) st.mode = b.getAttribute("data-mode");
        else { var k = b.getAttribute("data-k"), i = st.on.indexOf(k); if (i >= 0) st.on.splice(i, 1); else st.on.push(k); }
        saveState(st);
        [].forEach.call(box.querySelectorAll(".tg"), function (c) { c.setAttribute("aria-pressed", c.hasAttribute("data-mode") ? String(c.getAttribute("data-mode") === st.mode) : String(st.on.indexOf(c.getAttribute("data-k")) >= 0)); });
        if (box._p) drawChart(box, box._p); else box.querySelector(".cplot").style.height = (dims(st).total + 28) + "px";
      });
    });
  }
  function chart(box) {
    var t = box.getAttribute("data-t");
    wire(box);
    Promise.all([getChart(t), getInd()]).then(function (r) {
      var p = r[0];
      if (!box.isConnected) return;
      box._p = p;
      var f = p.fan, ev = p.event, eb = box.querySelector('[data-k="earn"]');
      if (eb && !ev) { eb.disabled = true; eb.title = "No upcoming earnings date published"; }
      var vals = [fmt(p.last) + (p.cur ? " <small>" + esc(p.cur) + "</small>" : ""), sp(p.chg_1y), fmt(p.lo52) + " <small>to</small> " + fmt(p.hi52),
        f ? (f.sigma * 100).toFixed(0) + "%" : "n/a", ev ? esc(ev.label) + " " + esc(longDate(ev.date)) : "None published"];
      [].forEach.call(box.querySelectorAll(".cs b"), function (b, i) { b.innerHTML = vals[i]; });
      box.querySelector(".cdata").innerHTML = table(p);
      drawChart(box, p);
    }).catch(function () {
      if (!box.isConnected) return;
      box.querySelector(".cs b").textContent = "Chart unavailable";
      box.querySelector(".cplot").innerHTML = '<p class="note" style="padding:16px">The price file could not be loaded. Try again later.</p>';
    });
  }
  var rz; window.addEventListener("resize", function () { clearTimeout(rz); rz = setTimeout(function () {
    [].forEach.call(document.querySelectorAll(".chartbox"), function (b) { if (b._p && +b.getAttribute("data-w") !== Math.round(b.querySelector(".cplot").clientWidth)) drawChart(b, b._p); });
  }, 150); });

  /* ---------- play the range: replay a bootstrap fan on past data, round by round ----------
     Spec: docs/forecast-cone-animation.md. Opt-in only: the static cone stays the default view.
     Paths draw on two canvases inside a stage that covers the plot (absolute, so nothing moves). DOM beats
     (beam, orb, ring) animate transform and opacity only, with the Web Animations API.
     Easing cubic-bezier(.2,.8,.2,1); durations 160 / 600 / 900 ms. Reduced motion: final frame per round, Next button. */
  var RANGE = null, rangeP = null, EASE = "cubic-bezier(.2,.8,.2,1)", D_MICRO = 160, D_BEAT = 600, D_FAN = 900, LAND = 60;
  var RGC = { bg: "#04080b", grid: "#10202a", axis: "#5f7a80", teal: "#3ad6c4", red: "#e0675a", gold: "#d4af37", up: "#5fa97c", dn: "#cb5d46", ink: "#d8e6e6" };
  var NOTE = "Replay on past data. A range of typical moves, not a forecast. Not investment advice.";
  /* timeline of one round, in ms from its start */
  var T_ORB = 450, T_FAN = 900, T_MED = T_FAN + D_FAN, T_LAND = T_MED + 300, T_RING = T_LAND + 20 * LAND, T_END = T_RING + 1100, T_TODAY_END = T_MED + 800;
  function getRange() {
    if (RANGE) return Promise.resolve(RANGE);
    if (!rangeP) rangeP = new Promise(function (ok, no) { var sc = document.createElement("script"); sc.src = "range.js?v=1"; sc.onload = function () { RANGE = window.RANGE; ok(RANGE); }; sc.onerror = no; document.head.appendChild(sc); });
    return rangeP;
  }
  function reduced() { return window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches; }
  function rgPanel() {
    var seg = ""; for (var i = 0; i < 20; i++) seg += "<i></i>";
    return '<div class="rgp"><div class="rgc rgpx"><span class="label">Price</span><b class="rgn">&nbsp;</b><span class="rgd label">&nbsp;</span></div>' +
      '<div class="rgc"><span class="label">Paths ending up vs down</span><div class="rgseg" aria-hidden="true">' + seg + '</div><div class="rgsn"><span><b class="rgu">0</b> up</span><span><b class="rgdn">0</b> down</span></div></div>' +
      '<div class="rgc rghr"><span class="label">Inside the 10th to 90th band</span><div><b class="rgh">n/a</b><span class="rgfr">0/0</span></div></div>' +
      '<div class="rgc rgrc"><span class="label">Regime</span><div class="rgrg"><span class="rgchip">&nbsp;</span><small class="rgrs">&nbsp;</small></div></div>' +
      '<ol class="rglog" aria-label="Replay log"></ol><p class="rgnote">' + NOTE + ' <span class="rgmeth">Each round draws 1,000 paths from the stock\u2019s own past daily moves (centered on no change), then checks the 10th to 90th band against the real close 20 trading days later.</span></p></div>';
  }
  /* Mount a replay stage. o: host (the stage fills it), p (chart data), side (panel inside the stage, right),
     after (element the panel goes after when not side), mainH (height of the price area), single (one round per
     Next, no auto advance), first (first round), closable, onClose */
  function rgMount(o) {
    var st = document.createElement("div"); st.className = "rg"; st.setAttribute("role", "region"); st.setAttribute("aria-label", "Range replay on past data");
    st.innerHTML = '<canvas class="rgb" aria-hidden="true"></canvas><canvas class="rgf" aria-hidden="true"></canvas>' +
      '<div class="rgbeam" aria-hidden="true"><i></i></div><div class="rgorb" aria-hidden="true"><u></u><i></i><b></b></div><div class="rgring" aria-hidden="true"><i></i><span></span></div>' +
      '<div class="rghd"><span class="rgpill label">&nbsp;</span><span class="rgctl">' + (reduced() ? "" : '<button type="button" class="rgbtn rgpause">Pause</button>') +
      '<button type="button" class="rgbtn rgnext">Next</button>' + (o.closable ? '<button type="button" class="rgbtn rgclose" aria-label="Close the range replay">Close</button>' : "") + "</span></div>" +
      '<p class="sr" role="status" aria-live="polite"></p>';
    var panel = document.createElement("div"); panel.innerHTML = rgPanel(); panel = panel.firstChild;
    o.host.appendChild(st);
    if (o.side) { st.appendChild(panel); st.classList.add("rg-side"); } else o.after.parentNode.insertBefore(panel, o.after.nextSibling);
    var R = { p: o.p, st: st, panel: panel, side: o.side, mainH: o.mainH, single: o.single, j: -1, hits: 0, done: 0, paused: false, raf: 0, t: 0, t0: 0, seen: true, rm: reduced(), live: true };
    if (o.closable) st.querySelector(".rgclose").addEventListener("click", function () { o.onClose(); });
    st.querySelector(".rgnext").addEventListener("click", function () { rgNext(R); });
    var pz = st.querySelector(".rgpause");
    if (pz) pz.addEventListener("click", function () { if (R.paused) { R.paused = false; rgResume(R); } else { R.paused = true; rgHalt(R); } pz.textContent = R.paused ? "Resume" : "Pause"; });
    R.onVis = function () { if (document.hidden) rgHalt(R); else rgResume(R); };
    document.addEventListener("visibilitychange", R.onVis);
    if (window.IntersectionObserver) { R.io = new IntersectionObserver(function (e) { R.seen = e[0].isIntersecting; if (R.seen) rgResume(R); else rgHalt(R); }); R.io.observe(st); }
    R.ready = Promise.all([getRange(), Promise.resolve(o.p)]).then(function (r) {
      if (!R.live) return;
      var p = R.p = r[1]; R.days = RANGE.roundDays(p.dc);
      R.cdl = {}; R.date = {};
      for (var i = p.daily_from; i < p.c.length; i++) { R.cdl[p.ix[i]] = i; R.date[p.ix[i]] = day(p, i); }
      rgSize(R); rgRound(R, Math.min(o.first || 0, R.days.length - 1));
    }).catch(function () { rgLog(R, "The range math could not be loaded. Try again later."); });
    return R;
  }
  function rgUnmount(R) {
    R.live = false; rgHalt(R);
    document.removeEventListener("visibilitychange", R.onVis); if (R.io) R.io.disconnect();
    R.st.remove(); R.panel.remove();
  }
  function rgOpen(box) {
    var p = box._p, plot = box.querySelector(".cplot"); if (!p || box._rg) return;
    var btn = box.querySelector(".tgplay");
    btn.setAttribute("aria-pressed", "true"); btn.querySelector("span").textContent = "Hide the range";
    box._rg = rgMount({ host: plot, p: p, side: plot.clientWidth >= 900, after: plot, mainH: dims(state()).main, closable: true, onClose: function () { rgClose(box, true); } });
  }
  function rgClose(box, focus) {
    var R = box._rg; if (!R) return;
    rgUnmount(R); box._rg = null;
    var btn = box.querySelector(".tgplay"); if (btn) { btn.setAttribute("aria-pressed", "false"); btn.querySelector("span").textContent = "Play the range"; if (focus) btn.focus(); }
  }
  function rgSize(R) {
    var w = R.st.clientWidth, h = R.st.clientHeight, dpr = Math.min(2, window.devicePixelRatio || 1);
    R.W = w; R.H = h; R.cw = R.side ? w - 284 : w; R.dpr = dpr;
    [].forEach.call(R.st.querySelectorAll("canvas"), function (c) { c.width = Math.round(R.cw * dpr); c.height = Math.round(h * dpr); c.style.width = R.cw + "px"; c.style.height = h + "px"; });
    R.bx = R.st.querySelector(".rgb").getContext("2d"); R.fx = R.st.querySelector(".rgf").getContext("2d");
    R.mono = getComputedStyle(document.documentElement).getPropertyValue("--mono") || "monospace";
  }
  /* geometry for round j (j === days.length is today) */
  function rgGeo(R, j) {
    var p = R.p, dc = p.dc, today = j >= R.days.length, k = today ? dc.length - 1 : R.days[j], h = today ? RANGE.H_TODAY : RANGE.H_REPLAY;
    var narrow = R.cw < 600, back = today ? (narrow ? 40 : 60) : narrow ? 30 : 40;
    var tagW = narrow ? 92 : 108, x0 = 8, x1 = R.cw - tagW, y0 = 46, y1 = Math.min(R.H, R.mainH || R.H) - 26;
    var s = R.sim, slots = today ? back + 1 : back + 1 + h, hx1 = today ? x0 + (x1 - x0) * 0.56 : x1, slot = (hx1 - x0) / slots, a = Math.max(1, k - back);
    var X = function (i) { return x0 + (i - a + 0.5) * slot; }, xNow = X(k);
    var FX = today ? function (st) { return xNow + st / h * (x1 - xNow); } : function (st) { return X(k + st); };
    var vals = []; for (var i = a; i <= Math.min(dc.length - 1, today ? k : k + h); i++) { var ci = R.cdl[i]; if (ci != null) { vals.push(p.h[ci], p.l[ci]); } else vals.push(dc[i]); }
    var ends = []; for (var q = 0; q < s.n; q++) ends.push(s.cum[q * s.w + h]); ends.sort(function (u, v) { return u - v; });
    vals.push(s.start * Math.exp(RANGE.pct(ends, today ? 0.05 : 0.02)), s.start * Math.exp(RANGE.pct(ends, today ? 0.95 : 0.98)));
    var lo = Math.log(Math.min.apply(null, vals)), hi = Math.log(Math.max.apply(null, vals)), pad = (hi - lo) * 0.08 || 0.02; lo -= pad; hi += pad;
    var Y = function (v) { return y0 + (hi - Math.log(v)) / (hi - lo) * (y1 - y0); };
    return { k: k, h: h, a: a, X: X, FX: FX, Y: Y, x0: x0, x1: x1, y0: y0, y1: y1, slot: slot, xNow: xNow, today: today, lo: lo, hi: hi, drawn: Math.min(s.n, R.cw >= 600 ? 200 : 80) };
  }
  function rgCandle(R, g, i, bright) {
    var c = R.bx, p = R.p, ci = R.cdl[i], x = g.X(i), bw = Math.max(1, g.slot * 0.62);
    if (ci == null) { c.fillStyle = RGC.axis; c.fillRect(x - bw / 2, g.Y(p.dc[i]) - 0.5, bw, 1); return; }
    var O = p.o[ci], C = p.c[ci], col = C >= O ? RGC.up : RGC.dn, yt = g.Y(Math.max(O, C)), yb = g.Y(Math.min(O, C));
    c.globalAlpha = bright ? 1 : 0.8; c.strokeStyle = col; c.fillStyle = col; c.lineWidth = 1;
    c.beginPath(); c.moveTo(Math.round(x) + 0.5, g.Y(p.h[ci])); c.lineTo(Math.round(x) + 0.5, g.Y(p.l[ci])); c.stroke();
    c.fillRect(x - bw / 2, yt, bw, Math.max(1, yb - yt));
    if (bright) { c.globalAlpha = 0.9; c.strokeStyle = RGC.ink; c.strokeRect(x - bw / 2 - 0.5, yt - 0.5, bw + 1, Math.max(1, yb - yt) + 1); }
    c.globalAlpha = 1;
  }
  function rgBase(R, g) {
    var c = R.bx, dpr = R.dpr; c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, R.cw, R.H);
    var fs = R.cw < 600 ? 10 : 11; c.font = fs + "px " + R.mono; c.textBaseline = "alphabetic";
    niceTicks(Math.exp(g.lo), Math.exp(g.hi), 4).forEach(function (v) { var y = g.Y(v); if (y < g.y0 + 6 || y > g.y1 - 4) return;
      c.fillStyle = RGC.grid; c.fillRect(g.x0, Math.round(y) + 0.5, g.x1 - g.x0, 1); c.fillStyle = RGC.axis; c.fillText(fmt(v), g.x0 + 2, y - 4); });
    if (g.today) { c.fillStyle = "rgba(58,214,196,.035)"; c.fillRect(g.xNow, g.y0, g.x1 - g.xNow, g.y1 - g.y0); c.fillStyle = RGC.axis; c.textAlign = "right"; c.fillText("+12 MO", g.x1, g.y1 + 18); c.textAlign = "left"; }
    else { c.fillStyle = RGC.axis; c.textAlign = "right"; c.fillText("+20 DAYS", g.FX(g.h), g.y1 + 18); c.textAlign = "left"; }
    var d0 = R.date[g.a]; if (d0) c.fillText(MON[d0.getUTCMonth()].toUpperCase() + " " + d0.getUTCDate(), g.x0 + 2, g.y1 + 18);
    for (var i = g.a; i <= g.k; i++) rgCandle(R, g, i, false);
  }
  /* draw path segments for steps (s0, s1] of the drawn subset; teal when the path ends above the start, red below */
  function rgFan(R, g, s0, s1) {
    var c = R.fx, s = R.sim, w = s.w, st = s.start;
    c.setTransform(R.dpr, 0, 0, R.dpr, 0, 0); c.save(); c.beginPath(); c.rect(0, g.y0 - 6, R.cw, g.y1 - g.y0 + 12); c.clip();
    c.globalCompositeOperation = "lighter"; c.lineJoin = "round";
    [[true, RGC.teal], [false, RGC.red]].forEach(function (grp) {
      c.beginPath();
      for (var q = 0; q < g.drawn; q++) {
        var o = q * w; if ((s.cum[o + g.h] > 0) !== grp[0]) continue;
        c.moveTo(g.FX(s0), g.Y(st * Math.exp(s.cum[o + s0])));
        for (var t = s0 + 1; t <= s1; t++) c.lineTo(g.FX(t), g.Y(st * Math.exp(s.cum[o + t])));
      }
      c.strokeStyle = grp[1]; c.globalAlpha = 0.05; c.lineWidth = 3; c.stroke();
      c.globalAlpha = g.drawn > 100 ? 0.16 : 0.24; c.lineWidth = 1; c.stroke();
    });
    c.restore();
  }
  function rgMedian(R, g) {
    var c = R.fx, s = R.sim, fs = R.cw < 600 ? 10 : 11;
    c.beginPath(); s.med.forEach(function (v, t) { if (t) c.lineTo(g.FX(t), g.Y(v)); else c.moveTo(g.FX(0), g.Y(v)); });
    c.strokeStyle = RGC.gold; c.lineJoin = "round";
    [[7, 0.1], [3.5, 0.25], [1.6, 1]].forEach(function (k) { c.lineWidth = k[0]; c.globalAlpha = k[1]; c.stroke(); });
    c.globalAlpha = 1; c.font = "600 " + fs + "px " + R.mono;
    var tags = spread([{ y: g.Y(s.p90), t: "90TH " + fmt(s.p90), c: RGC.teal }, { y: g.Y(s.p50), t: "50TH " + fmt(s.p50), c: RGC.gold }, { y: g.Y(s.p10), t: "10TH " + fmt(s.p10), c: RGC.red }], fs + 10, g.y0 + 8, g.y1 - 8);
    var xe = g.FX(g.h);
    tags.forEach(function (t) {
      var tw = c.measureText(t.t).width + 10, x = xe + 6;
      c.fillStyle = "rgba(4,8,11,.92)"; c.fillRect(x, t.y - fs / 2 - 4, tw, fs + 8); c.strokeStyle = t.c; c.lineWidth = 1; c.strokeRect(x + 0.5, t.y - fs / 2 - 3.5, tw - 1, fs + 7);
      c.fillStyle = t.c; c.fillText(t.t, x + 5, t.y + fs / 2 - 1);
    });
  }
  function rgAnim(el, kf, o) { if (reduced() || !el.animate) return null; return el.animate(kf, Object.assign({ easing: EASE, fill: "both" }, o)); }
  function rgPlace(el, x, y) { el.style.transform = "translate(" + x.toFixed(1) + "px," + y.toFixed(1) + "px)"; }
  function rgLog(R, txt) {
    var ol = R.panel.querySelector(".rglog"), li = document.createElement("li"); li.textContent = txt; ol.appendChild(li);
    while (ol.children.length > 6) ol.removeChild(ol.firstChild);
  }
  function rgSplit(R, up) {
    [].forEach.call(R.panel.querySelectorAll(".rgseg i"), function (c, i) { c.className = i < Math.round(up / 5) ? "u" : "d"; });
    R.panel.querySelector(".rgu").textContent = up; R.panel.querySelector(".rgdn").textContent = 100 - up;
  }
  function rgPrice(R, v, d) { R.panel.querySelector(".rgn").textContent = fmt(v); R.panel.querySelector(".rgd").textContent = d ? longDate(d.toISOString().slice(0, 10)).toUpperCase() : " "; }
  function rgRound(R, j) {
    var p = R.p, today = j >= R.days.length;
    if (j > R.days.length) return;
    R.j = j; R.t = 0; R.fired = {}; R.fanAt = 0; R.landed = 0;
    R.sim = today ? RANGE.today(p.dc, p.t) : RANGE.replay(p.dc, p.t, j, R.days[j]);
    var g = R.g = rgGeo(R, j), s = R.sim, d = R.date[g.k];
    R.fx.setTransform(R.dpr, 0, 0, R.dpr, 0, 0); R.fx.clearRect(0, 0, R.cw, R.H);
    R.st.querySelector(".rgf").classList.remove("dim");
    rgBase(R, g);
    var ds = d ? MON[d.getUTCMonth()].toUpperCase() + " " + d.getUTCDate() + ", " + d.getUTCFullYear() : "";
    var nar = R.cw < 600;
    R.st.querySelector(".rgpill").textContent = today ? (nar ? "TODAY · 12 MONTHS" : "TODAY · 12-MONTH RANGE") : "ROUND " + (j + 1) + "/" + R.days.length + (nar ? " · " + ds.replace(/, \d+$/, "") : " · REPLAY FROM " + ds);
    R.st.querySelector(".rgnext").textContent = today ? "Replay again" : "Next";
    var beam = R.st.querySelector(".rgbeam"), orb = R.st.querySelector(".rgorb"), ring = R.st.querySelector(".rgring");
    beam.style.height = g.y1 + "px"; rgPlace(beam, g.xNow, 0); rgPlace(orb, g.xNow, g.Y(s.start));
    ring.style.opacity = "0"; orb.querySelector("b").style.opacity = ""; orb.querySelector("b").textContent = today ? "NOW" : "FROM HERE";
    rgPrice(R, s.start, d);
    var rg = s.regime, chip = R.panel.querySelector(".rgchip");
    chip.textContent = rg.label; chip.className = "rgchip " + (rg.label === "TRENDING" ? "tr" : "ch");
    R.panel.querySelector(".rgrs").textContent = "50-day slope " + sp(rg.slope * 100) + ", efficiency " + rg.eff.toFixed(2);
    rgLog(R, (today ? "Today, " : "Round " + (j + 1) + ", ") + ds + ": " + s.n + " paths from " + fmt(s.start) + (today ? " over 12 months." : " over 20 trading days, using only moves before this date."));
    if (R.rm) { rgFinish(R); return; }
    beam.style.opacity = "1"; orb.style.opacity = "1";
    R.anims = [rgAnim(beam.firstChild, [{ transform: "scaleY(0)", opacity: 0 }, { transform: "scaleY(1)", opacity: 1 }], { duration: D_BEAT }),
      rgAnim(orb.firstChild, [{ transform: "scale(.2)", opacity: 0 }, { transform: "scale(1)", opacity: 1 }], { duration: D_MICRO * 2, delay: T_ORB }),
      rgAnim(orb.querySelector("b"), [{ opacity: 0, transform: "translateY(4px)" }, { opacity: 1, transform: "none" }], { duration: D_MICRO, delay: T_ORB + D_MICRO })].filter(Boolean);
    rgResume(R, true);
  }
  /* all beats of the current round at once (reduced motion, Next, or the end of the clock) */
  function rgFinish(R) {
    var g = R.g, s = R.sim;
    if (R.fanAt < g.h) { rgFan(R, g, R.fanAt, g.h); R.fanAt = g.h; }
    if (!R.fired.med) { R.fired.med = 1; rgMedian(R, g); rgSplit(R, s.upPct); }
    if (g.today) { if (!R.fired.end) { R.fired.end = 1; rgVerdict(R); } return; }
    while (R.landed < g.h) rgLand(R);
    if (!R.fired.ring) { R.fired.ring = 1; rgVerdict(R); }
  }
  function rgLand(R) {
    var g = R.g; R.landed++; var i = g.k + R.landed;
    rgCandle(R, g, i, true); rgPrice(R, R.p.dc[i], R.date[i]);
    if (R.landed === 1) R.st.querySelector(".rgf").classList.add("dim");
  }
  function rgVerdict(R) {
    var g = R.g, s = R.sim, live = R.st.querySelector("[role=status]");
    if (g.today) {
      rgLog(R, "12-month range from past daily moves: 10th " + fmt(s.p10) + ", median " + fmt(s.p50) + ", 90th " + fmt(s.p90) + ".");
      live.textContent = "Today: 12-month range " + fmt(s.p10) + " to " + fmt(s.p90) + ". Replay finished, " + R.hits + " of " + R.days.length + " rounds inside the band.";
      return;
    }
    if (s.hit) R.hits++; R.done++;
    var ring = R.st.querySelector(".rgring"), x = g.FX(g.h), y = g.Y(s.real);
    rgPlace(ring, x, y); ring.className = "rgring " + (s.hit ? "hit" : "miss") + (y > g.y1 - 40 ? " lo" : ""); ring.querySelector("span").textContent = s.hit ? "HIT" : "MISS";
    ring.style.opacity = "1"; R.st.querySelector(".rgorb b").style.opacity = "0";
    rgAnim(ring.firstChild, [{ transform: "scale(.3)", opacity: 0 }, { transform: "scale(1.15)", opacity: 1, offset: 0.6 }, { transform: "scale(1)", opacity: 1 }], { duration: D_BEAT });
    rgAnim(ring.querySelector("span"), [{ opacity: 0 }, { opacity: 1 }], { duration: D_MICRO, delay: D_MICRO });
    R.panel.querySelector(".rgh").textContent = Math.round(R.hits / R.done * 100) + "%";
    R.panel.querySelector(".rgfr").textContent = R.hits + "/" + R.done;
    var msg = "Real close 20 trading days later " + fmt(s.real) + ": " + (s.hit ? "HIT, inside" : "MISS, outside") + " the 10th to 90th band (" + fmt(s.p10) + " to " + fmt(s.p90) + ").";
    rgLog(R, msg);
    live.textContent = "Round " + (R.j + 1) + " of " + R.days.length + ": " + (s.hit ? "HIT" : "MISS") + ". " + msg;
  }
  function rgNext(R) {
    if (!R.days) return;
    if (R.j >= R.days.length) { R.hits = 0; R.done = 0; R.panel.querySelector(".rgh").textContent = "n/a"; R.panel.querySelector(".rgfr").textContent = "0/0"; rgHalt(R); rgRound(R, 0); return; }
    rgHalt(R); rgFinish(R); rgRound(R, R.j + 1);
  }
  function rgHalt(R) {
    if (R.raf) { cancelAnimationFrame(R.raf); R.raf = 0; R.t = performance.now() - R.t0; }
    if (R.anims) R.anims.forEach(function (a) { if (a.playState === "running") a.pause(); });
    if (R.pulse && R.pulse.playState === "running") R.pulse.pause();
  }
  function rgResume(R, fresh) {
    if (R.rm || R.raf || R.paused || !R.days || (!fresh && R.over) || document.hidden || !R.seen) return;
    if (fresh) R.over = false;
    R.t0 = performance.now() - R.t;
    if (R.anims) R.anims.forEach(function (a) { if (a.playState === "paused") a.play(); });
    if (R.pulse && R.pulse.playState === "paused") R.pulse.play();
    R.raf = requestAnimationFrame(function f(now) { R.raf = 0; if (rgTick(R, now - R.t0)) R.raf = requestAnimationFrame(f); else R.t = now - R.t0; });
  }
  /* one frame: returns true while there is more to do */
  function rgTick(R, t) {
    var g = R.g, s = R.sim, budget = performance.now() + 6;
    if (!R.fired.pulse && t >= T_ORB) { R.fired.pulse = 1; R.pulse = rgAnim(R.st.querySelector(".rgorb u"), [{ transform: "scale(.6)", opacity: 0.8 }, { transform: "scale(2.6)", opacity: 0 }], { duration: D_BEAT * 1.5, iterations: 3, fill: "none", easing: "linear" }); }
    if (t >= T_FAN && R.fanAt < g.h) {
      var e = Math.min(1, (t - T_FAN) / D_FAN), target = Math.ceil(g.h * (1 - Math.pow(1 - e, 3)));
      while (R.fanAt < target && performance.now() < budget) { var nx = Math.min(target, R.fanAt + Math.max(1, Math.ceil(g.h / 40))); rgFan(R, g, R.fanAt, nx); R.fanAt = nx; }
    }
    if (t >= T_MED && R.fanAt >= g.h && !R.fired.med) { R.fired.med = 1; rgMedian(R, g); rgSplit(R, s.upPct);
      rgLog(R, "Spread: 10th " + fmt(s.p10) + ", median " + fmt(s.p50) + ", 90th " + fmt(s.p90) + ". " + s.upPct + "% of paths end up."); }
    if (g.today) { if (t >= T_TODAY_END && R.fired.med) { rgFinish(R); R.over = true; return false; } return true; }
    if (t >= T_LAND) while (R.landed < g.h && t >= T_LAND + R.landed * LAND) rgLand(R);
    if (t >= T_RING && R.landed >= g.h && !R.fired.ring) { R.fired.ring = 1; rgVerdict(R); }
    if (t >= T_END && R.fired.ring) { if (R.single) { R.over = true; return false; } rgRound(R, R.j + 1); return false; }
    return true;
  }

  /* ---------- fundamentals card (stock page) ---------- */
  var FUND = [
    ["fwd_pe", "Forward P/E", "Price divided by expected earnings for the next 12 months; analysts use it to compare how much the market pays for future profit across peers."],
    ["ttm_pe", "Trailing P/E", "Price divided by the last 12 months of reported earnings; the classic check of what you pay for profit already earned."],
    ["ev_ebitda", "EV/EBITDA", "Company value including debt, divided by operating cash earnings; used to compare businesses with different debt and tax setups."],
    ["consensus_gap", "Analyst consensus gap", "How far the average published analyst estimate sits from the last close, shown as context on sentiment. It is not a forecast."],
    ["sector", "Sector", "The industry group; analysts compare a stock's multiples with its own sector, not the whole market."],
    ["mcap", "Market cap", "Share price times shares outstanding; used to size a company and pick its peer group."]
  ];
  function fundCard(F) {
    if (!F) return "";
    var val = function (k) { var v = F[k]; if (v == null) return '<span class="na">n/a</span>';
      if (k === "consensus_gap") return sp(v * 100) + (F.analysts ? ' <small>' + F.analysts + " analysts</small>" : "");
      if (k === "mcap") return big(v) + (F.cur ? " <small>" + esc(F.cur) + "</small>" : "");
      if (k === "sector") return esc(v); return v.toFixed(1) + "x"; };
    return '<section class="fund" aria-labelledby="fund-h"><h2 id="fund-h">Fundamentals</h2><div class="fgrid">' + FUND.map(function (f, i) {
      return '<div class="fc"><span class="label">' + f[1] + ' <button type="button" class="info" aria-label="What ' + f[1] + ' means" aria-describedby="ft' + i + '">i</button><span role="tooltip" id="ft' + i + '" class="tip">' + f[2] + '</span></span><b>' + val(f[0]) + "</b></div>";
    }).join("") + '</div><p class="note">As reported by Yahoo Finance in the latest scan. Figures can be stale or missing. Not investment advice.</p></section>';
  }

  /* ---------- link from lookup results ---------- */
  function link(res, t) {
    get().then(function (d) {
      var card = res.querySelector(".card"); if (!card || !d.stocks[t] || card.querySelector(".v5link")) return;
      var p = document.createElement("p"); p.className = "v5link";
      p.innerHTML = '<a class="btn" href="#/stock/' + encodeURIComponent(t) + '">See the scanner\'s call history for ' + esc(t) + "</a>";
      card.insertBefore(p, card.querySelector(".note:last-child") || null);
    }).catch(function () {});
  }

  /* ---------- stock page ---------- */
  function lensCard(k, c) {
    if (!c) return '<div class="hz"><span class="label">' + NAMES[k] + '</span><p class="note">Not scored in the latest scan.</p></div>';
    var called = c.label === "Bullish" || c.label === "Bearish";
    return '<div class="hz"><span class="label">' + NAMES[k] + "</span><div class=\"r1\" style=\"margin-top:8px\">" + chip(c.label) +
      '<span class="label">' + (called ? "Called" : "No call") + "</span></div>" +
      '<ul class="why" style="margin-left:0">' + c.reasons.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul></div>";
  }
  function stock(root, sym) {
    sym = String(sym || "").split("?")[0];
    root.innerHTML = '<section class="hero"><span class="label">Stock</span><p class="lede">Loading...</p></section>';
    root.classList.add("boot"); /* keep the footer below the fold until the page is drawn (no layout shift) */
    get().then(function (d) {
      root.classList.remove("boot");
      var t = (sym || "").toUpperCase(), s = d.stocks[t] || d.stocks[sym];
      if (location.hash.indexOf("#/stock") !== 0) return;
      if (!s) {
        root.innerHTML = '<section class="hero"><span class="label">Stock</span><h1>No call on <em>' + esc(sym) + '.</em></h1><p class="lede">Stock pages exist only for names the scanner has made a Bullish or Bearish call on. You can still <a href="#/lookup/' + encodeURIComponent(sym) + '">look it up</a>. Not investment advice.</p></section>';
        return;
      }
      var cur = ORDER.map(function (k) { return lensCard(k, s.current[k]); }).join("");
      var dates = {}, byLens = {};
      s.history.forEach(function (h) { dates[h.date] = 1; (byLens[h.lens] = byLens[h.lens] || []).push(h); });
      var hist = ORDER.filter(function (k) { return byLens[k]; }).map(function (k) {
        return "<tr><td><b>" + NAMES[k] + '</b></td><td>' + byLens[k].map(function (h) {
          return esc(h.date) + " " + chip(h.call) + (h.score == null ? "" : ' <span class="label" style="white-space:nowrap">score ' + Math.round(h.score) + "</span>");
        }).join("<br>") + "</td></tr>";
      }).join("");
      var gr = s.graded.length ? '<div class="twrap"><div class="tw" tabindex="0" role="region" aria-label="Graded calls"><table><thead><tr><th>Called</th><th>View</th><th>Call</th><th>Window</th><th>Stock</th><th>Vs S&amp;P</th></tr></thead><tbody>' +
        s.graded.map(function (g) { return "<tr><td>" + esc(g.date) + "</td><td>" + esc(NAMES[g.lens]) + "</td><td>" + esc(g.call) + '</td><td class="num">' + g.window + 'd</td><td class="num">' + pctTxt(g.stock_return) + '</td><td class="num">' + pctTxt(g.excess) + "</td></tr>"; }).join("") +
        "</tbody></table></div></div>" : '<p class="note">Not graded yet. A call is graded from the next trading day\'s close, over 5, 20 and 60 trading days.</p>';
      var n = Object.keys(dates).length;
      root.innerHTML = '<section class="hero"><span class="label">' + esc("Stock | " + (s.index ? s.index + " | " : "") + (s.sector || "")) + "</span><h1>" + esc(t) + ' <em style="font-size:.5em">' + esc(s.name) + "</em></h1>" +
        '<p class="lede">What the scanner currently says in each view, how its calls on this name have changed, and how they graded.</p>' +
        '<p class="v5link"><a class="btn ghost" href="#/lookup/' + encodeURIComponent(t) + '">Open in lookup</a></p></section>' +
        (s.chart ? '<section class="csec" aria-label="Price chart"><h2>Three years of price</h2>' + chartBox(t) + "</section>" : "") + fundCard(s.fund) +
        '<section><h2>Current call by view</h2><div class="hzs">' + cur + "</div></section>" +
        "<section><h2>Call and score history</h2><p class=\"note\" style=\"margin-top:6px\">" + n + " logged date" + (n === 1 ? "" : "s") + (n === 1 ? ". Only one scan so far, so there is no trend to show yet." : ".") + '</p><div class="twrap hist"><div class="tw" tabindex="0" role="region" aria-label="Call history"><table><tbody>' + hist + "</tbody></table></div></div></section>" +
        "<section><h2>Graded calls</h2>" + gr + '<p class="note">Mechanical rules on past data, not a forecast. Not investment advice.</p></section>';
      var cb = root.querySelector(".chartbox"); if (cb) chart(cb);
    }).catch(function () { root.classList.remove("boot"); root.innerHTML = '<section class="hero"><h1>Stock data <em>unavailable.</em></h1><p class="lede">Not investment advice.</p></section>'; });
  }

  /* tooltips close on Escape and on a tap outside. Escape keeps focus on the info button (the tip hides, nothing moves);
     the tip comes back on the next focus change or once the pointer leaves the label */
  var root = document.documentElement;
  function tipsOff() { root.classList.add("tipx"); }
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" || e.key === "Esc") tipsOff(); });
  document.addEventListener("pointerdown", function (e) {
    var lb = e.target.closest && e.target.closest(".fc .label");
    if (lb) { root.classList.remove("tipx"); return; }
    tipsOff();
    var a = document.activeElement; if (a && a.classList && a.classList.contains("info")) a.blur();
  });
  document.addEventListener("focusin", function () { root.classList.remove("tipx"); });
  document.addEventListener("mouseout", function (e) {
    var lb = e.target.closest && e.target.closest(".fc .label");
    if (lb && !(e.relatedTarget && lb.contains(e.relatedTarget))) root.classList.remove("tipx");
  });

  /* ---------- landing hero: one replay round on a featured stock ----------
     Featured = the stock page with the largest market cap among USD listings (a size rule, not a pick). */
  function featured(d) {
    var best = null, bm = -1;
    Object.keys(d.stocks).sort().forEach(function (t) { var s = d.stocks[t], f = s.fund || {}; if (!s.chart) return; var m = f.cur === "USD" && f.mcap ? f.mcap : 0; if (m > bm) { bm = m; best = t; } });
    return best;
  }
  function hero(o) {
    var dP = get(), R = rgMount({ host: o.host, p: dP.then(function (d) { return getChart(featured(d)); }), side: o.side, after: o.after, single: true, first: 4 });
    dP.then(function (d) { var t = featured(d); if (o.onTicker) o.onTicker(t, d); }).catch(function () {});
    return R;
  }
  window.V5 = { hero: hero, unmount: rgUnmount, data: get, featured: featured, changes: changes, report: report, link: link, stock: stock, chartBox: chartBox, chart: chart };
})();
