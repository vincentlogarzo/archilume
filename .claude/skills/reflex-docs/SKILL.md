# Reflex Docs Reference

**Trigger:** Use when writing or modifying Reflex UI code — especially under `archilume/apps/archilume_ui/`. Consult before implementing state, components, styling, events, routing, or database patterns.

## Mandatory procedure

1. **Read `llms.txt` first.** `.claude/skills/reflex-docs/reference/llms.txt` — LLM-optimised Reflex overview covering basics, state, components, events, styling, routing.

2. **Search local docs for specifics:**
   ```
   grep -ri "<topic>" .claude/skills/reflex-docs/reference/
   ```
   The `core/` and `components/` directories contain detailed docs on state, styling, routing, forms, layout, overlays, data display, and tables — with props, event triggers, and code examples.

3. **If local docs don't cover it**, use WebFetch to check live docs:
   - Component library: `https://reflex.dev/docs/library/`
   - Any specific component: `https://reflex.dev/docs/library/<category>/<component>`
   - State: `https://reflex.dev/docs/state/overview/`
   - Styling: `https://reflex.dev/docs/styling/overview/`

4. **Follow documented patterns exactly.** Do not invent workarounds when docs provide a solution.

5. **If no match found anywhere**, state that explicitly ("No Reflex docs match for X") before proceeding.

## When to refresh

Refresh if:
- The `reference/` directory is missing or empty
- A Reflex API behaves differently than documented — snapshot may be stale
- The user upgrades the Reflex version

```powershell
powershell -File .claude/skills/reflex-docs/refresh.ps1
```

## Reference directory layout

```
.claude/skills/reflex-docs/reference/
├── llms.txt                        # LLM-optimised overview (start here)
├── core/
│   ├── state.md                    # State, vars, events, helpers
│   ├── styling.md                  # Global/component/inline styles, theming
│   └── routing.md                  # Pages, routes, navigation
├── components/
│   ├── forms.md                    # form, input, select, upload + props
│   ├── layout.md                   # box, flex, grid + props
│   ├── overlay.md                  # dialog, toast + props
│   └── data-display.md             # table, tabs, typography, dynamic rendering
└── reflex-web-docs/                # Tutorials from reflex-web repo
    ├── getting_started/
    └── ai_builder/
```
