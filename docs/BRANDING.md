# Branding — MCP Light Memory

This document records the visual identity for **MCP Light Memory**.

## Assets

| File | Purpose |
|---|---|
| `docs/assets/logo.svg` | Primary logo (rounded square + memory stack + spark + M mark). 128×128 viewBox. |
| `docs/assets/icon.svg` | Icon-only variant (no M mark, compact). 64×64 viewBox. |

Both assets are hand-written SVG (no external design software, no binary
blobs) and render correctly in GitHub README, social previews, and docs.

## Concept

The logo communicates four ideas at once:

- **Memory** — three stacked layers (a memory stack / bookmark stack).
- **Lightweight** — a small spark/light motif above the stack.
- **MCP / protocol** — four connection nodes on the sides of the stack.
- **M** — a subtle `M` mark integrated below the stack (for *Memory* / *MCP*).

The shape is a rounded square — friendly, modern, app-icon friendly.

## Color palette

| Role | Hex | Notes |
|---|---|---|
| Background | `#0f1620` → `#1b2a3a` (gradient) | Deep charcoal / graphite. |
| Primary accent | `#22d3ee` → `#0ea5b7` (gradient) | Electric cyan / teal. |
| Secondary | `#e2e8f0` | Soft off-white for the M mark. |
| Stroke | `#22d3ee` | Cyan border on the rounded square. |

The palette is restrained and technical. It works on dark and light
backgrounds (the background gradient provides contrast on light themes; the
cyan accent is readable on dark themes).

## Usage notes

- The logo may be displayed at any size; it is recognizable down to 24×24.
- The icon variant drops the M mark and is intended for favicons / small
  avatars / compact list views.
- Do not stretch the logo non-uniformly.
- The logo is monochrome-friendly: replacing the cyan with any single color
  still reads correctly (the stack + spark + nodes carry the concept).
- No mascot, no cartoon style — the identity is intentionally minimal and
  developer-tool-native.

## Social preview

For a GitHub social preview, compose the logo on a `#0f1620` background with
the wordmark `MCP Light Memory` set in a clean sans-serif (e.g. Inter,
SF Pro, Segoe UI) in `#e2e8f0`, with the tagline
`Lightweight local-first persistent memory for coding agents and MCP clients.`
in `#22d3ee`. A ready-to-edit Figma/SVG banner is out of scope for this
rebrand; the logo + wordmark can be composed in any editor.