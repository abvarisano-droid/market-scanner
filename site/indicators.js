/* Pure indicator math for the price chart. No DOM. Loaded by v5.js on demand; also run by
   tests/test_indicators.py through Node to check it against a pandas reference.
   All inputs are arrays of daily closes (oldest first); outputs line up index for index, null until warm. */
(function (root) {
  "use strict";
  function sma(a, n) {
    var out = [], s = 0;
    for (var i = 0; i < a.length; i++) { s += a[i]; if (i >= n) s -= a[i - n]; out.push(i >= n - 1 ? s / n : null); }
    return out;
  }
  /* exponential average seeded with the first value (pandas ewm(span=n, adjust=False)) */
  function ema(a, n) {
    var k = 2 / (n + 1), out = [], e = null;
    for (var i = 0; i < a.length; i++) { e = e == null ? a[i] : a[i] * k + e * (1 - k); out.push(e); }
    return out;
  }
  /* Bollinger Bands: n day simple average plus and minus m population standard deviations */
  function bollinger(a, n, m) {
    var mid = sma(a, n), up = [], lo = [];
    for (var i = 0; i < a.length; i++) {
      if (mid[i] == null) { up.push(null); lo.push(null); continue; }
      var v = 0; for (var j = i - n + 1; j <= i; j++) v += (a[j] - mid[i]) * (a[j] - mid[i]);
      var sd = Math.sqrt(v / n); up.push(mid[i] + m * sd); lo.push(mid[i] - m * sd);
    }
    return { mid: mid, up: up, lo: lo };
  }
  /* RSI with Wilder smoothing (alpha 1/n, seeded with the first change), 0 to 100 */
  function rsi(a, n) {
    var out = [null], g = null, l = null, al = 1 / n;
    for (var i = 1; i < a.length; i++) {
      var d = a[i] - a[i - 1], up = d > 0 ? d : 0, dn = d < 0 ? -d : 0;
      g = g == null ? up : up * al + g * (1 - al); l = l == null ? dn : dn * al + l * (1 - al);
      out.push(i < n ? null : l === 0 ? (g === 0 ? 50 : 100) : 100 - 100 / (1 + g / l));
    }
    return out;
  }
  /* MACD: fast EMA minus slow EMA, signal EMA of that, histogram the gap; null until the slow EMA is warm */
  function macd(a, f, s, sig) {
    var ef = ema(a, f), es = ema(a, s), line = ef.map(function (v, i) { return v - es[i]; }), sg = ema(line, sig);
    var warm = s + sig - 2;
    return { macd: line.map(function (v, i) { return i < warm ? null : v; }), signal: sg.map(function (v, i) { return i < warm ? null : v; }),
      hist: line.map(function (v, i) { return i < warm ? null : v - sg[i]; }) };
  }
  function pick(arr, ix) { return ix.map(function (i) { return arr[i] == null ? null : arr[i]; }); }
  var api = { sma: sma, ema: ema, bollinger: bollinger, rsi: rsi, macd: macd, pick: pick };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.IND = api;
})(this);
