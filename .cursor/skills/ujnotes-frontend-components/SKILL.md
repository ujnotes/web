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
