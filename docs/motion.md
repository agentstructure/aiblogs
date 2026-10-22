# Motion

How the four blogs move, following the website route ("가치 → 작동 방식 → 증거 → 행동") of
[awesome-ai-motion](https://github.com/gongnyang/awesome-ai-motion) (MIT), which builds on
IBM Carbon's motion tokens and WCAG 2.2. These are reading sites, so there is very little
motion: hover feedback, a reading bar on posts, and a switch to turn it all off.

## Principles

1. Static first. Every page is complete with no JavaScript, with reduced motion, and with
   animations paused. Headlines and the subscribe form are readable and usable on first render.
2. One job per effect: draw attention, show a relationship, show a change, or confirm an input.
   If an effect only makes things "look cool", leave it out.
3. One main action per page (reading, then subscribing), with one or two supporting ones.
4. Move with `transform` and `opacity`, not layout properties.

## Tokens (`static/style.css`, `:root`)

| Token | Value | Use |
| :--- | :--- | :--- |
| `--dur-fast` | 110ms | small fades |
| `--dur-feedback` | 150ms | button and link hover/press feedback |
| `--dur-reveal` | 280ms | section and card reveals |
| `--dur-emphasis` | 400ms | one emphasis moment per page |
| `--ease-standard` | `cubic-bezier(0.2, 0, 0.38, 0.9)` | state changes |
| `--ease-entrance` | `cubic-bezier(0, 0, 0.38, 0.9)` | things arriving |
| `--ease-expressive` | `cubic-bezier(0.4, 0.14, 0.3, 1)` | the single emphasis moment |
| `--reveal-rise` | 16px | reveal travel distance |

Staggers, if ever added: 20-60ms per item, whole group under 500ms. Use `linear` only for
scroll-linked progress.

## What moves today

- Links, post-list titles and the subscribe button: colour/opacity feedback at
  `--dur-feedback` with `--ease-standard`.
- Post pages (`templates/post.html`): a scroll-linked reading bar (`.read-progress`), CSS only,
  shown only where `animation-timeline: scroll()` is supported and
  `prefers-reduced-motion` is `no-preference`; elsewhere it is absent.

## Pause animations

The footer in `templates/base.html` (shared by every page of every blog) has a
**Pause animations** button (`.motion-toggle`, `aria-pressed`). It sets
`<html data-motion="off">` and stores `motion=off` in `localStorage` (wrapped in try/catch).
A tiny inline script in `<head>` applies the stored choice before the stylesheet loads, so
there is no flash of motion. The button is `hidden` in the HTML and only shown once the
footer script runs, so it never appears without JavaScript. Clicking it fires
`site-motion-change` on `window` for any future script that animates.
The `:root[data-motion="off"]` rule in `static/style.css` stops all animations, makes
transitions instant and hides the reading bar. This covers WCAG 2.2.2 (Pause, Stop, Hide).

## Rules

- No infinite pulse or floating on calls to action. Decorative loops beside reading content
  settle after a few cycles.
- No bounce or overshoot on numbers, bars or anything that carries a value.
- No scroll hijacking, forced snapping or long pinned sections.
- A reveal never hides content without JavaScript or with reduced motion.
- Emails (`templates/email.html`) and feeds are out of scope: no motion there.

## Checklist for a new animation

1. What does it do: attention, relationship, change or feedback?
2. Does the page still make sense with it removed?
3. Duration and distance inside the token ranges above?
4. Gated by `prefers-reduced-motion` and stopped by `data-motion="off"`?
5. Checked with reduced motion on, with Pause animations on, and on a phone?
