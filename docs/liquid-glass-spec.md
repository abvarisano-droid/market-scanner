# Liquid Glass (dark): spec

Filled from WEB_DESIGN_REFERENCE.md section 6 before any markup. Branch `claude/liquid-glass`.
The scanner gets the same Liquid Glass system as the personal site (`assets/glass.css` there), in a
dark variant that keeps the black and gold identity. Visual only: every feature, route, chart layer
and word stays, apart from four listed fixes. The whole theme is one marked block at the end of
`site/style.css` (no extra request, so no LCP cost); delete that block to roll back.

## Alternatives compared (1280 px, home)

Screenshots: `ms-lg-alt-a-1280.png`, `ms-lg-alt-b-1280.png`, `ms-lg-alt-c-1280.png` (scratchpad, not committed).

| | Layout | Verdict |
|---|---|---|
| A. Open mesh | One strong page-wide gold mesh, the hero is open type on it, every section a blurred glass card | Most "liquid", but the mesh competes with the gold data (bars, chips, the 50-day line) and blur on every card cost frames. Gold stops meaning "signal". |
| B. Gold slab | The hero and funnel sit in one floating glass slab with a slow gold light behind it; sticky glass pill nav; everything below is quiet glass panels on near-black | **Chosen.** One signature moment, black stays black, gold stays the data color, and every text block sits on a known surface so contrast holds. |
| C. Banded | Edge-to-edge frosted bands per section, square corners | Reads as stripes, not glass; the bands fight the two-column lists and the slab moment is lost. |

## Spec

```
SITE: Market Scanner (static, hash routes: scan, lookup, stock, long-term, how it works, track record)
ONE SIGNATURE MOMENT: home hero. The headline, lede and funnel field live on one dark glass slab;
  a warm gold light drifts slowly behind it (26s). Everything else is still glass.
WEBSITE MAP: unchanged. Home: hero slab (funnel, story, by index), sector heat, what changed,
  index chips, lens tabs, bullish and bearish lists. Lookup: search, card with chart. Stock: head,
  chart, fundamentals, current calls, history, graded. Long-term: filter bar, table. How: method
  sections. Track: ring and stats, report card, graded table.

TYPE (unchanged from the live site, pinned here)
  display + body: Iowan Old Style / Palatino / Georgia stack, weight 400 (600 for names)
  labels, chips, numbers: system mono stack
  scale: h1 34-76 (clamp 8.5vw) / h2 26-38 / h3 22-24 / stat numbers 22-54 / body 16 / small 13-14 /
    label 11 mono +.14em uppercase / chip 10 mono +.1em uppercase
  line-height: body 1.55, headings 1.04-1.1
PALETTE (dark only)
  bg #050505 / text #ebe6d8 / muted #8d8777 (raised to #9a9483 on glass) / gold #d4af37 / bear #cb5d46
  glass fill: linear rgba(255,244,214,.065) to rgba(255,244,214,.025) over the bg (reads about #0f0e0b)
  glass strong (slab, popovers): rgba(16,14,11,.72)
  edge: 1px rgba(236,224,186,.13), top highlight inset 0 1px 0 rgba(255,248,228,.10)
  gold light fields (background only, never under small text without glass): rgba(212,175,55,.10-.22)
  contrast on the brightest glass (#1a1710 measured): text 13.9:1, muted 5.6:1, gold 8.4:1, bear 4.9:1
SPACING
  4px base; page gutter 16 (phone) / 32 (760+); panel padding 16 phone, 22 desktop; max width 1200
RADII / BORDERS / SHADOWS
  slab 28px (20 phone), panels 18px, inner tiles 12px, pills 999px
  border 1px edge token plus the inset top highlight
  shadow 0 1px 0 rgba(0,0,0,.5), 0 24px 60px -28px rgba(0,0,0,.85)
MOTION
  easing: cubic-bezier(.2,.8,.2,1) (the site's existing curve); light field ease-in-out
  durations: chip and hover 200ms, reveal 700ms (unchanged), light drift 26s alternate loop
  distances: drift up to 5% translate, 6deg rotate; no hover lifts on data panels
  properties: transform + opacity only
  reduced-motion fallback: light field static (global rule already stops every animation)
SCROLL SYSTEM
  smooth scroll: Lenis n (native). Pinned: the nav pill is sticky. Triggers: none new.
MEDIA
  no images or video added; the light is CSS gradients (zero bytes)
  static fallback: light renders still under reduced motion; without backdrop-filter or with
  prefers-reduced-transparency the nav pill is a solid rgba(10,9,7,.97)
  live backdrop blur only on the sticky nav pill (sharp text scrolls under it); panels are
  translucent without a live blur (measured, see Build notes)
PERF TARGETS
  Lighthouse mobile 98+ (perf), a11y 95+, CLS 0.00, LCP under 2s on 4G, no external requests
```

## Fixes in the same branch

1. 390 px chart toggles no longer scroll sideways: the row wraps, and on phones each chip shows a
   short visible label (the rest is visually hidden, so the accessible name stays the full name).
2. Volatility cone labels no longer collide with the moving-average and last-close end tags or the
   52-week reference labels: the chart places every label box and moves cone labels (then 52-week
   labels) to the nearest free spot.
3. How it works: "analyst target" is now "analyst estimate".
4. `scanner/data.py` `earnings_dates` has `timeout=10` (yfinance's calendar takes no timeout, so it
   runs in a worker thread and gives up after 10 seconds).

## Build notes

- Blur measured (headless Chromium, 1280 px, scripted scroll, frames per second): with a 16px
  backdrop blur on every panel, home dropped to 27 to 30, a stock page to 27 and How it works to 20.
  Without panel blur all three sit at 55 to 61. The nav pill blur costs nothing measurable (home 56
  to 58 with it, 58 to 60 without), so it stays; panels are translucent glass with no live blur.
- Phones: the nav pill is not sticky under 760 px (it wraps to two lines there and would cost
  80 px of every screen).
- CLS: the slab keeps the loading hero's 56px top margin (a smaller margin collapsed through `main`
  and moved it 36 px when the scan loaded), and `main` has `min-height:100vh` so the footer stays
  below the first screen while lookup, long-term and how it works load their data (main had a
  0.25 footer shift there on a direct visit).
- Chips: 390 px now wraps to three rows of short labels inside the chart panel; nothing scrolls.
- Chart labels: checked on 9 tickers at 390, 768 and 1280 px with every layer on: no two labels
  overlap (measured from rendered text boxes).
- Muted text raised from #8d8777 to #9a9483 so it holds AA on the brightest part of the slab.
- Script and style URLs bumped to `?v=8` so returning visitors get the new files.

## Results

- Lighthouse mobile, local server with gzip, three runs each: home 100 / 100 / 100 / 100
  (LCP 1.3 to 1.5 s, CLS 0, TBT 40 to 70 ms); stock page with all layers 100 / 100 / 100 / 100
  (LCP 1.4 s, CLS 0).
- axe (WCAG 2 A and AA) clean on home, lookup, stock, long-term, how, track at 390 and 1280.
- Playwright at 390 and 1280 on the same six views: 0 console errors, no horizontal overflow, no
  external requests, "Not investment advice" on every view.

## Anti-slop checklist (section 7)

- [x] One signature moment (home slab with drifting gold light), everything else still glass.
- [x] 3 layout alternatives generated and compared (A, B, C above; B chosen).
- [x] Type scale explicit (pinned above, unchanged from the live site).
- [x] Motion in numbers: 26s drift, 5% and 6deg, 200ms chips, 700ms reveal, cubic-bezier(.2,.8,.2,1).
- [x] Transform/opacity only (the drift keyframes are translate3d and rotate).
- [x] Reduced-motion fallback: light static, every animation off (existing global rule).
- [x] Static fallback: no 3D or video; light renders still; solid nav pill without backdrop-filter
      or with reduced transparency.
- [x] Mobile first: wrapped chips, non-sticky phone pill, 16px gutters, no hover-only content.
- [x] Lighthouse 98+ (100), CLS 0.00, LCP 1.3 to 1.5 s on the mobile profile.
- [x] A specific decision: black stays black, gold stays the data color, one slab of light.
