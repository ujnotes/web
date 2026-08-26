# Agent instructions

Follow the workspace conventions in the parent AGENTS file [`../../AGENTS.md`](../../AGENTS.md) (`H:\AGENTS.md`).

## Git commits

- When a task is completed, show the proposed commit message, then create the commit.
- Do not leave completed work uncommitted unless the user explicitly asks to skip the commit.

## Article cover URLs

- Fetch and list article covers as `/{slug}.jpg` (example: `https://ujnotes.local/world/philosophy/life.jpg?mode=prod`).
- Never use `/{slug}/index.jpg` as the Url.tsv / Tiggu / local preview cover URL.
- Baked `interim`/`public` preview hosts map `/{slug}.jpg` via `.htaccess`; production maps the same canonical URL via `firebase.json` rewrites onto `/{slug}/index.jpg`.
- See parent `AGENTS.md` section “Ujnotes article cover URLs” for the full rule.

## Production deploy trigger

- `ujnotes.com` deploys when `ujnotes/web-public` `main` is pushed (Firebase Hosting GitHub Action).
- That push is manual: local `publish-notion.ps1` / `publish-notion-subtree.ps1`, or the `Publish page from Source` `workflow_dispatch` on `ujnotes/web`.
- Notion database polling (15-minute cron) is parked. Do not restore it. The planned replacement is a URL hook / dashboard trigger.

## Local Notion subtree publishing

- Use `publish-notion-subtree.ps1` for an existing canonical article and its descendant articles. It is the supported path for shared-cover fan-out, one-time canonical queuing, configured-runner batch publication, atomic nested translations, and production cover hash verification.
- Run `-DryRun` when the subtree or source is uncertain. Require the exact supplied source to exist and already contain JPEG data; do not silently substitute or convert a similarly named file.
- Keep single-route builds genuinely isolated by filtering the canonical ID table and every localized `ID_<lang>.tsv` to the selected slug. Rebuilding all localized routes for every selected row is a publisher bug.
- Use canonical `/{slug}.json`, `/<lang>/{slug}.json`, and `/{slug}.jpg` verification URLs, with explicit UTF-8 decoding for localized content. Do not verify through deployment-only `/index.*` paths.
- Invoke as `& .\publish-notion-subtree.ps1 -RootSlug <slug>` from this directory. Do not wrap in `powershell.exe -File`; that breaks the embedded Python `-c` snippets.
- An isolated child publish does not rebuild parent listing HTML. Republish the listing slug to refresh child tiles (placeholder.svg on `/computer/game` while `/computer/game/doom` is already correct).
- Covers already on disk: omit `-CoverSource`.
- Set `[Console]::OutputEncoding` / `$OutputEncoding` to UTF-8 no BOM and `$env:PYTHONUTF8=1` before capturing NCMS Python. OEM CP437 turns Hindi into mojibake and fails the built-JSON description check. `NCMS_RESULT` must use `ensure_ascii=True`; read generated JSON/PHP with `Read-Utf8Text`.
- Homepage is slug `root` and bakes to `public/index.html`. It is not a Notion-queued article. Do not run `publish-notion.ps1 -Slug root` (that overwrites `Root.php` tree markup). Isolated child publishes do not rebuild homepage tiles.
- Rebuild the homepage with Tiggu: write a temporary `Config/Render.lsv` containing only `root`, delete stale `public/index.html` first (Tiggu `check()` ignores Resource/Url.tsv cover changes), run Tiggu through the renderer selected by `H:\Website\console\config.yaml` (prefer `runner: native`), copy `public/index.html` into `web-public`, commit, and push. Delete `Render.lsv` afterwards. Do not commit it.
- Never edit `web-public` / GitHub raw HTML by hand (no search-replace on `build/public/*.html`). Production files are minify output. Always render into `interim`, let Tiggu minify into `public`, then publish that. If a tile or script src is wrong, fix source or rerun Tiggu, then publish.


