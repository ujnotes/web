---
name: ujnotes-publish-articles
description: >-
  Publishes Ujnotes Notion articles through publish-notion.ps1 /
  publish-notion-subtree.ps1, including HTML, AJAX JSON, covers, inline
  assets, parent listing tiles, UTF-8, and production verification. Use when
  publishing, republishing, deploying ujnotes.com, or queuing Notion Status.
---

# Publish Ujnotes articles

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

---

## Parent listings and homepage

- An isolated child publish does not rebuild parent listing HTML. To refresh tiles on a parent (e.g. `/computer/game`), RootSlug must be `computer/game`, not only `computer/game/doom`.
- Do not run `publish-notion.ps1 -Slug root`. Rebuild the homepage with Tiggu and a temporary `Config/Render.lsv` containing only `root` (see `ujnotes-home-tree`).

---

## Preconditions

- Clean `web-site` (`D:\Ujnotes\Website\site\project`) and `web-public` (`D:\Ujnotes\Website\project\build`) before publishing.
- Filter `ID.tsv`, every `ID_<lang>.tsv`, and `Translations.tsv` to the selected slug for an isolated build.

---

## After deploy verification

Verify:
- `https://ujnotes.com/{slug}`
- `https://ujnotes.com/{slug}.json`
- `https://ujnotes.com/<lang>/{slug}.json` when translated
- `https://ujnotes.com/{slug}.jpg`
- Parent listing tile `src=` when the cover is new

Commit leftover `web-site` ID/Url/PHP updates. Production is the `web-public` push.
