---
name: ujnotes-menu-tiles
description: Preserve column alignment and centering in narrow navigation tile groups.
---

# Narrow menu tile alignment

For wrapping navigation tile groups below 540px, center the flex rows and remove left padding. Match tile and filler widths including horizontal margins. Keep invisible filler tiles at zero height, zero padding and zero border so incomplete rows align to the same columns without adding blank vertical space. Remove older narrow rules that give fillers height or hide all but one filler. Scope these rules to ordinary sidebar tile groups; the homepage hierarchy has independent tree geometry.

Shared tile rules belong in the Cutie Framework, with its committed SHA recorded in the site. Preserve unrelated existing edits. Verify one-column and two-column narrow layouts when a browser preview is available.
