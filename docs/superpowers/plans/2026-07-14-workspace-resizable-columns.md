# Workspace Resizable Columns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add drag handles so left and right workspace panels can be resized; defaults scale with viewport on load and do not persist.

**Architecture:** Keep everything in `workspace.html`: CSS variables `--left-w` / `--right-w` drive `grid-template-columns`, two splitter elements sit between panels, and a small inline script sets load-time defaults then handles pointer drag with min-width clamps. No storage and no window-resize recomputation after load.

**Tech Stack:** Existing FastAPI + Jinja + HTMX workspace shell; vanilla JS (inline); pytest + TestClient for markup/CSS hooks.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-14-workspace-resizable-columns-design.md`
- Implementation file: `career_agent/ui/templates/workspace.html` only (no new static assets / libraries)
- No `localStorage` / `sessionStorage`
- Defaults computed once on load from viewport; window resize after load does not recompute until reload
- Defaults: `left = clamp(180, round(vw * 0.20), 360)`, `right = clamp(200, round(vw * 0.24), 420)`, then shrink proportionally if `left + right + 360 + gaps > vw`
- Min: left/right ≥ 180px; center ≥ ~360px during drag
- Splitters: `role="separator"`, `aria-orientation="vertical"`
- Preserve HTMX / panel content behavior

---

## File map

| File | Responsibility |
|------|----------------|
| `career_agent/ui/templates/workspace.html` | Splitter markup, CSS vars/grid/handles, default + drag script |
| `tests/test_ui.py` | Assert splitters, CSS vars, script hooks; no storage APIs |

---

### Task 1: Splitter markup, CSS variables, defaults + drag script

**Files:**
- Modify: `career_agent/ui/templates/workspace.html`
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: existing `.workspace` three-panel shell
- Produces:
  - CSS vars `--left-w`, `--right-w` on `.workspace`
  - Elements `.splitter[data-side="left"]` and `.splitter[data-side="right"]`
  - Inline script defining `computeDefaultWidths(viewportWidth, gaps)` used on load (expose on `window.__workspaceLayout` for testability of the pure formula)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ui.py`:

```python
def test_workspace_has_column_splitters(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    r = client.get("/")
    assert r.status_code == 200
    assert b'class="splitter"' in r.content
    assert b'data-side="left"' in r.content
    assert b'data-side="right"' in r.content
    assert b'role="separator"' in r.content
    assert b'aria-orientation="vertical"' in r.content
    assert b"--left-w" in r.content
    assert b"--right-w" in r.content
    assert b"localStorage" not in r.content
    assert b"sessionStorage" not in r.content


def test_workspace_layout_formula_helper_present(tmp_path, monkeypatch):
    """Shell must expose pure default-width helper for the load-time formula."""
    client, _ = make_client(tmp_path, monkeypatch)
    r = client.get("/")
    assert b"computeDefaultWidths" in r.content
    assert b"__workspaceLayout" in r.content
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `.venv/bin/pytest tests/test_ui.py::test_workspace_has_column_splitters tests/test_ui.py::test_workspace_layout_formula_helper_present -v`  
Expected: FAIL (splitters / helper missing)

- [ ] **Step 3: Update CSS grid to use variables**

In `workspace.html`, change `.workspace` to a 5-track layout (`left | splitter | center | splitter | right`):

```css
.workspace {
  display: grid;
  grid-template-columns:
    var(--left-w, 280px)
    8px
    minmax(360px, 1fr)
    8px
    var(--right-w, 320px);
  column-gap: 4px;
  height: 100vh;
  padding: 12px;
  /* keep any other existing .workspace rules */
}
.splitter {
  width: 100%;
  cursor: col-resize;
  background: transparent;
  border-radius: var(--radius);
  touch-action: none;
  user-select: none;
}
.splitter:hover,
.splitter:focus-visible,
.splitter.is-dragging {
  background: var(--accent-soft);
  outline: none;
}
```

- [ ] **Step 4: Insert splitter markup**

Replace the workspace body block with:

```html
  <div class="workspace" id="workspace">
    <aside id="tree-panel">{% include "partials/tree.html" %}</aside>
    <div
      class="splitter"
      data-side="left"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize experiences panel"
      tabindex="0"
    ></div>
    <main id="center-panel">{% include "partials/center_placeholder.html" %}</main>
    <div
      class="splitter"
      data-side="right"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize assistant panel"
      tabindex="0"
    ></div>
    <aside id="right-panel">{% include "partials/right_notes.html" %}</aside>
  </div>
```

- [ ] **Step 5: Add inline script (defaults + drag)**

Before `</body>`:

```html
<script>
(function () {
  const MIN_SIDE = 180;
  const MIN_CENTER = 360;
  const LEFT_MAX = 360;
  const RIGHT_MAX = 420;

  function computeDefaultWidths(viewportWidth, chrome) {
    // chrome = horizontal padding + splitter tracks + column-gaps outside panels
    const available = Math.max(viewportWidth - chrome, MIN_SIDE * 2 + MIN_CENTER);
    let left = Math.min(LEFT_MAX, Math.max(MIN_SIDE, Math.round(viewportWidth * 0.20)));
    let right = Math.min(RIGHT_MAX, Math.max(200, Math.round(viewportWidth * 0.24)));
    const overflow = left + right + MIN_CENTER - available;
    if (overflow > 0) {
      const total = left + right;
      left = Math.max(MIN_SIDE, Math.round(left - (overflow * left) / total));
      right = Math.max(MIN_SIDE, Math.round(right - (overflow * right) / total));
      while (left + right + MIN_CENTER > available && (left > MIN_SIDE || right > MIN_SIDE)) {
        if (left >= right && left > MIN_SIDE) left -= 1;
        else if (right > MIN_SIDE) right -= 1;
        else break;
      }
    }
    return { left, right };
  }

  window.__workspaceLayout = { computeDefaultWidths, MIN_SIDE, MIN_CENTER };

  const workspace = document.getElementById("workspace");
  if (!workspace) return;

  function measureChrome() {
    const styles = getComputedStyle(workspace);
    const pad =
      (parseFloat(styles.paddingLeft) || 0) + (parseFloat(styles.paddingRight) || 0);
    const gaps = (parseFloat(styles.columnGap) || 0) * 4; // 4 gaps among 5 tracks
    const splitterTracks = 8 + 8;
    return pad + gaps + splitterTracks;
  }

  function applyWidths(left, right) {
    workspace.style.setProperty("--left-w", left + "px");
    workspace.style.setProperty("--right-w", right + "px");
  }

  const defaults = computeDefaultWidths(window.innerWidth, measureChrome());
  applyWidths(defaults.left, defaults.right);

  let active = null; // { side, startX, startLeft, startRight, el }

  function onPointerMove(event) {
    if (!active) return;
    const chrome = measureChrome();
    const maxTotal = window.innerWidth - chrome - MIN_CENTER;
    const dx = event.clientX - active.startX;
    let left = active.startLeft;
    let right = active.startRight;
    if (active.side === "left") {
      left = Math.min(Math.max(MIN_SIDE, active.startLeft + dx), maxTotal - right);
    } else {
      right = Math.min(Math.max(MIN_SIDE, active.startRight - dx), maxTotal - left);
    }
    applyWidths(left, right);
  }

  function onPointerUp(event) {
    if (!active) return;
    active.el.classList.remove("is-dragging");
    active.el.releasePointerCapture?.(event.pointerId);
    active = null;
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
  }

  workspace.querySelectorAll(".splitter").forEach((el) => {
    el.addEventListener("pointerdown", (event) => {
      if (event.button != null && event.button !== 0) return;
      event.preventDefault();
      const left = parseFloat(getComputedStyle(workspace).getPropertyValue("--left-w")) || defaults.left;
      const right = parseFloat(getComputedStyle(workspace).getPropertyValue("--right-w")) || defaults.right;
      active = {
        el,
        side: el.getAttribute("data-side"),
        startX: event.clientX,
        startLeft: left,
        startRight: right,
      };
      el.classList.add("is-dragging");
      el.setPointerCapture?.(event.pointerId);
      window.addEventListener("pointermove", onPointerMove);
      window.addEventListener("pointerup", onPointerUp);
    });
  });
})();
</script>
```

Tune `measureChrome()` if visual spacing drifts — required behavior: load defaults from formula, drag updates vars, no storage, no resize listener that recomputes defaults.

- [ ] **Step 6: Run tests — expect PASS**

Run: `.venv/bin/pytest tests/test_ui.py::test_workspace_has_column_splitters tests/test_ui.py::test_workspace_layout_formula_helper_present -v`  
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add career_agent/ui/templates/workspace.html tests/test_ui.py
git commit -m "$(cat <<'EOF'
feat: add draggable workspace column splitters

Scale left/right defaults from viewport on load and allow pointer drag without persisting widths.
EOF
)"
```

---

### Task 2: Formula unit coverage + regression

**Files:**
- Modify: `tests/test_ui.py`
- Verify: full suite

**Interfaces:**
- Consumes: published formula constants from Task 1
- Produces: Python mirror of the default-width math + assertion that the shell does not attach a `resize` recompute listener

- [ ] **Step 1: Add Python mirror test for the published formula**

```python
def _compute_default_widths(viewport_width: int, chrome: int = 80) -> tuple[int, int]:
    min_side, min_center = 180, 360
    left_max, right_max = 360, 420
    available = max(viewport_width - chrome, min_side * 2 + min_center)
    left = min(left_max, max(min_side, round(viewport_width * 0.20)))
    right = min(right_max, max(200, round(viewport_width * 0.24)))
    overflow = left + right + min_center - available
    if overflow > 0:
        total = left + right
        left = max(min_side, round(left - (overflow * left) / total))
        right = max(min_side, round(right - (overflow * right) / total))
        while left + right + min_center > available and (left > min_side or right > min_side):
            if left >= right and left > min_side:
                left -= 1
            elif right > min_side:
                right -= 1
            else:
                break
    return left, right


def test_default_width_formula_scales_and_clamps():
    wide_l, wide_r = _compute_default_widths(1600)
    narrow_l, narrow_r = _compute_default_widths(900)
    assert wide_l >= narrow_l or wide_r >= narrow_r
    assert 180 <= narrow_l <= 360
    assert 180 <= narrow_r <= 420
    assert narrow_l + narrow_r + 360 <= 900


def test_workspace_script_has_no_window_resize_recompute(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    html = client.get("/").text
    assert "addEventListener(\"resize\"" not in html
    assert "addEventListener('resize'" not in html
```

- [ ] **Step 2: Run focused tests**

Run: `.venv/bin/pytest tests/test_ui.py::test_default_width_formula_scales_and_clamps tests/test_ui.py::test_workspace_script_has_no_window_resize_recompute tests/test_ui.py::test_workspace_has_column_splitters -v`  
Expected: PASS

- [ ] **Step 3: Full suite**

Run: `.venv/bin/pytest -q`  
Expected: PASS

- [ ] **Step 4: Manual smoke**

Run: `career-agent ui --port 8778` (or project equivalent), open browser:

1. Wide vs narrow window → reload each time → different default side widths  
2. Drag left and right splitters → panels resize; center remains usable  
3. Resize window without reload → widths stay at load defaults  
4. Reload → drag state discarded  

- [ ] **Step 5: Commit if Task 2 added tests after Task 1 commit**

```bash
git add tests/test_ui.py
git commit -m "$(cat <<'EOF'
test: cover workspace default width formula and no-resize policy

EOF
)"
```

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| Drag handles left↔center and center↔right | Task 1 |
| CSS vars / grid | Task 1 |
| Load-time viewport defaults + clamps | Task 1 (+ formula test Task 2) |
| No persistence | Task 1 assertion |
| No recompute on window resize after load | Task 2 |
| Min center ~360 / sides ≥180 | Task 1 script |
| `workspace.html` only | Task 1 |
| pytest still green | Task 2 |
