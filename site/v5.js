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
    root.innerHTML = '<section class="hero"><span class="label">Stock</span><p class="lede">Loading...</p></section>';
    get().then(function (d) {
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
      root.innerHTML = '<section class="hero"><span class="label">' + esc((s.index ? s.index + " | " : "") + (s.sector || "")) + "</span><h1>" + esc(t) + ' <em style="font-size:.5em">' + esc(s.name) + "</em></h1>" +
        '<p class="lede">What the scanner currently says in each view, how its calls on this name have changed, and how they graded.</p>' +
        '<p class="v5link"><a class="btn ghost" href="#/lookup/' + encodeURIComponent(t) + '">Open in lookup</a></p></section>' +
        '<section><h2>Current call by view</h2><div class="hzs">' + cur + "</div></section>" +
        "<section><h2>Call and score history</h2><p class=\"note\" style=\"margin-top:6px\">" + n + " logged date" + (n === 1 ? "" : "s") + (n === 1 ? ". Only one scan so far, so there is no trend to show yet." : ".") + '</p><div class="twrap hist"><div class="tw" tabindex="0" role="region" aria-label="Call history"><table><tbody>' + hist + "</tbody></table></div></div></section>" +
        "<section><h2>Graded calls</h2>" + gr + '<p class="note">Mechanical rules on past data, not a forecast. Not investment advice.</p></section>';
    }).catch(function () { root.innerHTML = '<section class="hero"><h1>Stock data <em>unavailable.</em></h1><p class="lede">Not investment advice.</p></section>'; });
  }

  window.V5 = { changes: changes, report: report, link: link, stock: stock };
})();
