# Workspace Resizable Columns

Date: 2026-07-14  
Status: Approved for planning (pending final user review of this doc)  
Depends on: Career workspace visual restyle (`2026-07-14-career-workspace-visual-restyle-design.md`)

## Goal

Let users drag vertical dividers to widen or narrow the left (Experiences) and right (Completeness / notes) panels. Defaults scale with window width on load; widths are not persisted across reloads.

## Decisions

| Topic | Choice |
|-------|--------|
| Mechanism | Drag handles + small inline JS in `workspace.html` |
| Persistence | None — reload restores window-based defaults |
| Window resize after load | Do not recompute defaults; only drag changes widths until next reload |
| Dependencies | No new libraries |

## Behavior

- Two vertical splitters: between left↔center and center↔right.
- Drag updates the corresponding side width; center remains `1fr`.
- Clamp: left/right ≥ ~180px; keep center ≥ ~360px (stop drag before collapsing the middle).
- Cursor `col-resize` on handles; subtle hover using existing border/accent tokens.
- Pointer events for resize; keyboard separator support is out of scope for v1.

## Defaults (computed once on load)

```
left  = clamp(180, round(viewportWidth * 0.20), 360)
right = clamp(200, round(viewportWidth * 0.24), 420)
```

If `left + right + centerMin + workspace gaps/padding > viewportWidth`, shrink left and right proportionally until center fits.

Apply via CSS variables on `.workspace`:

```css
grid-template-columns: var(--left-w) 1fr var(--right-w);
```

## Implementation notes

- File: `career_agent/ui/templates/workspace.html` only (markup for splitters + CSS + inline script).
- Splitter elements: `role="separator"`, `aria-orientation="vertical"`.
- On `pointerdown` / `pointermove` / `pointerup` (or equivalent), update `--left-w` or `--right-w` in pixels.
- Preserve existing panel styling, HTMX, and three-panel structure.

## Out of scope

- `localStorage` / `sessionStorage`
- Recomputing defaults on every window `resize` after load
- Collapsing a panel to zero width / hide toggles
- Dedicated keyboard resize UX
- Extracting a separate CSS/JS asset file

## Verification

- Load at narrow and wide viewports; confirm different initial left/right widths and center still usable.
- Drag each splitter; widths change without breaking layout or HTMX exchanges.
- Reload; widths reset to window-based defaults (not the last drag).
- Resize the browser window after load without dragging; widths stay at the load defaults until reload.
- Existing UI pytest suite still passes.
