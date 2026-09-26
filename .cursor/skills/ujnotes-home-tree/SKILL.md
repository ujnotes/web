---
name: ujnotes-home-tree
description: >-
  Rules, connector patterns, layout configuration, and build workflow for the
  Ujnotes homepage tile tree and navigation branches. Use when editing Home_menu.php,
  Home.css, Root.js, homepage hierarchy, connectors, or rebuilding the homepage.
---

# Ujnotes homepage tile tree

## Information architecture

- **Homepage root**: Roots at **World** with synthetic children **Philosophy → Science → Technology → Business**. Hub URLs stay `/philosophy`, `/science`, `/technology`, `/business`. The published Notion `root` row's 🏠 JSON callout owns the synthetic order.
- **Meta pages**: Timeline, Changelog, and Roadmap are meta pages (`type: page`), never under World.
- **Canonical hierarchy**:
  - `science` (hub) → `science/physics` (large group) → Electrical, Electromagnetism, Optics, Quantum Physics. Direct children capped as leaves on homepage.
  - `science` (hub) → `science/mathematics` (separate row below Physics) → Axioms, Proof, Multiplication, Zero, Division by Zero.
  - `technology` (hub) → `technology/computer` (large group) → Algorithm, Program, OS, Programming, Game, AI, etc.
  - `technology` (hub) → `technology/electronics` (large group) → Semiconductor, Transistors, Integrated Circuits, Digital Electronics, Microprocessor, etc.
  - `technology` (hub) → `technology/telecommunications`, `technology/radio`, `technology/power_electronics`, `technology/information_technology`.
  - `business` (hub) → 5 fundamental pillars: `business/trade`, `business/money`, `business/debt`, `business/market`, `business/startup`. Pillar children capped as leaves on homepage.

Business pillars with visible child tiles must each occupy a full row. The child subtree can be much wider than a standard 184px pillar node; placing two pillars in one row makes those child tiles overlap neighboring pillars. Keep the full-row rule scoped to direct children of `#home-business-children` in `Home.css`.

---

## Large groups vs. shared rows

When a section inside a hub or tree expands into a multi-column horizontal subtree:
1. **Large groups take the whole space**:
   - Register the slug in the Notion `root` row's 🏠 JSON under `largeGroupSlugs` (e.g. `science/physics`, `technology/computer`, `technology/electronics`), then run NCMS `sync-home`.
   - `home_menu_render_tree()` attaches class `home-menu-large-group`.
   - In CSS, `.home-menu-large-group` sets `flex: 0 0 100%; width: 100%; max-width: 100%`.
   - This gives its child tree unconstrained horizontal width across the full row.
   - Because no sibling shares its row, `homeMenuSharesRowWithSibling` returns `false`, assigning a clean **side leader** toggle next to the section tile (no colliding bottom drops).
2. **Other sections get pushed down together**:
   - Sibling sections without large subtrees (e.g. `science/mathematics`, or `Telecommunications`, `Radio`, etc.) retain standard tile width (`flex: 0 0 var(--home-node-width)` = 184px).
   - Because the preceding large group takes 100% width, these remaining sections wrap down to the next row **together**, sitting side-by-side as a clean row of sibling topic tiles.
   - Mark secondary sections with many child articles as leaves (`leafSlugs`) or cap their direct children (`capChildrenOf`) in the Notion 🏠 policy so they do not spill uncurated subtrees across the shared row.

---

## Connector patterns & layout rules

1. **World hubs**: World roots at World with synthetic children Philosophy → Science → Technology → Business. Hubs use class `home-menu-hub`, stack full-width in `#home-world-children` (column, 24px gaps). Hubs never use bottom connectors.
2. **World leader**: World's vertical spine stays near the left (`#home-world-children` padding-left ~8px). Hub tiles branch off it with short elbows. Each hub offsets its own `--home-glyph-center` / `--home-indent` so the hub's outgoing spine does not sit on World's leader (no stacked double spines).
3. **Side vs bottom leaders**: Use a **side** spine (toggle beside the tile) when children stack vertically under one parent or when a section takes full width. Use a **bottom** leader (drop under the parent tile, then horizontal) only when the parent **shares a horizontal row with another sibling** that also has children (`homeMenuSharesRowWithSibling` — previous or next; first-in-row counts, e.g. Algorithm beside Program).
4. **Bottom-leader glyph**: On a bottom leader, park the expand/collapse glyph **soon after the line start** (under the parent tile / top of the vertical drop), not out at the first child's elbow.
5. **Child row alignment**: When several parents in one row use bottom leaders (Algorithm / Program / OS / …), their first visible children (Binary Search / Illustrator / *Nix / …) must sit on the **same horizontal level**. Same `margin-top` on those subtrees; do not mix side-spine and bottom-leader for siblings on one row.
6. **Toggle near tile**: For side spines, the +/- hit target stays next to its origin tile (glyph center just left of the tile). Do not leave the toggle far out on a long elbow.
7. **Cap / select**: The Notion 🏠 JSON is the source of `config/Home.json`. `leafSlugs` shows nodes without descendants; `capChildrenOf` makes direct children leaves; `selectedChildren` gives an explicit ordered subset (with a `⋮` more-link); and `childLimits` caps otherwise automatic children. The renderer derives every other node from published `Config/ID.tsv`, in its declared order.
8. **Isolation**: Hub subtrees and large group subtrees use `isolation: isolate` so absolute spines do not paint over subsequent sections.
9. **Image credits**: Cover image credits live in the **footer**, never directly under the home tree.
10. **Uniform strokes**: Use an opaque color for ordinary tree connectors in both themes. Translucent strokes brighten where a parent leader and child elbow overlap; keep alternate dashed connectors visually distinct through their dash pattern.
11. **Tile motion**: Connector geometry is measured from tile bounding boxes in `Root.js`. Animate each tile's image and text children, not the tile or its layout ancestors. Reveal only tiles below the initial viewport, and disable motion for `prefers-reduced-motion`.
12. **Homepage portrait**: Its link uses `:focus` to reveal the full image. Keep any idle animation on the unfocused link so the expanded image stays still and usable.
13. **Intro backdrop**: Use a low-contrast image behind the homepage introduction and fade it into the page on the left, right, and bottom so copy and the portrait remain legible. Register new static backdrop assets under `resource/` in the bake URL list.
14. **AJAX parity**: An XURL home load inserts the tree into the current article shell, which may have older inline CSS. Include the current Home styles in the root JSON through the site fragment and `Sync-Home.ps1` composer. Recheck connector geometry on subsequent animation frames after the first pass changes connector classes and wrapping. Compare settled direct and AJAX layouts at the same viewport, including navigation from an older published article.
15. **Browser cache**: Production root JSON may be cached for up to an hour. After a deploy, compare the live JSON bytes with the reviewed artifact, then test AJAX navigation in a fresh browser context. An already-open browser may keep showing its cached older tree until a hard reload or cache expiry.

---

## Files

Article footer navigation uses the published `Config/ID.tsv` hierarchy. When an article has no direct child tiles, `SubList.php` shows an inline SVG fast-forward icon beside the next localized article in depth-first tree order, continuing through ancestor siblings. Keep an accessible link label. Do not use raw TSV adjacency: newly appended descendants can appear after unrelated branches.

- **Markup**: `root/HTML/Component/Root.php` and the Hindi variant are generated from the Notion `root` page; edit the introductory text there.
- **Tree and side menu logic**: `root/Framework/API/Navigation.php`.
- **Tree and side menu policy**: 🏠 and 🧭 JSON code blocks under callouts on the published Notion `root` page. NCMS writes `config/Home.json` and `config/Menu.json` with `sync-home`.
- **Layout CSS**: `root/CSS/Base/Component/Home/Home.css` and `Home_narrow.css`.
- **Connector geometry & toggles**: `root/JS/Page/Root.js`.

---

## Rebuilding the homepage

The homepage slug is `root` and bakes to `public/index.html`. Its source is the published Notion `root` row, with a 📐 `home` layout and separate 🏠 and 🧭 JSON callouts. Run `D:\Ujnotes\Website\project\Sync-Home.ps1` to update local source. It calls NCMS `sync-home` and preserves the Home AJAX style include in both generated language components. Do not use the ordinary article publisher for `root`; it does not stage the two menu policy files.

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
   - Verify the AJAX root JSON contains the same home tree. Deploy it with the HTML and updated script bundle.
5. Remove `Config/Render.lsv` immediately afterwards (never commit `Render.lsv`).
6. An isolated homepage bake can also refresh previously cached pages and language variants. Compare visible content and tile counts against deployed artifacts; carry over only the reviewed homepage output and its referenced script bundle.
7. For production release: copy the reviewed `public/index.html` and its referenced script bundle to `web-public`, commit, and push.
