---
name: ujnotes-home-tree
description: >-
  Rules, connector patterns, layout configuration, and build workflow for the
  Ujnotes homepage tile tree and navigation branches. Use when editing Home_menu.php,
  Home.css, Root.js, homepage hierarchy, connectors, or rebuilding the homepage.
---

# Ujnotes homepage tile tree

## Information architecture

- **Homepage root**: Roots at **World** with synthetic children **Philosophy → Science → Technology** (`home_menu_branch_children`). Hub URLs stay `/philosophy`, `/science`, `/technology`.
- **Meta pages**: Timeline, Changelog, and Roadmap are meta pages (`type: page`), never under World.
- **Canonical hierarchy**:
  - `technology` (hub) → `technology/computer` (Computer article & computing tree) → Algorithm, Program, OS, Programming, Game, AI, etc.
  - `technology` (hub) → `technology/electronics` (Electronics article) → Semiconductor, Transistors, Integrated Circuits, Digital Electronics, Microprocessor, etc.
  - `technology` (hub) → `technology/telecommunications`, `technology/radio`, `technology/power_electronics`, `technology/information_technology`.

---

## Large groups vs. shared rows

When a section inside a hub or tree expands into a multi-column horizontal subtree:
1. **Large groups take the whole space**:
   - Register the slug in `home_menu_large_group_slugs()` in `Home_menu.php` (e.g. `technology/computer`, `technology/electronics`).
   - `home_menu_render_tree()` attaches class `home-menu-large-group`.
   - In CSS, `.home-menu-large-group` sets `flex: 0 0 100%; width: 100%; max-width: 100%`.
   - This gives its child tree unconstrained horizontal width across the full row.
   - Because no sibling shares its row, `homeMenuSharesRowWithSibling` returns `false`, assigning a clean **side leader** toggle next to the section tile (no colliding bottom drops).
2. **Other sections get pushed down together**:
   - Sibling sections without large subtrees (e.g. `Telecommunications`, `Radio`, `Power Electronics`, `Information Technology`) retain standard tile width (`flex: 0 0 var(--home-node-width)` = 184px).
   - Because the preceding large group takes 100% width, these remaining sections wrap down to the next row **together**, sitting side-by-side as a clean row of sibling topic tiles.
   - Mark secondary sections with many child articles as leaves on the homepage (`home_menu_leaf_slugs()`) so they do not spill uncurated subtrees across the shared row.

---

## Connector patterns & layout rules

1. **World hubs**: World roots at World with synthetic children Philosophy → Science → Technology. Hubs use class `home-menu-hub`, stack full-width in `#home-world-children` (column, 24px gaps). Hubs never use bottom connectors.
2. **World leader**: World's vertical spine stays near the left (`#home-world-children` padding-left ~8px). Hub tiles branch off it with short elbows. Each hub offsets its own `--home-glyph-center` / `--home-indent` so the hub's outgoing spine does not sit on World's leader (no stacked double spines).
3. **Side vs bottom leaders**: Use a **side** spine (toggle beside the tile) when children stack vertically under one parent or when a section takes full width. Use a **bottom** leader (drop under the parent tile, then horizontal) only when the parent **shares a horizontal row with another sibling** that also has children (`homeMenuSharesRowWithSibling` — previous or next; first-in-row counts, e.g. Algorithm beside Program).
4. **Bottom-leader glyph**: On a bottom leader, park the expand/collapse glyph **soon after the line start** (under the parent tile / top of the vertical drop), not out at the first child's elbow.
5. **Child row alignment**: When several parents in one row use bottom leaders (Algorithm / Program / OS / …), their first visible children (Binary Search / Illustrator / *Nix / …) must sit on the **same horizontal level**. Same `margin-top` on those subtrees; do not mix side-spine and bottom-leader for siblings on one row.
6. **Toggle near tile**: For side spines, the +/- hit target stays next to its origin tile (glyph center just left of the tile). Do not leave the toggle far out on a long elbow.
7. **Cap / select**:
   - `home_menu_leaf_slugs()`: shows these nodes on the homepage but does not expand their descendants.
   - `home_menu_cap_children_of()`: direct children of these nodes are shown as leaves (no deeper expansion on the homepage).
   - `home_menu_selected_child_slugs()`: parent slug => list of child slugs to show in explicit order. Unselected siblings are omitted and a vertical `⋮` more-link is rendered on the last tile.
   - `home_menu_selected_child_limit()`: parent slug => maximum count of children to show when no explicit selected-child list is configured.
8. **Isolation**: Hub subtrees and large group subtrees use `isolation: isolate` so absolute spines do not paint over subsequent sections.
9. **Image credits**: Cover image credits live in the **footer**, never directly under the home tree.

---

## Files

- **Markup**: `root/HTML/Component/Root.php` (renders branch `'world'`).
- **Tree logic & curation**: `root/HTML/Fragment/Home_menu.php`.
- **Layout CSS**: `root/CSS/Base/Component/Home/Home.css` and `Home_narrow.css`.
- **Connector geometry & toggles**: `root/JS/Page/Root.js`.

---

## Rebuilding the homepage

The homepage slug is `root` and bakes to `public/index.html`. It is **not** a Notion-queued article. Never run `publish-notion.ps1 -Slug root` (that would overwrite `Root.php` tree markup).

### Build steps:
1. Write a temporary `Config/Render.lsv` in `Website/site/project`:
   ```tsv
   root
   ```
2. Delete stale `public/index.html` (Tiggu's `check()` may skip rebuilding if source files haven't changed timestamp).
3. Run native Tiggu via `PublishRunner.ps1`:
   ```powershell
   Import-Module D:\Ujnotes\Website\project\PublishRunner.ps1
   Invoke-UjnotesNativeTiggu -ProjectPath "D:\Ujnotes\Website\site\project" -WebsiteRoot "D:\Ujnotes\Website"
   ```
4. Verify `public/index.html`:
   - Inspect DOM structure and ensure no overlapping nodes.
   - Verify tiles and more-links (`home-menu-more`).
5. Remove `Config/Render.lsv` immediately afterwards (never commit `Render.lsv`).
6. For production release: copy `public/index.html` to `web-public/index.html`, commit, and push.
