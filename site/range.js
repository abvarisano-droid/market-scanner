/* Pure math for "Play the range" on the stock chart. No DOM. Loaded by v5.js on demand; also run by
   tests/test_range.py through Node and checked against an independent Python version.
   Honest framing: paths are a bootstrap of the stock's own past daily log returns, demeaned so the
   center is "no change". It is a range of typical moves, not a forecast.
   Inputs are daily closes (oldest first). Every random draw comes from a seeded generator, so the same
   ticker always gives the same paths. */
(function (root) {
  "use strict";
  var N_STATS = 1000, H_REPLAY = 20, H_TODAY = 252, SPACING = 15, ROUNDS = 5, MIN_POOL = 120;

  /* FNV-1a 32-bit hash of a string, then mulberry32: small, fast and easy to reproduce in Python */
  function hash(s) {
    var h = 2166136261;
    for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; }
    return h >>> 0;
  }
  function rng(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  /* numpy's default percentile (linear interpolation between closest ranks) on a sorted array */
  function pct(sorted, q) {
    var h = (sorted.length - 1) * q, lo = Math.floor(h), hi = Math.min(sorted.length - 1, lo + 1);
    return sorted[lo] + (h - lo) * (sorted[hi] - sorted[lo]);
  }
  /* log returns that end on or before day k, demeaned */
  function pool(dc, k) {
    var r = [], s = 0;
    for (var i = 1; i <= k; i++) { var v = Math.log(dc[i] / dc[i - 1]); r.push(v); s += v; }
    var m = s / r.length;
    return r.map(function (v) { return v - m; });
  }
  /* Simulate N_STATS paths of h steps from day k. Returns cumulative log moves (Float64Array, path-major,
     h + 1 values per path, first is 0), the 10th, 50th and 90th percentile end prices, the per-step median
     path and the share of paths that end above the start. */
  function simulate(dc, k, h, seedStr) {
    var r = pool(dc, k), m = r.length, next = rng(hash(seedStr)), w = h + 1, cum = new Float64Array(N_STATS * w);
    for (var p = 0; p < N_STATS; p++) {
      var acc = 0, o = p * w;
      for (var s = 1; s <= h; s++) { acc += r[Math.floor(next() * m)]; cum[o + s] = acc; }
    }
    var start = dc[k], col = new Float64Array(N_STATS), med = [0], up = 0;
    for (s = 1; s <= h; s++) {
      for (p = 0; p < N_STATS; p++) col[p] = cum[p * w + s];
      col.sort();
      med.push(pct(col, 0.5));
    }
    for (p = 0; p < N_STATS; p++) if (cum[p * w + h] > 0) up++;
    return { k: k, h: h, start: start, cum: cum, w: w, n: N_STATS,
      p10: start * Math.exp(pct(col, 0.1)), p50: start * Math.exp(pct(col, 0.5)), p90: start * Math.exp(pct(col, 0.9)),
      med: med.map(function (v) { return start * Math.exp(v); }), upPct: Math.round(up / N_STATS * 100) };
  }
  function sma(dc, k, n) { var s = 0; for (var i = k - n + 1; i <= k; i++) s += dc[i]; return s / n; }
  /* Regime at day k. slope: 50-day average now versus 20 trading days earlier. efficiency: net move over the
     last 20 days divided by the sum of the absolute daily moves (1 = a straight line, near 0 = back and forth).
     TRENDING when |slope| >= 3% and efficiency >= 0.30, else CHOPPY. */
  function regime(dc, k) {
    var slope = sma(dc, k, 50) / sma(dc, k - 20, 50) - 1, path = 0;
    for (var i = k - 19; i <= k; i++) path += Math.abs(dc[i] - dc[i - 1]);
    var eff = path ? Math.abs(dc[k] - dc[k - 20]) / path : 0;
    return { label: Math.abs(slope) >= 0.03 && eff >= 0.3 ? "TRENDING" : "CHOPPY", slope: slope, eff: eff };
  }
  /* The five replay dates: the last one ends its 20-day window on the latest close; each earlier one starts
     15 trading days before. Dates without enough history are dropped. */
  function roundDays(dc) {
    var last = dc.length - 1, out = [];
    for (var j = ROUNDS - 1; j >= 0; j--) { var k = last - H_REPLAY - SPACING * j; if (k - 1 >= MIN_POOL && k >= 70) out.push(k); }
    return out;
  }
  function replay(dc, t, j, k) {
    var sim = simulate(dc, k, H_REPLAY, t + "|" + j), real = dc[k + H_REPLAY];
    sim.real = real; sim.hit = real >= sim.p10 && real <= sim.p90; sim.regime = regime(dc, k);
    return sim;
  }
  function today(dc, t) {
    var k = dc.length - 1, sim = simulate(dc, k, H_TODAY, t + "|today");
    sim.regime = regime(dc, k);
    return sim;
  }
  /* the numbers only, for tests and the page's self-check */
  function summary(dc, t) {
    var days = roundDays(dc), hits = 0, rounds = days.map(function (k, j) {
      var s = replay(dc, t, j, k); if (s.hit) hits++;
      return { k: k, start: s.start, p10: s.p10, p50: s.p50, p90: s.p90, real: s.real, hit: s.hit, upPct: s.upPct, regime: s.regime.label };
    });
    var td = today(dc, t);
    return { rounds: rounds, hits: hits, today: { p10: td.p10, p50: td.p50, p90: td.p90, upPct: td.upPct, regime: td.regime.label } };
  }
  var api = { hash: hash, rng: rng, pct: pct, pool: pool, simulate: simulate, regime: regime, roundDays: roundDays,
    replay: replay, today: today, summary: summary, H_REPLAY: H_REPLAY, H_TODAY: H_TODAY, N_STATS: N_STATS };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.RANGE = api;
})(this);
