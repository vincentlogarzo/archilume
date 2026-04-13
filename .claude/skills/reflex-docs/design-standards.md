# Archilume Reflex UI Design Standards

Target audience: architects and engineers. UI must feel precise and professional.

**If a reference image is provided:** match layout, spacing, typography, and color exactly. Use placeholder content where needed (`https://placehold.co/`). Do not improve or add to the design — just match it.

**If no reference image:** design from scratch using the standards below.

- **Colors**: No default Tailwind palette (indigo-500 etc.). Derive a custom palette. Use radial gradients for depth; SVG noise for texture.
- **Typography**: Never the same font for headings and body. Pair display/serif + clean sans. Headings: tight tracking (`-0.03em`). Body: generous line-height (`1.7`).
- **Shadows & Depth**: Layered, color-tinted shadows (low opacity). Clear z-plane system: base → elevated → floating.
- **Animations**: Only `transform` and `opacity`. Never `transition-all`. Spring-style easing.
- **Interactive States**: Every clickable element needs hover, focus-visible, and active states — no exceptions.
- **Images**: Gradient overlay (`from-black/60`) + `mix-blend-multiply` color treatment layer.
- **Spacing**: Consistent tokens — not arbitrary Tailwind steps.
