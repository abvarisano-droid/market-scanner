/* Kronos model range card on stock pages (2026-11-02). Spec: docs/kronos-range.md.
   A model range, not a prediction. Not investment advice.
   Static: one inline SVG (no animation, so nothing to reduce for reduced motion) inside the replay's stage colors, and
   the replay's panel cells (.rgc, .rgseg, .rgh) for the numbers. Data: data/kronos/<T>.json, written each night by
   scripts/kronos_bands.py. The section keeps a fixed stage height from the first paint, so filling it moves nothing. */
(function () {
  var COL = { grid: "#10202a", axis: "#5f7a80", teal: "#34e0d6", red: "#ff7a45", median: "#d9f9f7", ink: "#d8e6e6" };
  var H = 220, IDX = null;
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function fmt(v) { if (v == null) return "n/a"; var a = Math.abs(v); return v.toFixed(a >= 1000 ? 0 : a >= 100 ? 1 : 2); }
  function pct(v) { return (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%"; }
  function shell() {
    var seg = ""; for (var i = 0; i < 20; i++) seg += "<i></i>";
    return '<h2>Kronos model range</h2><div class="kx"><div class="kxstage" style="height:' + H + 'px"><p class="kxwait label">Loading the Kronos range</p></div>' +
      '<div class="rgp kxp"><div class="rgc rgpx"><span class="label">Last close</span><b class="rgn kxlast">&nbsp;</b><span class="label kxasof">&nbsp;</span></div>' +
      '<div class="rgc"><span class="label">Paths ending up vs down</span><div class="rgseg" aria-hidden="true">' + seg + '</div><div class="rgsn"><span><b class="kxu">0</b> up</span><span><b class="kxd">0</b> down</span></div></div>' +
      '<div class="rgc rghr"><span class="label">Held its p10 to p90 range</span><div><b class="rgh kxh">n/a</b><span class="rgfr kxfr">no days scored yet</span></div><small class="rgbase">A well calibrated 10th to 90th band holds about 8 in 10 days.</small></div>' +
      '<p class="rgnote kxnote">A model range, not a prediction. Not investment advice.</p></div></div>';
  }
  function svg(d, W) {
    var hist = d.hist || [], n = hist.length, m = d.p50.length, padL = 8, padR = 64, padT = 14, padB = 22;
    var slot = (W - padL - padR) / Math.max(1, n + m - 1), X = function (i) { return padL + i * slot; };
    var vals = hist.map(function (h) { return h[1]; }).concat(d.p10, d.p90);
    (d.paths || []).forEach(function (p) { vals = vals.concat(p); });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), pad = (hi - lo) * 0.06 || 1;
    lo -= pad; hi += pad;
    var Y = function (v) { return padT + (hi - v) / (hi - lo) * (H - padT - padB); }, x0 = X(n - 1), o = [];
    [0.25, 0.5, 0.75].forEach(function (f) { var y = padT + f * (H - padT - padB); o.push('<line x1="' + padL + '" x2="' + (W - padR) + '" y1="' + y.toFixed(1) + '" y2="' + y.toFixed(1) + '" stroke="' + COL.grid + '"/>'); });
    o.push('<line x1="' + x0.toFixed(1) + '" x2="' + x0.toFixed(1) + '" y1="' + padT + '" y2="' + (H - padB) + '" stroke="' + COL.teal + '" stroke-opacity=".5" stroke-dasharray="3 3"/>');
    var up = "", dn = [];
    for (var j = 0; j < m; j++) { up += (j ? "L" : "M") + X(n + j).toFixed(1) + " " + Y(d.p90[j]).toFixed(1); dn.unshift("L" + X(n + j).toFixed(1) + " " + Y(d.p10[j]).toFixed(1)); }
    o.push('<path d="M' + x0.toFixed(1) + " " + Y(d.base).toFixed(1) + up.replace(/^M/, "L") + dn.join("") + 'Z" fill="' + COL.teal + '" fill-opacity=".10"/>');
    (d.paths || []).forEach(function (p) {
      var c = p[p.length - 1] >= d.base ? COL.teal : COL.red;
      o.push('<path d="M' + x0.toFixed(1) + " " + Y(d.base).toFixed(1) + p.map(function (v, k) { return "L" + X(n + k).toFixed(1) + " " + Y(v).toFixed(1); }).join("") + '" stroke="' + c + '" stroke-opacity=".28" stroke-width="1" fill="none"/>');
    });
    o.push('<path d="M' + x0.toFixed(1) + " " + Y(d.base).toFixed(1) + d.p50.map(function (v, k) { return "L" + X(n + k).toFixed(1) + " " + Y(v).toFixed(1); }).join("") + '" stroke="' + COL.median + '" stroke-width="1.6" fill="none"/>');
    if (n) o.push('<path d="' + hist.map(function (h, k) { return (k ? "L" : "M") + X(k).toFixed(1) + " " + Y(h[1]).toFixed(1); }).join("") + '" stroke="' + COL.ink + '" stroke-width="1.4" fill="none"/>');
    o.push('<circle cx="' + x0.toFixed(1) + '" cy="' + Y(d.base).toFixed(1) + '" r="3.5" fill="' + COL.teal + '"/>');
    var xr = X(n + m - 1) + 6, tags = [["p90", d.p90[m - 1]], ["p50", d.p50[m - 1]], ["p10", d.p10[m - 1]]], last = -99;
    tags.forEach(function (t) { var y = Math.max(Y(t[1]) + 3, last + 13); last = y;
      o.push('<text x="' + xr.toFixed(1) + '" y="' + y.toFixed(1) + '" fill="' + (t[0] === "p50" ? COL.median : COL.teal) + '" font-size="10" font-family="var(--mono)">' + t[0] + " " + fmt(t[1]) + "</text>"); });
    o.push('<text x="' + padL + '" y="' + (H - 6) + '" fill="' + COL.axis + '" font-size="10" font-family="var(--mono)">last ' + n + " closes</text>");
    o.push('<text x="' + (x0 + 6).toFixed(1) + '" y="' + (H - 6) + '" fill="' + COL.axis + '" font-size="10" font-family="var(--mono)">next ' + m + " trading days (model)</text>");
    var label = d.t + " Kronos model range from the " + d.asof + " close of " + fmt(d.base) + ": after " + m + " trading days the paths run from " + fmt(d.p10[m - 1]) +
      " (10th percentile) to " + fmt(d.p90[m - 1]) + " (90th), middle " + fmt(d.p50[m - 1]) + ". A model range, not a prediction.";
    return '<svg viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="' + esc(label) + '">' + o.join("") + "</svg>";
  }
  function fill(sec, d) {
    var st = sec.querySelector(".kxstage"), W = Math.round(st.clientWidth) || 320;
    st.innerHTML = svg(d, W);
    sec._kx = d;
    sec.querySelector(".kxlast").textContent = fmt(d.base) + (d.cur ? " " + d.cur : "");
    sec.querySelector(".kxasof").textContent = "as of " + d.asof;
    var u = Math.round(d.up / d.paths_n * 20), dn = Math.round(d.down / d.paths_n * 20);
    [].forEach.call(sec.querySelectorAll(".rgseg i"), function (el, i) { el.className = i < u ? "u" : i >= 20 - dn ? "d" : ""; });
    sec.querySelector(".kxu").textContent = d.up;
    sec.querySelector(".kxd").textContent = d.down;
    var h = d.held || { held: 0, scored: 0, window: 20 };
    sec.querySelector(".kxh").textContent = h.scored ? h.held + "/" + h.scored : "n/a";
    sec.querySelector(".kxfr").textContent = h.scored >= h.window ? "last " + h.window + " days" : h.scored ? "fewer than " + h.window + " days so far" : "no days scored yet";
    var end = d.p50[d.p50.length - 1] / d.base - 1;
    sec.querySelector(".kxnote").textContent = d.held_text + " Middle path " + pct(end) + " over " + d.horizon + " trading days. " + d.method + " A model range, not a prediction. Not investment advice.";
  }
  function empty(sec, why) {
    sec.querySelector(".kxstage").innerHTML = '<p class="kxwait label">' + esc(why) + "</p>";
  }
  function mount(sec, t) {
    if (!sec) return;
    sec.innerHTML = shell();
    /* the index lists the pages that have a range, so a page without one makes no failing request */
    if (!IDX) IDX = fetch("data/kronos/index.json").then(function (r) { if (!r.ok) throw new Error("index"); return r.json(); })
      .catch(function (e) { IDX = null; throw e; });  /* a failed index is fetched again on the next page */
    IDX.then(function (ix) {
      if (!ix || !ix.pages || !Object.prototype.hasOwnProperty.call(ix.pages, t)) throw new Error("none");
      return fetch("data/kronos/" + encodeURIComponent(t) + ".json?v=" + encodeURIComponent(ix.pages[t] || ""));
    }).then(function (r) { if (!r.ok) throw new Error("none"); return r.json(); }).then(function (d) {
      if (!sec.isConnected) return;
      if (!d || !d.p50 || !d.p50.length) throw new Error("bad");
      fill(sec, d);
    }).catch(function () { if (sec.isConnected) empty(sec, "No Kronos range for this page yet. Ranges refresh each night for up to 36 stock pages."); });
  }
  var rz; window.addEventListener("resize", function () { clearTimeout(rz); rz = setTimeout(function () {
    [].forEach.call(document.querySelectorAll(".kxsec"), function (s) { if (s._kx && s.isConnected) fill(s, s._kx); });
  }, 150); });
  window.KRONOS = { mount: mount };
})();
