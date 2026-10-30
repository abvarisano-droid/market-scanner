# market-scanner

Project instructions for coding agents (Claude Code, Codex, Grok, Cursor).

## Visual and layout work

Before any task that touches visual design or page layout (a page, section, hero,
animation, component styling, or a restyle), read `WEB_DESIGN_REFERENCE.md` in the repo
root and fill out the spec template in its section 6 before writing markup. Run the
anti-slop checklist in section 7 before calling the work done.

Non-negotiables from that file:
- Never ship the first generation. Produce and compare 3 layout alternatives.
- Pin type scale, palette, and easing curve before writing markup.
- Transform/opacity-only animation, plus a reduced-motion fallback and a static fallback
  for every 3D or video-driven section.
- Targets: Lighthouse 95+, CLS 0.00, under 2s on a phone over cell data.
- Fix one thing per prompt: brief, build, screenshot, correct, repeat.
