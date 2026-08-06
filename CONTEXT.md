# Ujnotes – AI Agent Context

## Project

Ujnotes is a static knowledge publishing platform (ujnotes.com), backed by a CMS rather than a traditional database-driven website.

It is intended to be:

- documentation
- articles
- technical notes
- knowledge base

rather than a blogging platform with dynamic editing.

---

# Overall Architecture

The publishing pipeline is intentionally separated into stages.

```
Notion / NCMS
        │
        ▼
Content Model
        │
        ▼
render.sh
        │
        ▼
Generated Static Site
        │
        ▼
project/build/public
        │
        ▼
Git
        │
        ▼
CI/CD
        │
        ▼
ujnotes.com
```

Important repositories mentioned:

- `web-site`
- `web`

A rendering script (`render.sh`) converts CMS content into the generated static website.

The generated output lives under

```
project/build/public
```

which is what ultimately gets committed/deployed.

---

# Content Source

The CMS (referred to as NCMS in earlier discussions) is the source of truth.

Workflow:

1. Edit content inside CMS
2. Run renderer
3. Generated HTML produced
4. Commit generated output
5. CI deploys site

The generated website is **not** edited manually.

---

# Localization Design

Localization received considerable design discussion.

## Language property

Each document contains a

```
Language
```

property.

Phase 1 values:

```
en
hi
```

This is a Notion Select property.

Existing documents default to

```
en
```

---

# URL Design

Decision:

English is the default language.

URLs:

```
/article-name
```

instead of

```
/en/article-name
```

Other languages receive prefixes.

Example

```
/hello-world

/hi/hello-world
```

This was an explicit design decision.

---

# Translation Independence

Translations are **not** blocking.

Each language can be published independently.

Meaning:

If only English exists:

```
Published
```

If Hindi isn't ready:

```
No Hindi page
```

The existence of one language should never prevent publishing another.

---

# Shared Identity

All translated pages share the same logical identity.

A common

```
Id
```

(or slug identifier)

is reused across languages.

Example

| Id | Language |
|------|----------|
| install-linux | en |
| install-linux | hi |

The language changes.

The logical article does not.

---

# Initial Scope

Phase 1 intentionally minimizes implementation work.

Only:

- add Language field
- default existing pages to English
- introduce language prefixes
- reuse Id

No major rendering engine redesign was intended initially.

---

# Publishing Philosophy

The design favors:

- static generation
- deterministic builds
- reproducible output
- CMS as source of truth

rather than runtime rendering.

---

# Important Design Decisions

### ✔ English is canonical

English URLs remain shortest.

```
/
/article
```

not

```
/en/article
```

---

### ✔ Other languages are additive

Languages extend the site.

They do not replace English.

---

### ✔ Shared article identity

Every translation maps to one conceptual article.

This simplifies:

- cross-language navigation
- canonical linking
- future translation management

---

### ✔ Translation rollout is incremental

Languages can launch one at a time.

No requirement for translation completeness.

---

# Known Build Process

```
CMS
    ↓
render.sh
    ↓
build/public
    ↓
Git
    ↓
CI/CD
```

---

# Assumptions Another AI Agent Should Preserve

- Never edit generated HTML directly.
- CMS is the authoritative content source.
- English has no `/en` URL prefix.
- Other languages use language prefixes.
- Articles across languages share the same logical `Id`.
- Publishing one language must not depend on other translations being complete.
- Existing content defaults to English.
- The renderer is responsible for language-aware output.
- Deployment occurs from the generated `build/public` artifacts, not the CMS directly.
