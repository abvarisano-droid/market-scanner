# Apple design audit: Market Scanner site

Audited 2026-10-31 against Ashton's Apple design guide (response, interruptibility, springs, spatial consistency,
materials, accessibility signals, type, wayfinding, labels). Method: `site/` served locally, Playwright Chromium at
390 and 1280 px on home, lookup, stock (BKNG), long-term, how it works and track record, with computed-style and
interaction probes (press transform, focus after a lens switch, counters after a step back, target sizes, media
query coverage). Branch `claude/apple-design`. The Liquid Glass look, layout B, data, wording and features stay as
they were; every change is one marked block at the end of `site/style.css` plus small edits in `site/app.js` and
`site/v5.js`.

## Ranked issues, worst first

| # | Issue (rule) | Measured | Status |
|---|---|---|---|
| 1 | No press feedback on any control (response on press-down). Buttons, lens tabs, chart chips, sector tiles, nav links and the info dots only change on release. | 0 `:active` rules in the stylesheet; transform while held: `none`. | Fixed: `:active` scale .97 (tiles .98) in 100ms ease-out, release 160ms on the glass curve; funnel stage cells highlight on press; an empty passive `touchstart` listener so iOS Safari shows `:active`. |
| 2 | A lens tab switch rebuilds the whole home view and throws away what the reader was doing (interruptibility, agency): keyboard focus drops to `body`, the funnel story restarts at step 1, the selected sector is cleared. | Focus after tab click: `BODY`. Phone readers who had stepped through the funnel were sent back to 1 of 4. | Fixed: the funnel keeps its step (drawn instantly, no autoplay restart), the selected sector is restored, focus returns to the pressed tab. |
| 3 | Funnel counters snap instead of moving from the live value (animate from the presentation value). Tapping an earlier step or interrupting autoplay reset counters to their final or zero values in one frame. | Step back from 4 to 1: later counters jumped straight to 0. | Fixed: counters interpolate from the number on screen to the new target (step back now counts down: 638, 359, 0). |
| 4 | Touch targets under 44 px on phones (flexibility, HIG). | Nav links 28 px tall, lens tabs 32, chart chips 32, buttons 34, info dots 24. | Fixed: nav, tabs and buttons 44 px under 760 px; chips 36 px plus a 3 px invisible hit ring (42 px, no overlap with the 6 px gap); info dots get a 10 px hit ring. |
| 5 | Tooltips fade in place, not from their trigger, and leave on a different path (spatial consistency). `visibility` flipped to hidden instantly, so the exit was a hard cut while the entry faded. | `transform-origin` default, transform `none`, transition `opacity .2s` only. | Fixed: tips grow from the label row (origin at the trigger's side, translateY -4 px and scale .96 to 1) and leave the same way; `visibility` waits 200 ms so the fade out plays. CSS transitions reverse from the current value, so a quick hover in and out is interruptible. Escape closes an open tip (hover, focus or tap) without moving focus, and a tap or click outside closes it; it shows again on the next focus change or once the pointer leaves the label. |
| 6 | No `prefers-contrast: more` support (accessibility). Glass panels are 2 to 6% fills with a 13% edge, so separation is weak for low-vision readers. | 0 rules. | Fixed: near-solid surfaces, 50% edges, muted text #c4bdaa, brighter list text, solid nav, light fields and the chip fade off. |
| 7 | `prefers-reduced-transparency` only covered the nav and hero (materials). Panels, tabs, chips, the chart box, the tip and the gold light fields stayed translucent. | 1 rule, 2 selectors. | Fixed: every glass token goes solid, the nav drops its blur, both light fields are removed. |
| 8 | Tracking and leading not size-specific (type). h2 (26 to 38 px) and h3 (22 to 24 px) had `normal` tracking; h3 inherited body leading 1.55 (37 px lines for 24 px text); large numerals untracked. | h3 line-height 37.2 px. | Fixed: h1 -0.018em (-0.022em at 760+), h2 -0.012em / 1.1, card h2 -0.016em / 1.05, h3 -0.006em / 1.2, big numerals -0.02em, stat numbers -0.01em. Body and mono labels unchanged. |
| 9 | Wayfinding: the active nav item is only a CSS class (no `aria-current`), and a stock page lights no nav item and never says it is a stock page. | `aria-current` null on all links; stock eyebrow "S&P 500 \| Consumer Cyclical". | Fixed: `aria-current="page"` on the active link; the stock eyebrow now starts with "Stock". |
| 10 | Index chip row slices a chip in half at the right edge with no sign there is more (scroll edge). | Row 3111 px wide in a 358 px box at 390. | Fixed: a 44 px mask fade at the right edge plus 40 px end padding so the last chip scrolls clear of it. |
| 11 | The lens tab's gold pill jumps instead of sliding to the new tab, and the lists re-fade on every switch. | | Not fixed: needs the lists redrawn without rebuilding the view; candidate for a later pass. |
| 12 | Stock pages have no in-page way back to the list the reader came from (wayfinding). | | Not fixed: the nav and "Open in lookup" cover it; a back link is a feature change, so it goes to the backlog. |
| 13 | Nav label "Scan" for home is a little generic (direct labels). | | Kept: it names the day's scan, and a longer label breaks the 360 px nav. |

No spring helper was added: nothing on the site is gesture-driven (no drags, sheets or flicks), and every motion
here is either a CSS transition that already reverses from its current value or the funnel counter, which now
starts from its live value.

## Verification

- `python -m pytest -q`: passes.
- Playwright Chromium at 375, 390 and 1280 px, with and without reduced motion, on all six views: 0 console
  errors, 0 px horizontal overflow, CLS 0, no outside requests, "Not investment advice" on every view; home is
  pixel-identical across 600 ms under reduced motion.
- Reduced motion: presses dim to .75 opacity instead of scaling; tooltips fade only.
- Perf: no new assets or requests; about 4 KB of CSS and under 1 KB of JS added. Cache keys bumped to `?v=9`.
