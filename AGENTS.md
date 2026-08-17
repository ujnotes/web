# Agent instructions

Follow the workspace conventions in the parent AGENTS file [`../../AGENTS.md`](../../AGENTS.md) (`H:\AGENTS.md`).

## Git commits

- When a task is completed, show the proposed commit message, then create the commit.
- Do not leave completed work uncommitted unless the user explicitly asks to skip the commit.

## Article cover URLs

- Fetch and list article covers as `/{slug}.jpg` (example: `https://ujnotes.local/world/philosophy/life.jpg?mode=prod`).
- Never use `/{slug}/index.jpg` as the Url.tsv / Tiggu / local preview cover URL.
- See parent `AGENTS.md` section “Ujnotes article cover URLs” for the full rule.

## Local Notion subtree publishing

- Use `publish-notion-subtree.ps1` for an existing canonical article and its descendant articles. It is the supported path for shared-cover fan-out, one-time canonical queuing, warm-container batch publication, atomic nested translations, and production cover hash verification.
- Run `-DryRun` when the subtree or source is uncertain. Require the exact supplied source to exist and already contain JPEG data; do not silently substitute or convert a similarly named file.
- Keep single-route builds genuinely isolated by filtering the canonical ID table and every localized `ID_<lang>.tsv` to the selected slug. Rebuilding all localized routes for every selected row is a publisher bug.
- Use canonical `/{slug}.json`, `/<lang>/{slug}.json`, and `/{slug}.jpg` verification URLs, with explicit UTF-8 decoding for localized content. Do not verify through deployment-only `/index.*` paths.
