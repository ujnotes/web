---
name: ujnotes-svg-graphics
description: Create and verify Ujnotes inline SVG explanations and theme-aware SVG covers, including asset registration and raster fallbacks.
---

# Ujnotes SVG graphics

Use editable SVG for diagrams and alphabet or process examples. Ordinary covers follow `site/project/IMAGE_STYLE.md`; explicitly requested explanatory covers can use SVG and meaningful labels.

## Concept and style

- Prefer recognizable objects and explicit operations over abstract decoration. Show or explain every key, control, or object named in the analogy.
- Preserve the real operation and its limits. Verification graphics must distinguish detecting a change from preventing one. Name the actual algorithm when its behavior matters instead of presenting a scheme-specific mechanism as universal.
- Use muted slate outlines and primary text such as `#40516f`, rounded geometry, and restrained accent colours. Preserve user-approved visual details across revisions.
- Keep prose in native Notion blocks; raw rendering callouts contain only markup that requires custom rendering.

## Theme and placement

1. Scope inline SVG CSS and IDs per graphic to prevent collisions. Use `html.dark-mode` for inline page theming and `svg:root` for standalone OS-theme fallback rules.
2. SVGs loaded through `<img>` cannot read the parent page's classes. Define internal palettes with `prefers-color-scheme` and pass the selected site theme through CSS `color-scheme` on the image.
3. SVG covers default to tile size. Add a `hero` role in `config/Image_display.tsv` for a wide explanatory cover. Image lookup prefers SVG when both SVG and JPG exist.
4. Register SVG and required JPG fallback routes in `Config/Url.tsv`. Use canonical flat cover URLs `/{slug}.svg` and `/{slug}.jpg`; follow the publishing skill for index layouts and syncing existing JPG bytes.

## Verify and export

- Inspect the actual article's light and dark toggles and thumbnail view. OS-theme emulation alone does not verify the site's manually selected theme. Check labels, arrow direction, contrast, clipping, and operation order.
- Verify deployed SVG and fallback routes after publication.
- When rasterizing with browser canvas inside an SVG document, use `document.createElementNS('http://www.w3.org/1999/xhtml', 'canvas')`. Plain `createElement('canvas')` there can create an element without `getContext`.
