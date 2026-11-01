---
name: ujnotes-frontend-components
description: Author and maintain frontend-only Ujnotes tools using native Notion prose, declarative component callouts, and separately deployed data.
---

# Frontend components

Keep ordinary prose, metadata and disclosure in the canonical Notion Website row. Keep its translation as a direct child. Embed the interactive portion with a 🧩 callout whose own rich text contains two newline-separated fields:

```text
Component: <registered-name>
Data: /resource/data/<dataset-name>.json
```

Notion enhanced Markdown must put these fields in one rich-text value using `<br />`; separate paragraph children are not configuration. The translator preserves this callout verbatim. Component names must be allowlisted in the NCMS component asset registry. Dataset URLs are restricted to local JSON paths under `/resource/data/`; arbitrary HTML, executable code, external data URLs and traversal paths are rejected.

## Lifecycle and assets

- Site-owned browser code loads registered component scripts and styles lazily, scans on full loads and AJAX content replacement, aborts detached instances and runs their cleanup functions. Keep shared Framework code generic; site components belong in the site repository.
- Return cleanup for pending timers and external resources. Use the supplied AbortSignal for fetches and event listeners. Render imported data with text nodes rather than HTML interpolation.
- Component placeholders carry the explicit content language, so AJAX-loaded translations do not depend on the current document language. Localise controls and error/retry states; share model identifiers and price data across translations.
- Interactive tool placeholders opt out of automatic article-cover injection. The publisher must respect that marker too; existing cover assets may still serve menu tiles without preceding the tool.
- Store runtime assets and data under Resource, and register every fetched public route in the bake URL list. Keep tool data separate from the article AJAX JSON endpoint. Static resource JSON must bypass every article JSON rewrite, including duplicate late catch-alls.
- NCMS derives asset URL rows from component declarations. Single-page publication must merge these rows, retain dependencies in its isolated URL list, and copy and stage all the resulting assets from baked output. Do not patch generated output by hand.

## Price data

- Manually update the dataset, not rendered tables. Preserve schema version and valid JSON. Use one model record with status `current`, `retired` or `to_be_released`.
- Each price needs currency, units, non-negative numeric input/output rates (or null for unknown), an official HTTPS source and a checked date. Zero means explicitly free. Standard and batch rates are separate records.
- Keep source checked dates distinct from effective date intervals. Preserve scheduled rate changes, and record context tiers explicitly. Reject expired rates without a replacement; do not estimate retired or unreleased models.
- Restrict the estimate date to the data snapshot or later when historical validity has not been recorded. A future estimate uses announced prices, not a promise of future model availability.
- Unknown rates, absent batch support and unverified historical prices must not become zero-cost estimates. Treat a user-entered FX rate as an assumption unless separately sourced and dated.

## Review and publication

1. Update English Notion content, then its translation after approval, following the workspace article gates. Preserve the exact disclosure at the end of each body.
2. Generate draft source with NCMS; copy only the reviewed components and matching metadata rows into the live source checkout. Preserve unrelated TSV rows and their column count, including article Type.
3. Verify direct HTML and article JSON, data and asset routes, language metadata, mobile layout, both themes, AJAX detach/remount, error/retry and relevant calculation boundaries. Draft routes need `?full=true`; normal site history can remove that query, so reload with it explicitly during review.
4. Stop before interim/public baking until local-file approval. Introducing shared runtime code also needs the published entry pages' shared script references refreshed during the approved deployment; a new widget can otherwise be absent when entering through an old cached bundle.
5. Keep a tracked copy of this workflow in the publisher project's `.cursor/skills/` directory. Commit each changed source repository; leave production unchanged until publication is authorised.

- Keep display-currency conversion separate from provider rates: convert every displayed price consistently, require a positive user FX rate for non-base currencies, and label it as an assumption. Provider filters may combine selections; sorting must keep unknown values last in either direction. Hide empty optional release sections. For responsive tools inside an automatic grid track, use a zero-minimum flexible track so native controls do not widen the page.

- For automatic FX, use a browser-compatible public daily-reference API, show its source and actual rate date, and retain manual input on service failure. Abort requests on navigation and currency changes; a late response must never overwrite a manual edit. Keep per-model usage-fit suggestions localised and sourced separately from prices, and label them as editorial guidance. Preserve the provider-specific batch discount and whether context thresholds are inclusive. Table rows and chart bars should share calculator selection; hide empty optional status groups after filtering.

- Treat a model offering as a distinct model-and-selling-provider/route record with its own stable ID, rates, conditions and source. Preserve the shared underlying model ID when adding another provider; identify the provider in the calculator and chart so selections cannot collide. Compare chart breakdown bars on a shared scale and label input and output separately.

- Compact pricing tables should retain keyboard-accessible search, sorting, date selection and source provenance. For segmented cost bars, show labelled input/output colours and calculate segment widths as fractions of the total; preserve explicit numeric labels for accessibility. Double-clicking a filter may isolate it without removing ordinary multi-select behavior.

- For an explicitly requested ordinary local preview of a draft, use the existing test status only in the local English and translated ID rows; keep the canonical Notion row draft and keep test rows out of publication scopes. The test status allows local HTML and AJAX routes without the full query flag. Restore or deliberately transition local statuses through the approved publication workflow. Revalidate frontend component assets in local hosting and version their URLs when an older loader or component may already be cached; the first existing browser session may need a hard refresh.

- Interactive comparisons with an optional calculator should not assume a workload when it is disabled. Keep cost-only columns and cost chart metrics hidden until enabled, retain source-rate comparisons, and ensure an inline search stays focused and usable even when no rows match.

- Preserve search and sort control nodes across table rerenders. Header-embedded search must reattach even when no rows match, then restore focus and caret position. Group rates beside model names, keep wide tables in their own scroll regions, and use a full-width model selector above a balanced workload grid instead of leaving an orphan field.

- For pricing charts, scale bars by the exact selected metric without minimum percentage floors; rate views show only the selected rate colour, and workload totals may show input/output shares. Label units with the active display currency. Native disclosure controls should keep secondary filters and retired-model archives available without displacing the main comparison; preserve their open state across rerenders.

- Tabbed tool views should share filter, currency, date and workload state, expose proper tab/tabpanel relationships with roving keyboard focus, and switch to the calculator when a model is selected. Keep view-specific downloads with their table or chart panel.

- When compact table rows move conditions into tooltips, retain an accessible description and keyboard-focus behavior. Render floating notes outside scroll containers so they are not clipped, reposition focused notes on scroll, and allow Escape to dismiss them. Full-height table expansion should remove the vertical height cap while retaining narrow-screen horizontal scrolling, and its state must survive sorting or filtering.

- Icon-only tabs and date controls must keep localized accessible names and tooltips. A custom estimate date should visibly activate its calendar control and provide a reset to the default date. When rearranging article metadata around an interactive tool, move the existing localized content rather than duplicating or rewriting it. Check toolbar grid placement at narrow widths because older first-child spans can override newer field-specific rules.

- For plain range sliders, style WebKit and Firefox tracks and thumbs explicitly to remove native track borders; retain keyboard controls and the outer focus-visible indicator. Use decorative aria-hidden SVGs for workload-preset icons while preserving each button's text label.
