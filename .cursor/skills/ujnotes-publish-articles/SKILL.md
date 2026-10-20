---
name: ujnotes-publish-articles
description: >-
  Publishes Ujnotes Notion articles through publish-notion.ps1 /
  publish-notion-subtree.ps1, including HTML, AJAX JSON, covers, inline
  assets, parent listing tiles, UTF-8, and production verification. Use when
  publishing, republishing, deploying ujnotes.com, or queuing Notion Status.
---

# Publish Ujnotes articles

- When authoring a nested translation through Notion enhanced Markdown, put all 🌐 metadata fields in the callout's own rich text, separated with `<br>` (or actual rich-text newlines). Separate paragraphs become child blocks and are not read by NCMS's metadata parser. Verify with a `publish --status draft` review bundle before queuing. When merging TSV rows for local review, preserve unrelated lines verbatim rather than reserializing the whole table through a CSV writer.

For a **new** article, do not start here. Follow `D:\Ujnotes\AGENTS.md` **New article sequence**: Notion English, then approved translations, then local files, then approved interim/public bake, then this publish-to-web step.

---

## Native runner & console

- **Dockerless by default**: Publish Ujnotes with the native runner (`PublishRunner.ps1`). Do not start Docker Desktop or Docker Compose unless the user explicitly requests Docker.
- **Console trigger**: Start user-requested publications through `https://console.ujnotes.local/` whenever it is available, allowing progress tracking.
- **Native tool pinning**: Tooling dependencies are managed via `D:\Ujnotes\Website\project\Install-NativePublishTools.ps1` (Git Bash, PHP, Python, Java, minify, Closure Compiler).

---

## Command

From `D:\Ujnotes\Website\project` (do not wrap in `powershell.exe -File`):

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
& .\publish-notion-subtree.ps1 -RootSlug <slug>
```

- **Subtree**: Covers already on disk: omit `-CoverSource`. Use `-DryRun` first when the subtree is uncertain.
- **Single article (no descendants)**: Queue that canonical Notion row to `Status = publish`, then:
  ```powershell
  & .\publish-notion.ps1 -Slug <slug>
  ```
- **NCMS tree**: Default `-NcmsProject` is `D:\Ujnotes\Website\ncms`. Console passes that switch. Website NCMS must keep `resolve_publish_pages` and `wrap_leading_date`, or slug-targeted publishes fail.
- **Windows UTF-8 encoding**: Console encoding defaults to OEM CP437. Always set UTF-8 (no BOM), `$env:PYTHONUTF8=1`, and `$env:PYTHONIOENCODING=utf-8` before running NCMS Python. Dump `NCMS_RESULT` with `ensure_ascii=True`.

---

## Build, pipeline & runtime safeguards

1. **Cover & URL rules**:
   - Every row in `Config/Url.tsv` and `Url_<lang>.tsv` must return HTTP 200 on `ujnotes.local`. If any row 404s, Tiggu's `download()` sets `Halt=TRUE` and fails the bake.
   - Canonical covers are requested as flat `/{slug}.jpg`, while baked Firebase may store them as `/{slug}/index.jpg`. Staging must preserve the index layout and maintain the canonical rewrite.
   - NCMS should add a JPG URL row only when the article has an explicit 🖼️ cover callout, using the flat slug path/name rather than an `index.jpg` request. Coverless pages must not create an unfetchable URL row.
   - An article may intentionally have no cover asset. `Component_cover.php` must return without output when `getComponentImage` is null; never expose a missing-cover diagnostic in rendered HTML or JSON.
   - After local cover edits, run `project/Sync-PublishedImages.ps1` to compare every already-published `Url.tsv` JPG route with `root/Resource`. Use `-Apply` to update stale files in the `web-public` checkout, then commit and push that checkout. Firebase serves an existing flat JPG before a rewrite, so when flat and index artifacts both exist, both must match the local source. A URL row alone does not refresh deployed image bytes.
2. **AJAX JSON parity & shadowing flats**:
   - XURL navigation loads `/{slug}.json`, not the HTML file. Both `index.html` and `index.json` must deploy atomically.
   - Isolated Tiggu may emit flat `public/{slug}.html` and `.json`. The publisher must install `{slug}/index.*` and delete shadowing flats via `Resolve-StagedPageArtifacts` and `Remove-ShadowingFlatArtifacts`.
   - Firebase Hosting rewrites must include every translation variant: `/{lang}/{slug}.json -> /{lang}/{slug}/index.json`. Without these rewrites, live JSON verification loops fail with HTTP 404 for localized variants.
3. **Missing inline assets**:
   - `Framework/HTML/Fragment/Component_image.php` must not call `getimagesize` on a missing file (prevents PHP 8.4 fatal errors that leak HTML into `/{slug}.json`). It falls back to `/resource/placeholder.svg`.
4. **Breadcrumbs & up-nav**:
   - Breadcrumb (`getComponentPathStylized`) and up-nav (`getNearestExistingParentId`) must skip ID rows that do not exist yet, preventing intermediate 404s on nested slugs.
5. **Timeline dates**:
   - Wrap leading `dd Mon yyyy —` in `<span class='date'>…</span> —`. NCMS overwrite drops these spans unless `publish-notion.ps1` runs `Protect-TimelineDates.py` immediately after copying each variant PHP (idempotent).
6. **Metadata & schema integrity**:
   - `Merge-IdRow` must preserve an existing `Config/ID.tsv` Type (`page` for Timeline, Changelog, Roadmap; `article` for standard content).
   - Single-article publish (`publish-notion.ps1`) automatically synchronizes localized variants: merges rendered `Config/ID_<lang>.tsv` into the site's `ID_<lang>.tsv` and rendered `Config/Translations.tsv` into `Translations.tsv` during `update-source`, and updates their status to `published` in `mark-published`.
   - Localized `Config/ID_<lang>.tsv` descriptions must match Notion translation metadata exactly.
   - `Config/Translations.tsv` component slugs must reflect current canonical paths, avoiding legacy redirected paths.
   - Exclude `/manifest.json` from the `.json` rewrite in `Root/.htaccess`.
7. **Queued links guard**:
   - The queued-link guard is a substring match on baked JSON. If the match is site chrome (e.g. navigation) rather than an unpublished body dependency, resume with `-AllowQueuedLinks`.
8. **Checkpoints**:
   - If network or renderer access fails midway, resume the same checkpoint (`-Resume`); never refetch or mark published before verification succeeds.
9. **Tiggu cache busting**:
   - Use the native Python script-reference rewriter on Windows. A single GNU `sed` pass over the baked tree can stall for minutes.
   - Do not request a newly versioned production script URL before Firebase finishes deploying it. Firebase can cache a pre-deploy 404 for hours; verify the workflow first, then fetch the new URL.
10. **Firebase Hosting storage quota**:
   - After pushing `web-public`, confirm the Firebase GitHub workflow succeeded before treating the site as deployed. A push can fail with HTTP 429 `RESOURCE_EXHAUSTED` when retained Hosting releases fill project storage.
   - Inspect the live channel's `retainedReleaseCount`. An unlimited setting can accumulate old versions. Set a bounded release retention in Firebase Hosting only after the owner approves deleting older release history; then rerun the failed deploy and verify live bytes.
   - A Cloud Resource Manager API 403 during Firebase's preliminary permission check may be a warning. Use the final Hosting API error as the deployment failure reason.

---

## Parent listings and homepage

- For large generated trees, use native Windows `robocopy /E /MT:8 /R:1 /W:1` for the output transfer; recursive PowerShell `Copy-Item` can make the copy slower than the bake. Verify absolute source/destination roots and do not use mirroring to delete checkout files. Before pushing, scope page copies to published English IDs and registered published variants in `Translations.tsv`; preserve the renderer's language-prefixed root output rather than assuming every translated homepage uses the canonical homepage alias. Restore unrelated baseline routes and remove shadowing flat page artifacts through the publisher's normal layout rules.

- **Sitewide CSS changes**: Tiggu inlines shared CSS into each rendered HTML page. Rebuild every published page (with no `Config/Render.lsv`) and deploy the changed HTML across the public tree; copying only the shared script or homepage leaves other pages with old styles. Keep the published slug list as the scope when copying artifacts, so stale local bake files do not enter `web-public`.
- An isolated child publish does not rebuild parent listing HTML. To refresh tiles on a parent (e.g. `/computer/game`), RootSlug must be `computer/game`, not only `computer/game/doom`.
- Do not run `publish-notion.ps1 -Slug root`. The published Notion `root` row is pulled into local homepage components and menu policies with NCMS `sync-home`, then rebuilt with Tiggu and a temporary `Config/Render.lsv` containing only `root` (see `ujnotes-home-tree`).

---

## Preconditions

- Clean `web-site` (`D:\Ujnotes\Website\site\project`) and `web-public` (`D:\Ujnotes\Website\project\build`) before publishing.
- Filter `ID.tsv`, every `ID_<lang>.tsv`, `Translations.tsv`, and every `Url_<lang>.tsv` to the selected scope for an isolated build. Header-only localized URL tables are valid when all diagrams are inline. Include required shared script assets if script versioning is enabled; for a content-only preflight that reuses deployed scripts, invoke the native runner with `-SkipScriptVersioning`.
- Local draft previews use `?full=true` on HTML or JSON routes. Keep the TSV `Status` column intact when the runtime includes draft rows; dropping the first cell shifts every field and makes the draft slug unreachable.
- For the approved interim/public bake before queuing a new article, temporarily set its source ID and translation statuses to `publish` so the local renderer serves it, then restore the exact draft files. Use an isolated writable project copy with `Render.lsv`, filtered localized ID and translation tables, and only the article's needed URL rows. `Render.lsv` alone limits English pages; Tiggu still walks every published localized row and every global URL asset. Verify both languages' HTML/JSON, disclosure, and canonical cover in the isolated output before queuing the Notion row.

---

## After deploy verification

### Slow-stage recovery

- OliveTin cleanup may continue after a publisher checkpoint reports success. Wait for the Console execution itself to finish before starting another publishing action; its concurrency guard covers cleanup too.
- Distinguish rendering from output transfer and Git text normalization. If a completed bake is followed by a stalled transfer, stop only the identified Console execution, wait for its child processes to exit, and finish from the existing verified output. Do not requeue Notion or repeat the bake just to retry copying.
- A native replacement for a slow `Repair-GitTextTree` pass must preserve the same extension allowlist and special filenames, UTF-8 BOM removal, CRLF/CR to LF, trailing whitespace removal per line, and exactly one terminal LF. Compare bytes and write only changed files. Run `git diff --cached --check` before committing.
- A Git lock after cancellation may belong to a child process still exiting. Inspect processes and wait for release; do not delete a live lock.

Verify:
- `https://ujnotes.com/{slug}`
- `https://ujnotes.com/{slug}.json`
- `https://ujnotes.com/<lang>/{slug}.json` when translated
- `https://ujnotes.com/{slug}.jpg`
- Parent listing tile `src=` when the cover is new

Commit leftover `web-site` ID/Url/PHP updates. Production is the `web-public` push.
