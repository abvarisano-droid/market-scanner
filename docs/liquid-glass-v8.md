# Liquid Glass v8: Market Scanner

Source: the shared v8 spec in the Brain (`Resources/design/liquid-glass-v8.md`, approved by Ashton 2026-11-01). Restyle only: no facts, data files, routes or replay math changed. The replay (`site/range.js`, seeded bootstrap of demeaned past daily log returns, 10th to 90th band, 20 trading days) behaves exactly as before, with the same honest framing.

## Spec (WEB_DESIGN_REFERENCE section 6)

```
SITE: Market Scanner (static, site/)
ONE SIGNATURE MOMENT: the replay card on the landing, filled with the gold accent gradient, the dark replay instrument sunk into it
WEBSITE MAP: #/ (replay hero, KPI tiles, ways in), #/scan, #/lookup, #/longterm, #/how, #/track, #/stock/<ticker>

TYPE
  display: serif (Iowan Old Style, Palatino, Georgia fallback; no web font request) / 400
  scale: 12 / 13.5 / 15 / 18 / 28 / 40 px; page titles clamp(32px, 4.4vw, 54px)
  tracking: titles -0.018em, labels +0.08em uppercase
  body: system sans / 15px / 1.55; tickers and the replay panel stay mono
PALETTE
  bg #120d08 / surface rgba(34,27,19,.62) on #221b13 / text #f3eee2 / muted #a8a191 / accent #d4af37 to #8f7424
  hero card gradient #e6c656 to #a8862c with ink #17110a
  status: green #4ade80, red #f87171 (always with a word or sign)
SPACING
  base 4px, canvas padding 36px desktop / 16px phone, main max 1200px (1360px from 1600px)
RADII / BORDERS / SHADOWS
  shell 30, card 22, tile 18, field 14, pill 9999; edge 1px rgba(255,255,255,.13); shell shadow 0 40px 80px -24px rgba(0,0,0,.55)
MOTION
  easing: cubic-bezier(.2,.8,.2,1)
  durations: state 160ms, view entry 320ms, (replay keeps its own 160 / 600 / 900ms)
  distances: hover lift 3px, view entry 8px rise, press scale .97 to .98
  properties: transform + opacity only
  reduced-motion fallback: no entry, no lift, no sheen; presses dim instead of scale (existing rule)
SCROLL SYSTEM
  native scroll, no Lenis; rail is sticky inside the shell; index chips snap
MEDIA
  none added; no 3D or video sections
PERF TARGETS
  Lighthouse perf 95+, a11y 95+, CLS 0.00, LCP under 2s on 4G. No backdrop-filter at all (the room is already soft light), one extra CSS file (lg8.css, about 9 KB)
```

## Three layouts compared (screenshots: scratchpad lg8/market-scanner/alts.png)

| | A: rail + shell | B: top pill + shell | C: rail + shell + widget column |
|---|---|---|---|
| Replay size at 1920 | wide, side panel inside | widest, but pushed down by the nav | wide, side panel inside |
| KPI tiles | below the fold | below the fold | in view, floating beside the replay |
| At 1280 | replay keeps its side panel (host about 950px with the 200px rail and 24px padding used from 900 to 1365px) | same | replay drops to the stacked panel (host under 900px) |
| Matches the reference | close | weakest (no rail) | closest |

Picked: A below 1600px and C from 1600px. The rail tested better than the pill (B): it frees vertical space so the replay and its panel sit fully above the fold, and it is the reference's main move. C only kicks in where the replay still gets its 900px side panel, so the replay never changes behaviour.

## Anti-slop checklist (section 7)
- One signature moment (the gold replay card); everything else is quiet glass. Yes.
- 3 layouts generated and compared. Yes (above).
- Type scale explicit. Yes.
- Motion in numbers. Yes.
- Transform/opacity only. Yes (lg8.css and the v8 block in style.css).
- Reduced-motion fallback. Yes; plus reduced-transparency (solid fills) and more-contrast (stronger edges, flat gold).
- Static fallback for 3D or video. Not applicable.
- Mobile first with touch equivalents: phones get a bottom tab bar (5 items, 52px targets), Replay lives on the brand link. Yes.
- CLS 0.000 measured at 390, 1280, 1600 and 1920 on every view; no console errors, no horizontal overflow, axe clean.
- A specific decision: gold card with dark ink, teal instrument inside, warm lit room. Yes.

## Roll back
Delete the "Liquid Glass v8" blocks at the end of `site/style.css`, `site/lg8.css`, the `v8shell` / `v8canvas` wrappers and rail icons in `site/index.html`, and `kpis()` in `site/app.js`.
