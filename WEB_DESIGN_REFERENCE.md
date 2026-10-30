# WEB_DESIGN_REFERENCE.md

**Purpose:** Design reference for any visual or layout work on any website in this project.
**Read this before** building, editing, or restyling a page, section, hero, animation, or layout.
**Source:** Research dissection of AI/web-design creators and tools, Oct 2026.

---

## 0. How to use this file

Agents (Claude Code, Codex, Grok, Cursor): when a task touches visual design or page layout,
load this file first. Do not generate a "premium" look from adjectives. Convert taste into a
spec (section 6), then build.

Hard rules:
- Never accept the first generation. Ask for 3 layout alternatives.
- Pin type scale, palette, and easing curve BEFORE writing markup.
- Transform/opacity-only animation. Static fallback for every cinematic section.
- Perf target: Lighthouse 95+, 0.00 CLS, under 2s on a phone over cell data.
- Fix one thing per prompt. Brief, build, screenshot, correct, repeat.

---

## 1. The ten cross-cutting patterns

1. **Scroll is the main interaction.** Stories, chapters, cameras, and product teardowns are
   driven by scroll position: pinned sections, frame scrubbing, scroll-apart 3D.
2. **One signature moment per site.** A camera fly-through, a sneaker that pulls apart into
   labelled parts, a villa that constructs itself. Everything else is restrained.
3. **Slow, cinematic motion.** Fades, reveals, expansions. Never fast or jittery. Luxury is slow,
   and restraint reads as confidence in any category.
4. **Minimal premium typography plus ruthless hierarchy.** Big type, few words, clear eyebrow
   labels, deliberate whitespace.
5. **Performance discipline.** Speed is a design feature and a conversion factor, not a cleanup
   task at the end.
6. **AI directs, human art-directs.** Brief, AI builds, screenshot, fix one thing, repeat. AI
   rarely gets it right the first time.
7. **Mobile-first, not mobile-adapted.** Full-screen menus, lighter media, touch where laptops
   have hover.
8. **Design is priced, not just admired.** Tie the aesthetic to conversion.
9. **The demo is the marketing.** Show the thing moving before anyone reads a word.
10. **Source ships clean.** README plus CLAUDE.md / AGENTS.md so any agent can rebuild it.

Plus, from round 2:
11. **Taste is a spec, not a vibe.** "Make it premium" fails. "Serif display, 64/50/40px,
    -0.02em tracking, 800ms ease-out reveals" works.
12. **Builders make the thing; raw material feeds them.** Pipeline: reference, spec, component,
    builder.
13. **Exploration and building are two separate steps.** Generate directions first, hand ONE to
    the coding agent. Never one-shot a finished site.
14. **One participatory moment at the door.** An interactive invitation early, then restrained
    scrolling after.

---

## 2. The default premium recipe

The formula most of the high-end creators converge on:

- Cinematic fullscreen hero section plus smooth scroll
- Layered visuals plus parallax for depth
- Minimal premium typography
- GSAP + ScrollTrigger + Lenis
- Fades, reveals, and image expansion on scroll
- Subtle hover and cursor interactions
- Motion kept slow and smooth

Typical stack: Next.js + React + GSAP, or a single-file HTML build for small sites.

Architecture pattern worth copying: one fixed transparent WebGL canvas layered between section
backgrounds and copy, with 3D "acts" anchored to DOM elements via `data-stage`; pinned stages
using `position: sticky`; the render loop running on the GSAP ticker so Lenis, ScrollTrigger,
and 3D all share one clock.

---

## 3. Method notes from specific builds

- **Scroll-driven film tour:** generate ~200 frames with an AI video tool, build a scroll engine
  that turns frames into a cinematic tour, use GSAP to reveal details as you move through.
- **Layered 3D:** split one 3D object into separate pieces around a central anchor in Three.js so
  each part rotates, drifts, and reconnects independently. Feels engineered, not just spinning.
  Add depth-based pointer interaction so foreground reacts differently than background.
- **Procedural 3D:** build models in code rather than downloading stock.
- **Design-first selling:** build the prospect's actual future site as a working concept before
  any money changes hands.
- **Interactive calculator:** an ROI/cost calculator built on the prospect's own numbers.
- **Content-first building:** scrape or gather the real data and content first, then generate the
  site around it.
- **AI-search optimization:** structure content so ChatGPT and Google's AI answers can read and
  cite it. Local SEO means service-area pages plus a Google Business Profile.

---

## 4. Raw material (feed these to the builder)

| Resource | What it gives you |
|---|---|
| Refero Styles (styles.refero.design) | Design systems of 2,000+ real sites as structured DESIGN.md files: color tokens, type scales, spacing, explicit do/don'ts |
| 21st.dev | 5,000+ React/Tailwind components, live previews, "Copy Prompt" button that packages code plus install instructions |
| Aceternity UI | 200+ animated components modeled on award sites, transform/opacity-only discipline |
| MotionSites (motionsites.org/free) | 8,176 free prompt entries in a category taxonomy |
| Creatsly | Design references shipping with prompts, ZIPs, and an MCP hookup |
| transitions.dev | Copy-paste transitions for web apps |
| smallbits.design | 200+ pixelated icons on a strict 8x8 grid, free commercially |
| Scrolltide | 132 named design directions, each a detailed prompt plus full source |
| Sketchfab | Stock 3D models, fine when the motion design is yours |

**The single most transferable skill: extract, don't imitate.** Reverse-engineer any site you
admire into a DESIGN.md spec, then hand the spec to the agent.

---

## 5. Builders and tools

- **Lovable** / **YouWare** / **blink.new** - chat-to-site, full-stack (db, auth, payments, hosting)
- **Kombai** - "AI design engineer" with a taste agent and repo-aware context; reuses your own
  components, tokens, hooks
- **Diffui** - generates 8 parallel design directions in ~80s, learns a brand from screenshots,
  hands the winner to a coding agent
- **Spline** - browser 3D, agent-native via MCP; agents can read, write, and frame 3D scenes
- **v0 by Vercel**, **Google Stitch**, **Replit** - alternates worth comparing on taste

**Evaluate any builder on four axes:** code ownership/export, model flexibility, output taste,
community gallery. Builders are interchangeable commodities; the gallery and export terms are not.

**Open-source recreation stack for award-level sites:** r3f-scroll-rig, CurtainsJS, Barba, OGL,
Postprocessing, Aniso, Three.js, GSAP, gsap-skills, Lenis. If you can name the stack, you can
prompt or build each part separately.

---

## 6. The spec template (fill this before building)

```
SITE: 
ONE SIGNATURE MOMENT: 
WEBSITE MAP (pages, section order per page): 

TYPE
  display: [family] / [weights]
  scale: __ / __ / __ / __ px
  tracking: 
  body: [family] / size / line-height
PALETTE
  bg / surface / text / muted / accent (hex tokens)
SPACING
  base unit, section padding, max content width
RADII / BORDERS / SHADOWS
MOTION
  easing curve: 
  durations: reveal __ms, hover __ms, page transition __ms
  distances: 
  properties: transform + opacity only
  reduced-motion fallback: 
SCROLL SYSTEM
  smooth scroll: Lenis y/n
  pinned sections: 
  triggers: 
MEDIA
  formats, compression targets, static fallback for each cinematic section
PERF TARGETS
  Lighthouse perf 95+, a11y 95+, CLS 0.00, LCP under 2s on 4G
```

---

## 7. Anti-slop checklist

Run this before calling a visual build done:

- [ ] Does the page have exactly one signature moment, with everything else restrained?
- [ ] Were 3 layout alternatives generated and compared, not just the first output?
- [ ] Is the type scale explicit and consistent, not per-section guesswork?
- [ ] Is motion specified in numbers (duration, easing, distance), not adjectives?
- [ ] Transform/opacity only? No animating layout properties?
- [ ] Is there a reduced-motion fallback?
- [ ] Is there a static fallback for every 3D or video-driven section?
- [ ] Designed mobile-first, with touch equivalents for every hover?
- [ ] Lighthouse 95+, CLS 0.00, under 2s on a phone over cell data?
- [ ] Does it look like a specific decision, or like default AI output?

---

## 8. Glossary

**Hero section** - full-screen opening block, headline plus visual.
**Scroll-driven storytelling** - the page's narrative advances as you scroll.
**Pinned stages** - sections locked in view while scroll drives animation inside them.
**Parallax** - background and foreground moving at different speeds for depth.
**Frame scrubbing** - scroll position controls which frame of an animation displays.
**GSAP** - the standard JS animation library. **ScrollTrigger** - its scroll-position plugin.
**Lenis** - smooth-scroll library with inertia feel.
**Three.js / WebGL** - 3D in the browser; WebGL is the API, Three.js the library.
**Layered 3D scenes** - one model split into independently animated pieces.
**Depth-based pointer interaction** - input mapped by 3D depth.
**Micro-interactions** - small hover, pulse, and reveal details that read as premium.
**Visual hierarchy** - size, weight, and spacing guiding the eye.
**Whitespace** - empty space used deliberately; a hallmark of premium design.
**Lighthouse / PageSpeed** - Google's perf, a11y, and best-practices test.
**CLS (layout shift)** - content jumping as it loads; 0.00 is the target.
**AI-search optimization** - structuring content so AI answers can read and cite it.
**Headless CMS** - content management without a bundled front end (e.g. Sanity).
**Static site** - prebuilt pages, no server rendering; fast and cheap to host.
**Netlify / Vercel** - hosting for modern sites. **Supabase** - Postgres backend for forms/data.
**CLAUDE.md / AGENTS.md** - markdown files instructing a coding agent on project rules.
**Vibe coding** - describing what you want and letting AI write the code.
**Prompt engineering** - structured AI instructions; the loop is ask, look, correct, repeat.
**Blender** - free 3D software for custom web visuals.
**Procedural 3D** - models built in code, not downloaded.
**Motion swap** - swapping animation styles onto existing visuals.
**Design system** - defined fonts, colors, spacing, components reused across a site.
**AI slop** - the generic, samey look of AI-generated design. The thing to beat.
**Taste agent** - an AI layer whose job is design decisions, not code.
**DESIGN.md / design tokens** - a markdown spec of a design system an agent can build from.
**Easing curve** - the acceleration profile of a motion; the single biggest lever in whether
animation feels premium or cheap.
**Reduced-motion fallback** - a calmer version for users who prefer less motion.
**Transform/opacity-only animation** - animating only GPU-cheap properties.
**MCP (Model Context Protocol)** - the standard letting agents talk to tools.
**Pixel transition** - blocky, pixelated scene wipes.
**Website map** - page-by-page information architecture, drawn before any design.
**Motion as numbers** - specifying motion with exact values instead of adjectives.
**Fallback layers** - a lighter version that loads when the fancy version cannot.

---

## 9. Skills ladder

**No-code:** prompt engineering with screenshot-feedback loops; AI image/video generation for
site visuals; design taste (hierarchy, whitespace, typography); a repeatable build system;
selling via free concept builds and transparent packaging.

**Front-end (core craft):** HTML/CSS/JS, responsive and mobile-first; GSAP + ScrollTrigger +
Lenis; React/Next.js (or Astro/Svelte) plus Tailwind; typography and design systems; SEO
fundamentals plus local and AI-search structure; performance optimization; Git to Vercel or
Netlify on your own domain; the agentic workflow (coding agent in the folder, CLAUDE.md rules,
connectors).

**Advanced:** Three.js/WebGL layered scenes, camera fly-throughs, procedural models; Blender
assets; canvas frame scrubbing and particle systems; Supabase/Postgres and headless CMS;
building your own agents, skills, and prompt packs as products.

---

## 10. Reference sites worth studying

- **Son Daven** - Awwwards Site of the Month, Jun 2026. Restrained light, film grain, one big
  serif, slow pacing, pixel transitions. Proof that slowness is a design material and that a site
  can carry with zero 3D.
- **Why Zero** - you draw a zero, break the glass, land in an explorable 3D city. The
  participatory-moment-at-the-door pattern.
- **Chande Bootcamp 2026** - interactive design magazine: huge type, neon green, WebGL on scroll.
  Editorial rules transferred to the web, one idea per spread, type as the image.
