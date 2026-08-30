---
name: ujnotes-publish-articles
description: >-
  Publishes Ujnotes Notion articles through publish-notion.ps1 /
  publish-notion-subtree.ps1, including HTML, AJAX JSON, covers, inline
  assets, parent listing tiles, UTF-8, and production verification. Use when
  publishing, republishing, deploying ujnotes.com, or queuing Notion Status.
---

# Publish Ujnotes articles

For a **new** article, do not start here. Follow `H:\AGENTS.md` **New article sequence**: Notion English, then approved translations, then local files, then approved interim/public bake, then this publish-to-web step.

## Command

From `H:\Website\project` (do not wrap in `powershell.exe -File`):

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
& .\publish-notion-subtree.ps1 -RootSlug <slug>
```

Covers already on disk: omit `-CoverSource`. Use `-DryRun` first when the subtree is uncertain.

Single article (no descendants): queue that canonical Notion row to `publish`, then `& .\publish-notion.ps1 -Slug <slug>`. The single-page publisher only selects `Status=publish` rows.

Default `-NcmsProject` is `H:\Website\ncms`. Console does not pass that switch. Do not use `D:\Projects\Cutie\Sample\ncms\project` unless that tree is confirmed to include `resolve_publish_pages` and `wrap_leading_date`. Website NCMS must keep both, or a slug-targeted publish fails and Timeline date spans are missing from generated PHP.

After NCMS copies each variant `index.php`, `publish-notion.ps1` must run `Protect-TimelineDates.py` on that file. That re-wraps leading `dd Mon yyyy —` as `<span class='date'>…</span> —` so a republish cannot drop WCodes-style dash alignment. The wrap is idempotent. CSS lives in site `CSS/Base/Component/Timeline.css` and Framework `CSS/Base/Component/Timeline.css` (`min-width:11ch`). Verify live `/{slug}.json` still contains `class='date'`.

Isolated Tiggu may write flat `public/{slug}.html` and `.json` instead of `{slug}/index.*`. Use `Resolve-StagedPageArtifacts` to install the index layout, then delete shadowing flats.

`Merge-IdRow` must preserve an existing `Config/ID.tsv` Type. Timeline, Changelog, and Roadmap are `page`.

## What must be published together

XURL navigation loads `/{slug}.json` (and `/<lang>/{slug}.json`), not the HTML file. A full-page reload can look correct while AJAX still shows the previous article.

For every canonical row, the publisher must deploy **both** `index.html` and `index.json`, then verify live `/{slug}.json` (and each translation JSON) against the baked `index.json`. Do not treat HTML-only copy as a finished publish.

Also deploy:

- cover `/{slug}.jpg` (on disk as `index.jpg` plus Firebase rewrite)
- inline Url.tsv assets (for example `example.svg` beside the article)
- nested translation HTML/JSON atomically

## Parent listings and homepage

An isolated child publish does not rebuild parent listing HTML. If `/computer/algorithm` still uses `/resource/placeholder.svg` while `/computer/algorithm/binary_search.jpg` is live, republish `computer/algorithm`. Check listing `src=`, not only the article URL.

Do not run `publish-notion.ps1 -Slug root`. Rebuild the homepage with Tiggu and `Config/Render.lsv` containing only `root`.

## Preconditions

- Clean `web-site` (`H:\Website\site\project`) and `web-public` (`H:\Website\project\build`) before a subtree publish.
- Localized `Config/ID_<lang>.tsv` descriptions must match Notion exactly. A trailing `।` in Hindi that Notion does not have fails "Built JSON description does not match Notion".
- Filter `ID.tsv`, every `ID_<lang>.tsv`, and `Translations.tsv` to the selected slug for an isolated build.

## After deploy

Verify:

- `https://ujnotes.com/{slug}`
- `https://ujnotes.com/{slug}.json`
- `https://ujnotes.com/<lang>/{slug}.json` when translated
- `https://ujnotes.com/{slug}.jpg`
- parent listing tile `src=` when the cover is new

Commit leftover `web-site` ID/Url/PHP updates. Production is the `web-public` push.
