/* Merger arb desk page. Reads data/arb.json (written by scripts/refresh_arb.py), draws a sortable table and a
   detail panel with every term's source and its verified or Unverified flag. The selected deal lives in the URL
   hash (#MKTX), never in storage. Not investment advice. */
(function () {
  "use strict";
  var rowsEl = document.getElementById("arb-rows"), panel = document.getElementById("arb-panel");
  var table = document.getElementById("arb-table");
  var S = { deals: [], key: "target", dir: 1, sel: null };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function pct(x, d) { return x == null ? "Unknown" : (x * 100).toFixed(d == null ? 2 : d) + "%"; }
  function usd(x) { return x == null ? "Unknown" : "$" + Number(x).toFixed(2); }
  function v(d, k) { return d[k] ? d[k].value : null; }
  function terms(d) {
    var c = v(d, "cash_per_share"), r = v(d, "exchange_ratio"), a = v(d, "acquirer_ticker"), out = [];
    if (c != null) out.push("$" + Number(c).toFixed(2) + " cash");
    if (r != null) out.push(r + " " + (a || "acquirer") + " shares");
    if (!out.length) out.push("Unknown");
    return out.join(" + ") + (v(d, "cvr") ? " + CVR" : "");
  }
  function unverifiedCalc(d) {
    return ["cash_per_share", "exchange_ratio", "unaffected_price"].some(function (k) { return d[k] && !d[k].verified && d[k].value != null; });
  }
  function sortVal(d, k) {
    var c = d.calc || {};
    return { target: v(d, "target_ticker"), acquirer: v(d, "acquirer"), terms: c.offer_value, spread: c.spread,
      annualized: c.annualized, days: c.days_to_close, chance: c.implied_chance, open: c.open_steps }[k];
  }

  function sorted() {
    return S.deals.slice().sort(function (a, b) {
      var x = sortVal(a, S.key), y = sortVal(b, S.key);
      if (x == null && y == null) return 0;
      if (x == null) return 1;   // unknowns always last
      if (y == null) return -1;
      if (typeof x === "string") return S.dir * x.localeCompare(y);
      return S.dir * (x - y);
    });
  }

  function drawRows() {
    rowsEl.innerHTML = sorted().map(function (d) {
      var c = d.calc || {}, ch = c.implied_chance, on = d.id === S.sel;
      var neg = c.spread != null && c.spread < 0;
      return '<tr' + (on ? ' class="on"' : "") + '>' +
        '<td class="stk"><button type="button" class="arb-pick" data-id="' + esc(d.id) + '" aria-pressed="' + on + '">' +
          '<b class="tk">' + esc(v(d, "target_ticker")) + '</b><span class="nm">' + esc(v(d, "target")) + "</span></button></td>" +
        '<td class="wrap"><span>' + esc(v(d, "acquirer")) + "</span></td>" +
        '<td class="num">' + esc(terms(d)) + "<small>offer " + esc(usd(c.offer_value)) + "</small></td>" +
        '<td class="num r' + (neg ? " neg" : "") + '">' + pct(c.spread) + "</td>" +
        '<td class="num r' + (c.annualized != null && c.annualized < 0 ? " neg" : "") + '">' + pct(c.annualized, 1) + "</td>" +
        '<td class="num r">' + (c.days_to_close == null ? "Unknown" : esc(c.days_to_close)) + "</td>" +
        '<td class="num"><span class="arb-ch"><span class="track"><span class="fill" style="transform:scaleX(' + (ch == null ? 0 : ch) + ')"></span></span>' +
          pct(ch, 0) + (unverifiedCalc(d) ? ' <small title="Uses an unverified input">U</small>' : "") + "</span></td>" +
        '<td class="num r">' + esc(c.open_steps) + "</td></tr>";
    }).join("");
    [].forEach.call(table.querySelectorAll("th"), function (th) {
      var b = th.querySelector("button");
      if (b && b.getAttribute("data-k") === S.key) th.setAttribute("aria-sort", S.dir > 0 ? "ascending" : "descending");
      else th.removeAttribute("aria-sort");
    });
  }

  function flag(f) {
    if (!f) return '<span class="chip neutral">Unknown</span>';
    return f.verified ? '<span class="chip">Verified</span>' : '<span class="chip bear">Unverified</span>';
  }
  function src(f) {
    return f && f.source_url ? '<span class="arb-src"><a href="' + esc(f.source_url) + '" rel="noopener" target="_blank">Source</a> <span class="label">as of ' + esc(f.as_of) + "</span></span>" : "";
  }
  function fact(label, f, shown) {
    var val = shown != null ? shown : f && f.value != null ? f.value : "Unknown";
    return "<div><dt>" + esc(label) + "</dt><dd><span class=\"arb-v\">" + esc(val) + "</span> " + flag(f) + " " + src(f) +
      (f && f.note ? '<span class="arb-note">' + esc(f.note) + "</span>" : "") + "</dd></div>";
  }

  function drawPanel(focus) {
    var d = S.deals.filter(function (x) { return x.id === S.sel; })[0];
    if (!d) return;
    var c = d.calc || {}, ec = d.expected_close || {};
    var close = ec.value ? ec.value + (ec.by_date ? " (date used: " + ec.by_date + ")" : "") : "Unknown";
    panel.innerHTML =
      '<p class="label">' + esc(v(d, "target_ticker")) + " deal</p>" +
      '<h2 id="arb-panel-h">' + esc(v(d, "target")) + "</h2>" +
      '<p class="arb-sub">Acquirer: ' + esc(v(d, "acquirer")) + "</p>" +
      '<div class="arb-stats">' +
        '<div><span class="label">Price</span><b>' + esc(usd(c.target_price)) + '</b><small>close ' + esc(c.price_date || "") + "</small></div>" +
        '<div><span class="label">Offer value</span><b>' + esc(usd(c.offer_value)) + "</b><small>" + esc(c.kind) + "</small></div>" +
        '<div><span class="label">Spread</span><b class="' + (c.spread < 0 ? "neg" : "") + '">' + pct(c.spread) + "</b><small>" + (c.spread_usd == null ? "" : (c.spread_usd < 0 ? "-$" : "$") + Math.abs(c.spread_usd).toFixed(2) + " a share") + "</small></div>" +
        '<div><span class="label">Annualized</span><b>' + pct(c.annualized, 1) + "</b><small>" + (c.days_to_close == null ? "close date unknown" : c.days_to_close + " days") + "</small></div>" +
      "</div>" +
      "<h3>Terms</h3><dl class=\"arb-facts\">" +
        fact("Cash per share", d.cash_per_share, v(d, "cash_per_share") == null ? "None" : usd(v(d, "cash_per_share"))) +
        fact("Exchange ratio", d.exchange_ratio, v(d, "exchange_ratio") == null ? "None" : v(d, "exchange_ratio") + " " + (v(d, "acquirer_ticker") || "") + " per share") +
        fact("CVR", d.cvr, v(d, "cvr") || "None") +
        fact("Acquirer ticker", d.acquirer_ticker, v(d, "acquirer_ticker") || "Not listed") +
        fact("Agreement date", d.agreement_date) +
        fact("Announced", d.announce_date) +
        fact("Announced after the close", d.announced_after_close, v(d, "announced_after_close") ? "Yes" : "No") +
        fact("Expected close", d.expected_close, close) +
        fact("Unaffected price", d.unaffected_price, usd(v(d, "unaffected_price")) + (d.unaffected_price && d.unaffected_price.date ? " (close " + d.unaffected_price.date + ")" : "")) +
      "</dl>" +
      "<h3>Steps</h3><ul class=\"arb-steps\">" + (d.steps || []).map(function (s) {
        return '<li><span class="chip' + (s.status === "open" ? " bear" : "") + '">' + esc(s.status === "open" ? "Open" : "Done") + "</span> <b>" + esc(s.name) + "</b> " +
          flag(s) + " " + src(s) + (s.note ? '<span class="arb-note">' + esc(s.note) + "</span>" : "") + "</li>";
      }).join("") + "</ul>" +
      '<p class="arb-note">Implied chance ' + pct(c.implied_chance, 0) + ": rough, assumes the stock falls back to the unaffected price if the deal breaks. Not investment advice.</p>";
    panel.classList.remove("in");
    void panel.offsetWidth;  // restart the fade (transform and opacity only)
    panel.classList.add("in");
    if (focus) panel.focus({ preventScroll: window.matchMedia("(min-width: 1500px)").matches });
  }

  function select(id, focus) {
    S.sel = id;
    try { history.replaceState(null, "", "#" + encodeURIComponent(id)); } catch (e) { /* file:// or sandboxed */ }
    drawRows();
    drawPanel(focus);
  }

  table.addEventListener("click", function (e) {
    var b = e.target.closest("button");
    if (!b) return;
    if (b.classList.contains("arb-pick")) { select(b.getAttribute("data-id"), true); return; }
    var k = b.getAttribute("data-k");
    if (!k) return;
    S.dir = S.key === k ? -S.dir : (k === "target" || k === "acquirer" || k === "days" ? 1 : -1);
    S.key = k;
    drawRows();
  });

  fetch("data/arb.json").then(function (r) {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).then(function (data) {
    S.deals = data.deals || [];
    document.getElementById("arb-asof").textContent = S.deals.length + " deals \u00b7 prices as of " + (data.as_of || "unknown") + " \u00b7 terms as of " + (data.deals_as_of || "unknown");
    document.getElementById("asof").textContent = "(prices as of " + (data.as_of || "unknown") + ", terms as of " + (data.deals_as_of || "unknown") + ")";
    var want = decodeURIComponent(location.hash.replace(/^#/, ""));
    var ids = S.deals.map(function (d) { return d.id; });
    S.sel = ids.indexOf(want) >= 0 ? want : (sorted()[0] || {}).id;
    drawRows();
    drawPanel(false);
  }).catch(function () {
    document.getElementById("arb-asof").textContent = "Deal data could not be loaded";
    rowsEl.innerHTML = '<tr><td colspan="8">The deal file could not be loaded. Try again later. Not investment advice.</td></tr>';
  });
})();
