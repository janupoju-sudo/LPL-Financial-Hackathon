# Otter theme: earth palette, shader backgrounds, peeking otter

Date: 2026-10-03 · Owner: C (Jay) · Status: approved in chat (visual companion)

## Decisions
- Font: **Instrument Sans** everywhere (numbers keep Geist Mono). One font and one ink colour per line.
- Palette **"Otter in the river"**: cream paper, oat, soft water green, fur brown, deep ink.
- Backgrounds: Paper Shaders (`@paper-design/shaders-react`) mesh gradient. Moving on landing, sign-in and
  wizard; still in the app.
- Landing layout modelled on plaid.com: pill nav, big left-aligned headline, one supporting line, two pill
  buttons, quiet trust row, product card on the right.
- Mascot: an SVG otter head in the logo's style peeks over a card (pop up, bob, look around, blink, duck
  down, ~10s loop). Lives on the landing bill card, the sign-in card and the wizard's "You're ready" card.

## Colour roles
| Role | Light | Dark ("otter at night") |
|---|---|---|
| Background | `#f6f1e7` cream paper | `#14110d` river-brown black |
| Text | `#26231c` deep ink | `#f1e8d8` cream |
| Primary buttons, active nav | `#4a3727` fur brown | `#e9dcc6` oat (dark text) |
| Money in, approved | `#3f6656` water green | `#8fbf9f` moss |
| Money out, flags | `#a8503f` clay | `#e39a86` |
| Warnings | `#9a6b1c` ochre | `#e2b766` |

## App changes (no layout changes)
- `globals.css` tokens recoloured for both themes; the blurred "backdrop" blobs are replaced by a still shader.
- "Ask your books" renamed **"Ask Otter"** everywhere; the sidebar's bottom "Ask your books" link is removed
  (the floating Ask button, Home card and command palette remain).
- Settings dialog is centred on screen (Tailwind's reset removed the dialog's `margin: auto`) and gets a
  **Sign out** button at the bottom (also fixes phones, where the sidebar's sign-out link is hidden).

## Components
- `components/shader-bg.tsx`: full-screen MeshGradient; `animated` prop; colours follow light/dark theme;
  still when reduced motion is on or the tab is hidden; CSS gradient fallback when WebGL is missing.
- `components/otter-peek.tsx`: SVG otter + motion loop; clipped so it appears from behind the card's top edge.

## Testing
Typecheck, tests, production build; browser click-through of landing → wizard → sign-in → Home, Money in,
Money out, Documents, Ask Otter, Settings in light and dark, desktop and phone width.
