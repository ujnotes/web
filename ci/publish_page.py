#!/usr/bin/env python3
"""Cross-platform helpers for the guarded page publication workflow."""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path


SAFE_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]*$")
LANGUAGE_PREFIX = re.compile(r"^[a-z]{2,3}(?:-[a-z]{2})?$")
PHP_DIAGNOSTIC = re.compile(
    r"\b(?:PHP\s+)?(?:warning|fatal error|parse error|notice|deprecated)\s*:",
    re.IGNORECASE,
)


ASSET_REFERENCE = re.compile(
    r"""(?:src|href)\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s>]+))""",
    re.IGNORECASE,
)
PUBLISHED_ASSET_EXTENSIONS = {
    ".css",
    ".gif",
    ".jpeg",
    ".jpg",
    ".js",
    ".png",
    ".svg",
    ".webp",
    ".woff",
    ".woff2",
}


def validate_slug(slug):
    if (
        not slug
        or slug.startswith("/")
        or slug.endswith("/")
        or "\\" in slug
        or any(part in {".", ".."} for part in slug.split("/"))
        or not SAFE_SLUG.fullmatch(slug)
    ):
        raise ValueError(f"Unsafe article slug: {slug!r}")
    return slug


def parse_publish_target(requested_slug, candidate_slugs=()):
    """Resolve ``hi/slug`` public paths to ``(base_slug, language_or_None)``."""
    requested_slug = validate_slug(requested_slug)
    candidate_slugs = set(candidate_slugs)
    if requested_slug in candidate_slugs:
        return requested_slug, None
    parts = requested_slug.split("/", 1)
    if len(parts) == 2:
        language, remainder = parts[0].lower(), parts[1]
        if LANGUAGE_PREFIX.fullmatch(language):
            validate_slug(remainder)
            if not candidate_slugs or remainder in candidate_slugs:
                return remainder, language
    return requested_slug, None


def read_metadata(path):
    metadata_path = Path(path).resolve()
    with metadata_path.open(encoding="utf-8") as source:
        metadata = json.load(source)
    if not metadata.get("no_work"):
        validate_slug(metadata.get("slug", ""))
        if not metadata.get("page_id") and metadata.get("content_source") != "github":
            raise RuntimeError("NCMS metadata does not contain page_id")
    return metadata_path, metadata


def tsv_field_map(header_line, row_line):
    headers = header_line.split("\t")
    fields = row_line.split("\t")
    fields.extend([""] * (len(headers) - len(fields)))
    return {
        name.lower(): fields[index]
        for index, name in enumerate(headers)
    }


def published_translation_languages(path, slug):
    path = Path(path)
    if not path.is_file():
        return ["en"]
    lines = read_lines(path)
    if not lines:
        return ["en"]
    header = lines[0].split("\t")
    if not header or header[0] != "TranslationGroup":
        raise RuntimeError(f"Invalid translation manifest header: {path}")
    for line in lines[1:]:
        fields = line.split("\t")
        if not fields or fields[0] != slug:
            continue
        languages = []
        for index, language in enumerate(header[1:], start=1):
            status = fields[index] if index < len(fields) else ""
            if status == "published":
                languages.append(language.lower())
        if "en" not in languages:
            languages.insert(0, "en")
        return list(dict.fromkeys(languages))
    return ["en"]


def resolve_article_component(source, slug, language):
    if language == "en":
        flat = resolve_flat_php_component(source, slug)
        if flat is not None:
            return flat
        if slug == "root":
            raise RuntimeError(
                f"GitHub source is missing the root component: {source}/Root/HTML/Component/Root.php"
            )
    parts = ["Root", "HTML", "Component"]
    if language != "en":
        parts.append(language)
    parts.extend(slug.split("/"))
    parts.append("index.php")
    component = resolve_case_insensitive(source, Path(*parts))
    if component is None or not component.is_file():
        raise RuntimeError(
            f"GitHub source is missing component for {language!r}: "
            f"{Path(*parts).as_posix()}"
        )
    return component


def resolve_flat_php_component(source, slug):
    """Return an existing code-native flat Component/{slug}.php when present."""
    leaf = slug.rsplit("/", 1)[-1]
    parent_parts = ["Root", "HTML", "Component", *slug.split("/")[:-1]]
    return resolve_case_insensitive(source, Path(*parent_parts, f"{leaf}.php"))


def remove_shadowing_component_dir(source, slug):
    """Remove slug/ when a flat slug.php exists so PHP resolve prefers the flat file."""
    parent_parts = ["Root", "HTML", "Component", *slug.split("/")[:-1]]
    leaf = slug.rsplit("/", 1)[-1]
    shadow = resolve_case_insensitive(source, Path(*parent_parts, leaf))
    if shadow is not None and shadow.is_dir():
        shutil.rmtree(shadow)


def article_metadata_from_id(path, slug):
    header, row = find_article_row(path, slug)
    values = tsv_field_map(header, row)
    return {
        "title": values.get("title", ""),
        "description": values.get("description", ""),
        "label": values.get("label", ""),
    }


def write_metadata(path, metadata):
    with Path(path).open("w", encoding="utf-8", newline="\n") as target:
        json.dump(metadata, target, ensure_ascii=False, indent=2)
        target.write("\n")


def safe_target(root, relative):
    root = Path(root).resolve()
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise RuntimeError(f"Refusing path outside {root}: {target}")
    return target


def read_lines(path):
    return Path(path).read_text(encoding="utf-8").splitlines()


def write_lines(path, lines):
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def resolve_case_insensitive(root, relative):
    """Resolve a complete relative path without duplicating legacy casing."""
    root = Path(root).resolve()
    requested_parts = Path(relative).parts

    def resolve_from(current, index):
        if index == len(requested_parts):
            return current
        if not current.is_dir():
            return None
        requested_part = requested_parts[index]
        matches = [
            child
            for child in current.iterdir()
            if child.name.casefold() == requested_part.casefold()
        ]
        matches.sort(key=lambda child: child.name != requested_part)
        resolved = []
        for match in matches:
            candidate = resolve_from(match, index + 1)
            if candidate is not None:
                resolved.append(candidate)
        unique = {candidate.resolve() for candidate in resolved}
        if len(unique) > 1:
            raise RuntimeError(
                f"Ambiguous case-insensitive path below {current}: {requested_part}"
            )
        return resolved[0] if resolved else None

    return resolve_from(root, 0)


def first_notion_image_url(blocks):
    for block in blocks:
        if block.get("type") != "image":
            continue
        image = block.get("image", {})
        image_type = image.get("type")
        image_source = image.get(image_type, {}) if image_type else {}
        if image_source.get("url"):
            return image_source["url"]
    return None


def notion_json(url, api_key):
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
            "User-Agent": "ujnotes-publisher",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def notion_cover_target(source, slug):
    relative = Path("Root", "Resource", *slug.split("/"), "index.jpg")
    existing = resolve_case_insensitive(source, relative)
    if existing is not None:
        return existing
    parent = resolve_case_insensitive(source, relative.parent)
    return parent / "index.jpg" if parent is not None else safe_target(source, relative)


def resolve_component_cover(source, slug):
    """Find a cover under Resource/<slug> (index.* or flat slug.*)."""
    resource_root = Path("Root", "Resource", *slug.split("/"))
    candidates = [
        resource_root.with_suffix(".jpg"),
        resource_root.with_suffix(".png"),
        resource_root.with_suffix(".svg"),
        resource_root / "index.jpg",
        resource_root / "index.png",
        resource_root / "index.svg",
    ]
    for relative in candidates:
        existing = resolve_case_insensitive(source, relative)
        if existing is not None and existing.is_file():
            return existing
    return None


def materialize_staged_cover(stage, slug, cover, flat_fields=None):
    """Copy a Resource cover into public layouts Tiggu/publish expect; skip HTTP fetch."""
    slug = str(slug).replace("\\", "/").strip("/")
    if not slug or cover is None or not cover.is_file():
        return False
    staged_index = safe_target(
        stage, Path("public", *slug.split("/"), "index.jpg")
    )
    staged_index.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cover, staged_index)
    fields = flat_fields if flat_fields is not None else cover_url_fields(slug)
    flat = staged_url_artifact(stage, fields)
    if flat is not None:
        flat.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cover, flat)
    return True


def download_notion_cover(source, slug, page_id, api_key):
    endpoint = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
    while endpoint:
        payload = notion_json(endpoint, api_key)
        image_url = first_notion_image_url(payload.get("results", []))
        if image_url:
            break
        cursor = payload.get("next_cursor") if payload.get("has_more") else None
        endpoint = (
            "https://api.notion.com/v1/blocks/"
            f"{page_id}/children?page_size=100&start_cursor={cursor}"
            if cursor
            else None
        )
    else:
        return None

    request = urllib.request.Request(
        image_url, headers={"User-Agent": "ujnotes-publisher"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        content_type = response.headers.get_content_type()
        if content_type != "image/jpeg":
            raise RuntimeError(f"Notion cover must be JPEG, got {content_type!r}")
        content = response.read(50 * 1024 * 1024 + 1)
    if len(content) > 50 * 1024 * 1024:
        raise RuntimeError("Notion cover exceeds 50 MiB")

    cover = notion_cover_target(source, slug)
    cover.parent.mkdir(parents=True, exist_ok=True)
    cover.write_bytes(content)
    return cover

def parent_slug(slug):
    if slug == "root":
        return None
    if "/" not in slug:
        return "root"
    return slug.rsplit("/", 1)[0]


def published_article_slugs(path):
    """Return published/publish article IDs from an ID.tsv in file order."""
    rows = []
    for line in read_lines(path)[1:]:
        fields = line.split("\t")
        if len(fields) >= 2 and fields[0] in {"published", "publish"}:
            rows.append(fields[1])
    return rows


def affected_navigation_slugs(path, slug):
    """Return the article, its ancestors, and adjacent siblings."""
    rows = published_article_slugs(path)

    affected = {slug}
    current = parent_slug(slug)
    while current:
        affected.add(current)
        current = parent_slug(current)

    article_parent = parent_slug(slug)
    siblings = [row_slug for row_slug in rows if parent_slug(row_slug) == article_parent]
    if slug in siblings:
        index = siblings.index(slug)
        if index:
            affected.add(siblings[index - 1])
        if index + 1 < len(siblings):
            affected.add(siblings[index + 1])

    return [row_slug for row_slug in rows if row_slug in affected]


def files_identical(left, right):
    left = Path(left)
    right = Path(right)
    if left.stat().st_size != right.stat().st_size:
        return False
    left_hash = hashlib.sha256()
    right_hash = hashlib.sha256()
    with left.open("rb") as left_file, right.open("rb") as right_file:
        for chunk in iter(lambda: left_file.read(1024 * 1024), b""):
            left_hash.update(chunk)
        for chunk in iter(lambda: right_file.read(1024 * 1024), b""):
            right_hash.update(chunk)
    return left_hash.digest() == right_hash.digest()


def merge_lowercase_path(source, target):
    source = Path(source)
    target = Path(target)
    if source.parent == target.parent and source.name == target.name:
        return target
    if target.exists():
        try:
            if source.samefile(target):
                return source
        except OSError:
            pass
        if source.is_dir() and target.is_dir():
            for child in list(source.iterdir()):
                merge_lowercase_path(child, target / child.name.lower())
            source.rmdir()
            return target
        if source.is_file() and target.is_file() and files_identical(source, target):
            source.unlink()
            return target
        raise RuntimeError(f"Conflicting lowercase stage paths: {source} and {target}")
    source.rename(target)
    return target


def normalize_tree_lowercase(root):
    """Normalize an isolated stage tree to lowercase, merging safe collisions."""
    root = Path(root)
    if not root.is_dir():
        return
    for child in list(root.iterdir()):
        if child.is_dir():
            normalize_tree_lowercase(child)
        merge_lowercase_path(child, root / child.name.lower())


def find_article_row(path, slug):
    lines = read_lines(path)
    if not lines:
        raise RuntimeError(f"TSV is empty: {path}")
    for line in lines[1:]:
        fields = line.split("\t")
        if len(fields) >= 2 and fields[1] == slug:
            return lines[0], line
    raise RuntimeError(f"No generated ID row for {slug!r} in {path}")


def merge_id_row(path, slug, new_row, status=None):
    lines = read_lines(path)
    if not lines:
        raise RuntimeError(f"ID file is empty: {path}")
    header = lines[0].split("\t")
    fields = new_row.split("\t")
    fields.extend([""] * (len(header) - len(fields)))
    if status is not None:
        if "Status" not in header:
            raise RuntimeError(f"ID file has no Status column: {path}")
        fields[header.index("Status")] = status
    if "Type" in header:
        fields[header.index("Type")] = "article"
    new_row = "\t".join(fields[: len(header)])

    output = [lines[0]]
    found = False
    for line in lines[1:]:
        current = line.split("\t")
        if len(current) >= 2 and current[1] == slug:
            output.append(new_row)
            found = True
        else:
            output.append(line)
    if not found:
        output.append(new_row)
    write_lines(path, output)
    return new_row


def merge_url_row(path, slug, has_cover):
    lines = read_lines(path)
    if not lines:
        lines = ["Path\tName\tExtension"]
    output = [lines[0]]
    for line in lines[1:]:
        fields = parse_url_row(line)
        first = fields[0].replace("\\", "/").rstrip("/")
        row_slug = url_row_article_slug(fields)
        # Drop legacy folder-form and flat-form cover rows for this slug.
        if first == slug or row_slug == slug:
            continue
        output.append(line)
    if has_cover:
        output.append("\t".join(cover_url_fields(slug)))
    write_lines(path, output)


def parse_url_row(line):
    """Split a Url.tsv row, preserving a leading empty Path field."""
    fields = line.split("\t")
    fields.extend([""] * (3 - len(fields)))
    return fields[:3]


COVER_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "webp"})


def cover_url_fields(slug):
    """Return Url.tsv fields that Tiggu resolves to /{slug}.jpg."""
    slug = str(slug).replace("\\", "/").strip("/")
    if not slug:
        raise ValueError("cover slug required")
    if "/" in slug:
        parent, name = slug.rsplit("/", 1)
        return [f"{parent}/", name, "jpg"]
    return ["", slug, "jpg"]


def is_article_cover_row(fields):
    _, name, extension = fields[:3] if len(fields) >= 3 else ("", "", "")
    return bool(name and extension.lower() in COVER_EXTENSIONS)


def normalize_url_row(fields, language="en"):
    """
    Normalize Url.tsv fields to Tiggu's form:
    - root assets use a leading empty Path ("\\tscript\\tjs")
    - article covers use flat /{slug}.jpg fields (parent/\\tleaf\\tjpg)
    - legacy slug[/]\\tindex\\tjpg cover rows are rewritten to that flat form
    """
    path, name, extension = parse_url_row("\t".join(fields))
    # Repair legacy two-column root assets: "script\\tjs" => "\\tscript\\tjs".
    if path and not extension and name in {
        "js",
        "css",
        "json",
        "txt",
        "xml",
        "png",
        "jpg",
        "jpeg",
        "ico",
        "svg",
        "webp",
    }:
        path, name, extension = "", path, name

    path = path.replace("\\", "/").replace("//", "/")
    extension_l = extension.lower()

    # Legacy covers: "world/philosophy/life[/]\\tindex\\tjpg" → flat /slug.jpg
    if name == "index" and extension_l in COVER_EXTENSIONS and path:
        slug = path.strip("/")
        if language != "en" and slug and not slug.startswith(f"{language}/"):
            slug = f"{language}/{slug}"
        return cover_url_fields(slug)

    if language != "en" and name and extension_l in COVER_EXTENSIONS:
        slug = f"{path.strip('/')}/{name}" if path.strip("/") else name
        if not slug.startswith(f"{language}/"):
            slug = f"{language}/{slug}"
        return cover_url_fields(slug)

    if (
        name
        and name != "index"
        and extension_l in COVER_EXTENSIONS
        and path
        and not path.endswith("/")
    ):
        path = f"{path}/"

    if language != "en" and path and not path.startswith(f"{language}/"):
        path = f"{language}/{path.lstrip('/')}"
    return [path, name, extension]


def is_global_script_row(fields):
    path, name, extension = normalize_url_row(fields)
    return path == "" and name == "script" and extension == "js"


def url_row_article_slug(fields):
    path, name, extension = normalize_url_row(fields)
    if name and extension.lower() in COVER_EXTENSIONS:
        parent = path.replace("\\", "/").strip("/")
        return f"{parent}/{name}" if parent else name
    if not path:
        return None
    return path.rstrip("/")


def add_sitemap_url(path, url):
    path = Path(path)
    content = path.read_text(encoding="utf-8")
    canonical = url.rstrip("/")
    escaped = re.escape(canonical)
    existing = re.compile(rf"<loc>{escaped}/?</loc>", re.IGNORECASE)
    if existing.search(content):
        content = existing.sub(f"<loc>{canonical}</loc>", content)
        path.write_text(content, encoding="utf-8", newline="\n")
        return
    if "</urlset>" not in content:
        raise RuntimeError(f"Invalid sitemap; missing </urlset>: {path}")
    entry = f"\t<url>\n\t\t<loc>{canonical}</loc>\n\t</url>\n"
    content = content.replace("</urlset>", entry + "</urlset>")
    path.write_text(content, encoding="utf-8", newline="\n")


def article_variants(metadata):
    """Return normalized variants, including legacy single-article bundles."""
    variants = metadata.get("variants") or [
        {
            "slug": metadata["slug"],
            "title": metadata.get("title", ""),
            "description": metadata.get("description", ""),
            "language": metadata.get("language", "en"),
            "component": metadata["component"],
        }
    ]
    normalized = []
    seen = set()
    for raw_variant in variants:
        variant = dict(raw_variant)
        variant["slug"] = validate_slug(variant.get("slug", metadata["slug"]))
        variant["language"] = str(variant.get("language", "en")).lower()
        if variant["slug"] != metadata["slug"]:
            raise RuntimeError("All translation variants must use the base article slug")
        if variant["language"] in seen:
            raise RuntimeError(f"Duplicate article language: {variant['language']!r}")
        if not variant.get("component"):
            raise RuntimeError(f"Article variant {variant['language']!r} has no component")
        variant["public_slug"] = (
            variant["slug"]
            if variant["language"] == "en"
            else f"{variant['language']}/{variant['slug']}"
        )
        seen.add(variant["language"])
        normalized.append(variant)
    if "en" not in seen and not metadata.get("translation_merge"):
        raise RuntimeError("Nested translation bundles require an English base variant")
    return normalized


def sitemap_page_url(base_url, public_slug):
    base = base_url.rstrip("/")
    return base if public_slug == "root" else f"{base}/{public_slug}"


def localized_menu_slugs(variants):
    """Return menu routes that must accompany translated home pages."""
    return [
        f"{variant['language']}/menu"
        for variant in variants
        if variant["slug"] == "root" and variant["language"] != "en"
    ]


def localized_home_variants(variants):
    """Return translated root variants served from /{language}."""
    return [
        variant
        for variant in variants
        if variant["slug"] == "root" and variant["language"] != "en"
    ]


def merge_firebase_language_home(path, language, public_slug):
    """Map /{language} to the rendered translated root page on static hosting."""
    path = Path(path)
    with path.open(encoding="utf-8") as source:
        data = json.load(source)
    hosting = data.setdefault("hosting", {})
    rewrites = hosting.setdefault("rewrites", [])
    required = [
        {
            "source": f"/{language}",
            "destination": f"/{public_slug}/index.html",
        },
        {
            "source": f"/{language}.json",
            "destination": f"/{public_slug}/index.json",
        },
    ]
    for wanted in required:
        existing = next(
            (item for item in rewrites if item.get("source") == wanted["source"]),
            None,
        )
        if existing and existing.get("destination") != wanted["destination"]:
            raise RuntimeError(
                f"Rewrite {wanted['source']!r} already points to "
                f"{existing.get('destination')!r}"
            )
        if not existing:
            rewrites.insert(0, wanted)

    with path.open("w", encoding="utf-8", newline="\n") as target:
        json.dump(data, target, ensure_ascii=False, indent=2)
        target.write("\n")


def merge_translation_manifest(path, slug, languages, merge=False):
    path = Path(path)
    lines = read_lines(path) if path.is_file() else []
    old_header = lines[0].split("\t") if lines else ["TranslationGroup", "en"]
    if old_header[0] != "TranslationGroup":
        raise RuntimeError(f"Invalid translation manifest header: {path}")
    header = list(old_header)
    for language in languages:
        if language not in header:
            header.append(language)
    output = ["\t".join(header)]
    found = False
    for line in lines[1:]:
        fields = line.split("\t")
        if fields and fields[0] == slug:
            values = {
                name: fields[index] if index < len(fields) else ""
                for index, name in enumerate(old_header)
            }
            if not merge:
                for language in header[1:]:
                    values[language] = ""
            values.update({language: "published" for language in languages})
            values["TranslationGroup"] = slug
            output.append("\t".join(values.get(name, "") for name in header))
            found = True
        else:
            fields.extend([""] * (len(header) - len(fields)))
            output.append("\t".join(fields[: len(header)]))
    if not found:
        output.append(
            "\t".join(
                [slug]
                + [
                    "published" if language in languages else ""
                    for language in header[1:]
                ]
            )
        )
    write_lines(path, [line.rstrip("\t") for line in output])


def prepare_source(args):
    metadata_path, metadata = read_metadata(args.metadata)
    if metadata.get("no_work"):
        return
    slug = metadata["slug"]
    variants = article_variants(metadata)
    bundle = Path(args.bundle).resolve()
    source = Path(args.source).resolve()

    source_components = []
    for variant in variants:
        generated_component = safe_target(bundle, variant["component"])
        if variant["language"] == "en":
            flat = resolve_flat_php_component(source, slug)
            if flat is not None:
                # Code-native flat English pages (Root.php, About_me.php, …) keep
                # layout/helpers that Notion HTML does not represent. Writing
                # slug/index.php beside them shadows the flat file on Linux and
                # breaks JSON endpoints (HTML/PHP fatals instead of JSON).
                remove_shadowing_component_dir(source, slug)
                variant["source_component"] = flat.relative_to(source).as_posix()
                source_components.append(variant["source_component"])
                continue
        component_parts = ["Root", "HTML", "Component"]
        if variant["language"] != "en":
            component_parts.append(variant["language"])
        component_parts.extend(slug.split("/"))
        component_parts.append("index.php")
        component_relative = Path(*component_parts)
        source_component = resolve_case_insensitive(source, component_relative)
        if source_component is None:
            source_component = safe_target(source, component_relative)
        source_component.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(generated_component, source_component)
        generated_text = source_component.read_text(encoding="utf-8")
        generated_text = generated_text.replace(
            "<?php require('../JS/Base/page.js'); ?>", ""
        )
        if slug == "root" and variant["language"] != "en":
            generated_text = generated_text.replace(
                "<?php require('../HTML/Fragment/Component_bottom.php') ?>", ""
            )

        normalized_lines = [
            line.rstrip() for line in generated_text.splitlines()
        ]
        while normalized_lines and not normalized_lines[-1]:
            normalized_lines.pop()
        source_component.write_text(
            "\n".join(normalized_lines) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        variant["source_component"] = source_component.relative_to(source).as_posix()
        source_components.append(variant["source_component"])

    api_key = os.environ.get("NOTION_API_KEY")
    notion_cover = (
        download_notion_cover(source, slug, metadata["page_id"], api_key)
        if api_key
        else None
    )
    cover = notion_cover if notion_cover is not None else resolve_component_cover(
        source, slug
    )
    cover_is_file = cover is not None and cover.is_file()
    # Only a real image (Notion download or git Resource) counts — never queue a
    # Url.tsv jpg fetch from a cover callout alone.
    has_cover = cover_is_file
    # Translations often omit the cover callout; inject it whenever the base
    # article has a cover so runtime can fall back to the base image URL.
    if has_cover:
        for variant in variants:
            source_component = safe_target(source, variant["source_component"])
            component_text = source_component.read_text(encoding="utf-8")
            if "Component_cover.php" not in component_text:
                alt = variant.get("title", metadata.get("title", ""))
                alt = alt.replace("\\", "\\\\").replace("'", "\\'")
                markup = (
                    f"<?php $alt='{alt}'; "
                    "require('../HTML/Fragment/Component_cover.php') ?>"
                )
                source_component.write_text(
                    markup + "\n\n" + component_text,
                    encoding="utf-8",
                    newline="\n",
                )

    source_ids = []
    source_urls = []
    for variant in variants:
        language = variant["language"]
        suffix = "" if language == "en" else f"_{language}"
        bundle_id = safe_target(bundle, Path("Config", f"ID{suffix}.tsv"))
        source_id = safe_target(source, Path("Config", f"ID{suffix}.tsv"))
        if not source_id.is_file():
            write_lines(source_id, [read_lines(bundle_id)[0]])
        _, generated_row = find_article_row(bundle_id, slug)
        variant["article_row"] = merge_id_row(
            source_id, slug, generated_row, status="published"
        )
        variant["source_id"] = source_id.relative_to(source).as_posix()
        source_ids.append(variant["source_id"])

        source_url = safe_target(source, Path("Config", f"Url{suffix}.tsv"))
        if not source_url.is_file() or not read_lines(source_url):
            default_url = safe_target(source, Path("Config", "Url.tsv"))
            write_lines(source_url, read_lines(default_url))
        merge_url_row(source_url, slug, has_cover)
        variant["source_url"] = source_url.relative_to(source).as_posix()
        source_urls.append(variant["source_url"])

    source_sitemap = safe_target(source, Path("Root", "Site", "sitemap.xml"))
    for variant in variants:
        add_sitemap_url(
            source_sitemap,
            sitemap_page_url(args.base_url, variant["public_slug"]),
        )

    translations = safe_target(source, Path("Config", "Translations.tsv"))
    merge_translation_manifest(
        translations,
        slug,
        [variant["language"] for variant in variants],
        merge=bool(metadata.get("translation_merge")),
    )
    english_variant = next(
        (variant for variant in variants if variant["language"] == "en"),
        None,
    )
    if english_variant is not None:
        base_id = safe_target(source, english_variant["source_id"])
    else:
        base_id = safe_target(source, Path("Config", "ID.tsv"))
        if slug not in published_article_slugs(base_id):
            raise RuntimeError(
                f"Cannot publish translation-only {slug!r}: "
                f"English base is missing from {base_id}"
            )
    affected_slugs = affected_navigation_slugs(base_id, slug)
    render_slugs = list(affected_slugs)
    render_slugs.extend(
        variant["public_slug"]
        for variant in variants
        if variant["language"] != "en"
    )
    render_slugs = list(dict.fromkeys(render_slugs))

    source_paths = list(
        dict.fromkeys(
            source_components
            + source_ids
            + source_urls
            + [
                translations.relative_to(source).as_posix(),
                source_sitemap.relative_to(source).as_posix(),
            ]
            + ([cover.relative_to(source).as_posix()] if cover_is_file else [])
        )
    )
    metadata.update(
        {
            "has_cover": has_cover,
            "cover_origin": "notion" if notion_cover is not None else "source",
            "source_cover": (
                cover.relative_to(source).as_posix() if cover_is_file else None
            ),
            "variants": variants,
            "source_component": source_components[0],
            "source_components": source_components,
            "source_id": source_ids[0],
            "source_ids": list(dict.fromkeys(source_ids)),
            "source_url": source_urls[0],
            "source_urls": list(dict.fromkeys(source_urls)),
            "source_translations": translations.relative_to(source).as_posix(),
            "source_sitemap": source_sitemap.relative_to(source).as_posix(),
            "article_row": variants[0]["article_row"],
            "affected_slugs": affected_slugs,
            "render_slugs": render_slugs,
            "source_paths": source_paths,
        }
    )
    write_metadata(metadata_path, metadata)


def _canonical_source_relative(source, path):
    relative = Path(path).resolve().relative_to(Path(source).resolve()).as_posix()
    if relative.lower().startswith("root/"):
        return "Root/" + relative[5:]
    return relative


def prepare_github_article(source, slug, metadata_path):
    """Build publication metadata for one GitHub article slug."""
    source = Path(source).resolve()
    metadata_path = Path(metadata_path).resolve()
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    translations = safe_target(source, Path("Config", "Translations.tsv"))
    published_slugs = published_article_slugs(
        safe_target(source, Path("Config", "ID.tsv"))
    )
    slug, requested_language = parse_publish_target(slug, published_slugs)
    languages = published_translation_languages(translations, slug)
    if requested_language:
        if requested_language not in languages:
            raise RuntimeError(
                f"No published {requested_language!r} translation for {slug!r}"
            )
        languages = [requested_language]
    variants = []
    source_components = []
    source_ids = []
    source_urls = []

    for language in languages:
        suffix = "" if language == "en" else f"_{language}"
        relative_id = Path("Config", f"ID{suffix}.tsv").as_posix()
        source_id = safe_target(source, relative_id)
        if not source_id.is_file():
            raise RuntimeError(f"GitHub source is missing ID map: {source_id}")
        fields = article_metadata_from_id(source_id, slug)
        source_component = resolve_article_component(source, slug, language)
        relative_url = Path("Config", f"Url{suffix}.tsv").as_posix()
        source_url = safe_target(source, relative_url)
        if not source_url.is_file():
            relative_url = Path("Config", "Url.tsv").as_posix()
            source_url = safe_target(source, relative_url)
        if not source_url.is_file():
            raise RuntimeError(f"GitHub source is missing URL map: {source_url}")

        relative_component = _canonical_source_relative(source, source_component)
        variant = {
            "slug": slug,
            "title": fields["title"],
            "description": fields["description"],
            "language": language,
            "component": relative_component,
            "source_component": relative_component,
            "source_id": relative_id,
            "source_url": relative_url,
            "article_row": find_article_row(source_id, slug)[1],
        }
        variants.append(variant)
        source_components.append(relative_component)
        source_ids.append(relative_id)
        source_urls.append(relative_url)

    cover = resolve_component_cover(source, slug)
    cover_is_file = cover is not None and cover.is_file()
    has_cover = cover_is_file

    english_id = next(
        (
            relative_id
            for relative_id, variant in zip(source_ids, variants)
            if variant["language"] == "en"
        ),
        Path("Config", "ID.tsv").as_posix(),
    )
    base_id = safe_target(source, english_id)
    if slug not in published_article_slugs(base_id):
        raise RuntimeError(
            f"Cannot publish {slug!r}: English base is missing from {base_id}"
        )
    affected_slugs = affected_navigation_slugs(base_id, slug)
    render_slugs = list(affected_slugs)
    render_slugs.extend(
        (
            variant["slug"]
            if variant["language"] == "en"
            else f"{variant['language']}/{variant['slug']}"
        )
        for variant in variants
        if variant["language"] != "en"
    )
    render_slugs = [item.lower() for item in dict.fromkeys(render_slugs)]
    for variant in variants:
        variant["public_slug"] = (
            variant["slug"]
            if variant["language"] == "en"
            else f"{variant['language']}/{variant['slug']}"
        ).lower()

    relative_translations = Path("Config", "Translations.tsv").as_posix()
    relative_sitemap = Path("Root", "Site", "sitemap.xml").as_posix()
    relative_cover = None
    if cover_is_file:
        relative_cover = _canonical_source_relative(source, cover)
    source_paths = list(
        dict.fromkeys(
            source_components
            + list(dict.fromkeys(source_ids))
            + list(dict.fromkeys(source_urls))
            + [relative_translations, relative_sitemap]
            + ([relative_cover] if relative_cover else [])
        )
    )

    metadata = {
        "content_source": "github",
        "slug": slug,
        "title": variants[0]["title"],
        "description": variants[0]["description"],
        "language": variants[0]["language"],
        "component": source_components[0],
        "queued_slugs": [slug],
        "variants": variants,
        "has_cover": has_cover,
        "cover_origin": "source",
        "source_cover": relative_cover,
        "source_component": source_components[0],
        "source_components": source_components,
        "source_id": source_ids[0],
        "source_ids": list(dict.fromkeys(source_ids)),
        "source_url": source_urls[0],
        "source_urls": list(dict.fromkeys(source_urls)),
        "source_translations": relative_translations,
        "source_sitemap": relative_sitemap,
        "article_row": variants[0]["article_row"],
        "affected_slugs": affected_slugs,
        "render_slugs": render_slugs,
        "source_paths": source_paths,
    }
    if requested_language:
        metadata["requested_language"] = requested_language
        metadata["translation_merge"] = True
    return metadata


def prepare_github_all(source, metadata_path):
    """Build publication metadata that renders every published GitHub article."""
    source = Path(source).resolve()
    metadata_path = Path(metadata_path).resolve()
    source_id = safe_target(source, Path("Config", "ID.tsv"))
    if not source_id.is_file():
        raise RuntimeError(f"GitHub source is missing ID map: {source_id}")
    slugs = published_article_slugs(source_id)
    if not slugs:
        raise RuntimeError("No published articles found in GitHub source")

    primary = "root" if "root" in slugs else slugs[0]
    metadata = prepare_github_article(source, primary, metadata_path)
    translations = safe_target(source, Path("Config", "Translations.tsv"))

    source_components = []
    render_slugs = []
    source_ids = list(metadata["source_ids"])
    source_urls = list(metadata["source_urls"])
    for slug in slugs:
        languages = published_translation_languages(translations, slug)
        for language in languages:
            suffix = "" if language == "en" else f"_{language}"
            relative_id = Path("Config", f"ID{suffix}.tsv").as_posix()
            id_path = safe_target(source, relative_id)
            if not id_path.is_file():
                raise RuntimeError(f"GitHub source is missing ID map: {id_path}")
            source_ids.append(relative_id)

            relative_url = Path("Config", f"Url{suffix}.tsv").as_posix()
            url_path = safe_target(source, relative_url)
            if not url_path.is_file():
                relative_url = Path("Config", "Url.tsv").as_posix()
                url_path = safe_target(source, relative_url)
            if not url_path.is_file():
                raise RuntimeError(f"GitHub source is missing URL map: {url_path}")
            source_urls.append(relative_url)

            component = resolve_article_component(source, slug, language)
            source_components.append(_canonical_source_relative(source, component))
            public_slug = slug if language == "en" else f"{language}/{slug}"
            render_slugs.append(public_slug.lower())

    metadata["queued_slugs"] = list(slugs)
    metadata["affected_slugs"] = list(slugs)
    metadata["render_slugs"] = list(dict.fromkeys(render_slugs))
    # Keep the primary article as the metadata anchor; lint every component.
    metadata["source_components"] = list(
        dict.fromkeys(list(metadata["source_components"]) + source_components)
    )
    metadata["source_ids"] = list(dict.fromkeys(source_ids))
    metadata["source_urls"] = list(dict.fromkeys(source_urls))
    metadata["render_scope"] = "all"
    metadata["source_paths"] = list(
        dict.fromkeys(
            metadata["source_components"]
            + metadata["source_ids"]
            + metadata["source_urls"]
            + [metadata["source_translations"], metadata["source_sitemap"]]
            + (
                [metadata["source_cover"]]
                if metadata.get("source_cover")
                else []
            )
        )
    )
    return metadata


def prepare_github(args):
    """Build publication metadata from an existing GitHub site checkout."""
    source = Path(args.source).resolve()
    metadata_path = Path(args.metadata).resolve()
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    requested = (args.slug or "").strip()
    if not requested or requested == "*":
        metadata = prepare_github_all(source, metadata_path)
    else:
        metadata = prepare_github_article(source, requested, metadata_path)
    write_metadata(metadata_path, metadata)
    print("GITHUB_RESULT=" + json.dumps(metadata, ensure_ascii=True))
    return metadata


def staged_url_artifact(stage, fields):
    if len(fields) < 3 or not fields[1] or not fields[2]:
        return None
    row_dir = fields[0].replace("\\", "/").strip("/")
    relative = Path(*row_dir.split("/")) if row_dir else Path()
    relative /= f"{fields[1]}.{fields[2]}"
    return safe_target(stage, Path("public") / relative)


def create_stage(args):
    _, metadata = read_metadata(args.metadata)
    source = Path(args.source).resolve()
    stage = Path(args.stage).resolve()
    if stage.exists():
        shutil.rmtree(stage)

    shutil.copytree(
        source,
        stage,
        ignore=shutil.ignore_patterns(".git", "public", "interim"),
    )
    (stage / "public").mkdir()
    (stage / "interim").mkdir()

    normalize_tree_lowercase(stage / "Root" / "HTML" / "Component")
    normalize_tree_lowercase(stage / "Root" / "Resource")
    normalize_tree_lowercase(stage / "Root" / "Site")

    normalized_components = []
    for component in metadata.get("source_components", []):
        resolved = resolve_case_insensitive(stage, Path(component))
        if resolved is None or not resolved.is_file():
            raise RuntimeError(f"Staged component not found: {component}")
        relative = resolved.relative_to(stage)
        normalized = Path(
            *relative.parts[:3],
            *(part.lower() for part in relative.parts[3:]),
        )
        normalized_components.append(normalized.as_posix())
    if normalized_components:
        metadata["source_component"] = normalized_components[0]
        metadata["source_components"] = normalized_components
        write_metadata(Path(args.metadata), metadata)

    variants = article_variants(metadata)
    render_all = metadata.get("render_scope") == "all"
    has_translation_variant = any(
        variant["language"] != "en" for variant in variants
    )
    render_slugs = (
        metadata.get("render_slugs")
        if render_all or len(variants) > 1 or has_translation_variant
        else metadata.get("affected_slugs")
    )
    if not render_slugs:
        variant = article_variants(metadata)[0]
        render_slugs = [variant["public_slug"]]
    # Public/render routes are always lowercase; interim may keep stylized case.
    render_slugs = [str(slug).lower() for slug in render_slugs]
    render_list = safe_target(stage, Path("Config", "Render.lsv"))
    write_lines(render_list, render_slugs)
    metadata["render_slugs"] = render_slugs
    write_metadata(Path(args.metadata), metadata)

    # Full-site GitHub renders keep non-cover URL rows (normalized). Cover/jpg
    # rows are never fetched via Tiggu: materialize from Resource when present,
    # otherwise drop so missing images like about_site.jpg are not wget'd.
    if render_all:
        for url_path in sorted((stage / "Config").glob("Url*.tsv")):
            lines = read_lines(url_path)
            if not lines:
                continue
            output = [lines[0]]
            for line in lines[1:]:
                normalized = normalize_url_row(parse_url_row(line))
                if is_article_cover_row(normalized):
                    cover_slug = url_row_article_slug(normalized)
                    if not cover_slug:
                        continue
                    cover = resolve_component_cover(stage, cover_slug)
                    if cover is None:
                        continue
                    # Preserve the Url row extension on the flat public path
                    # (photo.jpg, apple-touch-icon.png, article covers, etc.).
                    materialize_staged_cover(
                        stage, cover_slug, cover, flat_fields=normalized
                    )
                    continue
                output.append("\t".join(normalized))
            write_lines(url_path, output)

        # Tiggu only reads Config/Url.tsv. Translated home pages still need
        # /{lang}/menu fetched into public/{lang}/menu.html (open sidebar).
        default_url = safe_target(stage, Path("Config", "Url.tsv"))
        url_lines = read_lines(default_url)
        if not url_lines:
            raise RuntimeError("Default URL manifest is empty")
        seen_rows = set(url_lines[1:])
        for menu_slug in localized_menu_slugs(variants):
            language = menu_slug.split("/", 1)[0]
            row = "\t".join([f"{language}/", "menu", ""])
            if row not in seen_rows:
                url_lines.append(row)
                seen_rows.add(row)
        write_lines(default_url, url_lines)
        return

    if metadata.get("source_cover"):
        source_cover = safe_target(source, metadata["source_cover"])
        for variant in variants:
            materialize_staged_cover(
                stage, variant["public_slug"].lower(), source_cover
            )

    default_url = safe_target(stage, Path("Config", "Url.tsv"))
    default_lines = read_lines(default_url)
    if not default_lines:
        raise RuntimeError("Default URL manifest is empty")
    url_header = default_lines[0]
    url_lines = [url_header]
    seen_rows = set()

    def append_url_row(fields):
        normalized_line = "\t".join(fields)
        artifact = staged_url_artifact(stage, fields)
        if normalized_line in seen_rows or (artifact and artifact.is_file()):
            return
        url_lines.append(normalized_line)
        seen_rows.add(normalized_line)

    # Root assets must keep the leading empty Path field ("\tscript\tjs").
    append_url_row(["", "script", "js"])

    for variant in variants:
        source_url = safe_target(stage, variant.get("source_url", metadata["source_url"]))
        for line in read_lines(source_url)[1:]:
            fields = parse_url_row(line)
            if is_global_script_row(fields):
                continue
            article_slug = url_row_article_slug(fields)
            if article_slug != metadata["slug"]:
                continue
            normalized = normalize_url_row(fields, language=variant["language"])
            # Covers are materialized under public/<slug>/index.jpg — never wget.
            if is_article_cover_row(normalized):
                continue
            append_url_row(normalized)
    for menu_slug in localized_menu_slugs(variants):
        language = menu_slug.split("/", 1)[0]
        append_url_row([f"{language}/", "menu", ""])
    write_lines(default_url, url_lines)


def merge_firebase(path, slug, has_cover, add_shortcut=True):
    path = Path(path)
    with path.open(encoding="utf-8") as source:
        data = json.load(source)
    hosting = data.setdefault("hosting", {})
    redirects = hosting.setdefault("redirects", [])
    rewrites = hosting.setdefault("rewrites", [])

    if add_shortcut and "/" in slug:
        shortcut = "/" + slug.rsplit("/", 1)[-1]
        destination = "/" + slug
        existing = next((item for item in redirects if item.get("source") == shortcut), None)
        if existing and existing.get("destination") != destination:
            raise RuntimeError(
                f"Shortcut {shortcut!r} already points to {existing.get('destination')!r}"
            )
        if not existing:
            redirects.append(
                {"source": shortcut, "destination": destination, "type": 301}
            )

    required = [] if slug == "root" else [
        {"source": f"/{slug}.json", "destination": f"/{slug}/index.json"}
    ]
    if has_cover:
        required.append(
            {"source": f"/{slug}.jpg", "destination": f"/{slug}/index.jpg"}
        )
    for wanted in required:
        existing = next(
            (item for item in rewrites if item.get("source") == wanted["source"]),
            None,
        )
        if existing and existing.get("destination") != wanted["destination"]:
            raise RuntimeError(
                f"Rewrite {wanted['source']!r} already points to "
                f"{existing.get('destination')!r}"
            )
        if not existing:
            rewrites.append(wanted)

    with path.open("w", encoding="utf-8", newline="\n") as target:
        json.dump(data, target, ensure_ascii=False, indent=2)
        target.write("\n")


def validate_rendered_artifact(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    visible_text = re.sub(r"<[^>]*>", " ", text)
    diagnostic = PHP_DIAGNOSTIC.search(visible_text)
    if diagnostic:
        start = max(0, diagnostic.start() - 120)
        end = min(len(visible_text), diagnostic.end() + 280)
        context = re.sub(r"\s+", " ", visible_text[start:end]).strip()
        raise RuntimeError(
            f"Rendered artifact contains PHP diagnostic: {path}: {context}"
        )


def localized_menu_html_path(root, menu_slug):
    relative = Path(*menu_slug.split("/"))
    candidates = [root / relative / "index.html", root / f"{relative}.html"]
    for path in candidates:
        if path.is_file():
            return path
    raise RuntimeError(f"Rendered localized menu is missing for {menu_slug!r}")


def validate_localized_menu_artifact(path, language):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    validate_rendered_artifact(path)
    html_language = re.search(
        r"<html\b[^>]*\blang=(?:[\"']?)([^\s\"'>]+)", text, re.I
    )
    if not html_language or html_language.group(1).lower() != language:
        raise RuntimeError(
            f"Localized menu has the wrong HTML language for {language!r}: {path}"
        )
    main_wrapper = re.search(
        r"<div\b[^>]*\bid=(?:[\"']?)main-wrapper(?:[\"']?)[^>]*>", text, re.I
    )
    if not main_wrapper or not re.search(
        r"\bclass=(?:[\"'][^\"']*\bpml-open\b|[^\s>]*\bpml-open\b)",
        main_wrapper.group(0),
        re.I,
    ):
        raise RuntimeError(f"Localized menu is not rendered open: {path}")


def rendered_page_paths(root, slug):
    root = Path(root)
    if slug == "root":
        candidates = [(root / "index.html", root / "root.json")]
    else:
        relative = Path(*slug.split("/"))
        candidates = [
            (root / relative / "index.html", root / relative / "index.json"),
            (root / f"{relative}.html", root / f"{relative}.json"),
        ]
    for html_path, json_path in candidates:
        if html_path.is_file() and json_path.is_file():
            return html_path, json_path
    raise RuntimeError(f"Rendered affected page is missing for {slug!r}")


def public_page_paths(root, slug, stage_html, stage_json):
    root = Path(root)
    if slug == "root":
        return root / "index.html", root / "root.json"
    relative = Path(*slug.split("/"))
    if stage_html.name == "index.html":
        return root / relative / "index.html", root / relative / "index.json"
    return root / f"{relative}.html", root / f"{relative}.json"


def public_html_exists(root, slug):
    root = Path(root)
    if slug == "root":
        return (root / "index.html").is_file()
    relative = Path(*slug.split("/"))
    return any(
        path.is_file()
        for path in (root / relative / "index.html", root / f"{relative}.html")
    )


def rendered_asset_paths(html_path):
    text = Path(html_path).read_text(encoding="utf-8", errors="replace")
    assets = set()
    for match in ASSET_REFERENCE.finditer(text):
        reference = next(value for value in match.groups() if value is not None)
        if not reference.startswith("/") or reference.startswith("//"):
            continue
        path = urllib.parse.urlsplit(reference).path.lstrip("/")
        if Path(path).suffix.lower() in PUBLISHED_ASSET_EXTENSIONS:
            assets.add(path)
    return assets


def published_asset_exists(public_repo, public_root, asset_path):
    public_asset = safe_target(public_root, asset_path)
    if public_asset.is_file():
        return True
    firebase_path = Path(public_repo) / "firebase.json"
    with firebase_path.open(encoding="utf-8") as source:
        firebase = json.load(source)
    wanted_source = f"/{asset_path}"
    rewrite = next(
        (
            item
            for item in firebase.get("hosting", {}).get("rewrites", [])
            if item.get("source") == wanted_source
        ),
        None,
    )
    if not rewrite or not rewrite.get("destination"):
        return False
    destination = urllib.parse.urlsplit(rewrite["destination"]).path.lstrip("/")
    return safe_target(public_root, destination).is_file()


def publish_artifacts(args):
    metadata_path, metadata = read_metadata(args.metadata)
    slug = metadata["slug"]
    variants = article_variants(metadata)
    variants_by_public_slug = {
        variant["public_slug"]: variant for variant in variants
    }
    stage = Path(args.stage).resolve()
    public_repo = Path(args.public_repo).resolve()
    stage_public = stage / "public"
    public_root = public_repo / "public"
    public_paths = ["firebase.json", "public/sitemap.xml"]
    variant_hashes = {}
    referenced_assets = set()
    render_all = metadata.get("render_scope") == "all"
    english_slugs = set(metadata.get("queued_slugs") or [slug])
    has_translation_variant = any(
        variant["language"] != "en" for variant in variants
    )

    artifact_slugs = (
        metadata.get("render_slugs")
        if render_all or len(variants) > 1 or has_translation_variant
        else metadata.get("affected_slugs")
    )
    if not artifact_slugs:
        artifact_slugs = list(metadata.get("affected_slugs", [slug]))
        artifact_slugs.extend(
            variant["public_slug"]
            for variant in variants
            if variant["language"] != "en"
        )
    for artifact_slug in dict.fromkeys(artifact_slugs):
        stage_html, stage_json = rendered_page_paths(stage_public, artifact_slug)
        for artifact in (stage_html, stage_json):
            if artifact.stat().st_size == 0:
                raise RuntimeError(f"Required build artifact is empty: {artifact}")
            validate_rendered_artifact(artifact)

        referenced_assets.update(rendered_asset_paths(stage_html))
        public_html, public_json = public_page_paths(
            public_root, artifact_slug, stage_html, stage_json
        )
        public_html.parent.mkdir(parents=True, exist_ok=True)
        public_json.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stage_html, public_html)
        shutil.copy2(stage_json, public_json)
        public_paths.extend(
            [
                public_html.relative_to(public_repo).as_posix(),
                public_json.relative_to(public_repo).as_posix(),
            ]
        )

        variant = variants_by_public_slug.get(artifact_slug)
        if variant:
            with stage_json.open(encoding="utf-8") as source_file:
                built_json = json.load(source_file)
            if str(built_json.get("desc", "")) != str(
                variant.get("description", "")
            ):
                raise RuntimeError(
                    f"Built JSON description does not match Notion for "
                    f"{variant['language']}"
                )
            content = str(built_json.get("content", ""))
            for queued_slug in metadata.get("queued_slugs", []):
                if (
                    queued_slug
                    and queued_slug != slug
                    and not render_all
                    and queued_slug in content
                    and not public_html_exists(public_root, queued_slug)
                ):
                    raise RuntimeError(
                        f"Built article links to queued unpublished page "
                        f"{queued_slug!r}"
                    )
            variant_hashes[artifact_slug] = hashlib.sha256(
                stage_json.read_bytes()
            ).hexdigest()
        elif render_all:
            variant_hashes[artifact_slug] = hashlib.sha256(
                stage_json.read_bytes()
            ).hexdigest()

    for menu_slug in localized_menu_slugs(variants):
        language = menu_slug.split("/", 1)[0]
        stage_menu = localized_menu_html_path(stage_public, menu_slug)
        if stage_menu.stat().st_size == 0:
            raise RuntimeError(f"Required localized menu is empty: {stage_menu}")
        validate_localized_menu_artifact(stage_menu, language)
        relative = Path(*menu_slug.split("/"))
        public_menu = (
            public_root / relative / "index.html"
            if stage_menu.name == "index.html"
            else public_root / f"{relative}.html"
        )
        public_menu.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stage_menu, public_menu)
        public_paths.append(public_menu.relative_to(public_repo).as_posix())

    for asset_path in sorted(referenced_assets):
        staged_asset = safe_target(stage_public, asset_path)
        public_asset = safe_target(public_root, asset_path)
        if staged_asset.is_file():
            public_asset.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged_asset, public_asset)
            public_paths.append(public_asset.relative_to(public_repo).as_posix())
        elif not published_asset_exists(
            public_repo, public_root, asset_path
        ):
            raise RuntimeError(
                f"Rendered page references a missing local asset: /{asset_path}"
            )

    missing_variants = set(variants_by_public_slug) - set(variant_hashes)
    if missing_variants:
        raise RuntimeError(
            f"Rendered translation variants are missing: {sorted(missing_variants)}"
        )

    firebase_path = public_repo / "firebase.json"
    public_sitemap = public_repo / "public" / "sitemap.xml"

    if render_all:
        for artifact_slug in dict.fromkeys(artifact_slugs):
            stage_jpg = safe_target(
                stage, Path("public", *artifact_slug.split("/"), "index.jpg")
            )
            has_cover = stage_jpg.is_file() and stage_jpg.stat().st_size > 0
            if has_cover:
                public_jpg = safe_target(
                    public_repo,
                    Path("public", *artifact_slug.split("/"), "index.jpg"),
                )
                public_jpg.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(stage_jpg, public_jpg)
                public_paths.append(public_jpg.relative_to(public_repo).as_posix())
            merge_firebase(
                firebase_path,
                artifact_slug,
                has_cover,
                add_shortcut=artifact_slug in english_slugs,
            )
            add_sitemap_url(
                public_sitemap, sitemap_page_url(args.base_url, artifact_slug)
            )
    else:
        if metadata["has_cover"]:
            for variant in variants:
                public_slug = variant["public_slug"]
                stage_jpg = safe_target(
                    stage, Path("public", *public_slug.split("/"), "index.jpg")
                )
                if not stage_jpg.is_file() or stage_jpg.stat().st_size == 0:
                    raise RuntimeError(
                        f"Expected cover artifact is missing: {stage_jpg}"
                    )
                public_jpg = safe_target(
                    public_repo,
                    Path("public", *public_slug.split("/"), "index.jpg"),
                )
                public_jpg.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(stage_jpg, public_jpg)
                public_paths.append(public_jpg.relative_to(public_repo).as_posix())

        for variant in variants:
            public_slug = variant["public_slug"]
            merge_firebase(
                firebase_path,
                public_slug,
                metadata["has_cover"],
                add_shortcut=variant["language"] == "en",
            )
            add_sitemap_url(
                public_sitemap, sitemap_page_url(args.base_url, public_slug)
            )

    for variant in localized_home_variants(variants):
        merge_firebase_language_home(
            firebase_path, variant["language"], variant["public_slug"]
        )

    metadata["public_paths"] = list(dict.fromkeys(public_paths))
    metadata["variant_hashes"] = variant_hashes
    primary_public_slug = variants[0]["public_slug"]
    if primary_public_slug not in variant_hashes:
        raise RuntimeError(
            f"Rendered primary variant is missing: {primary_public_slug!r}"
        )
    metadata["json_sha256"] = variant_hashes[primary_public_slug]
    write_metadata(metadata_path, metadata)


def verify_live(args):
    _, metadata = read_metadata(args.metadata)
    expected_hashes = metadata.get("variant_hashes") or {
        article_variants(metadata)[0]["public_slug"]: metadata["json_sha256"]
    }
    for variant in localized_home_variants(article_variants(metadata)):
        expected_hashes[variant["language"]] = expected_hashes[variant["public_slug"]]
    deadline = time.monotonic() + args.timeout
    pending = dict(expected_hashes)
    errors = {public_slug: "no response" for public_slug in pending}

    while pending and time.monotonic() < deadline:
        for public_slug, expected_hash in list(pending.items()):
            url = f"{args.base_url.rstrip('/')}/{public_slug}.json"
            request = urllib.request.Request(
                f"{url}?ncms_verify={int(time.time())}",
                headers={
                    "Cache-Control": "no-cache",
                    "User-Agent": "ujnotes-ncms-publisher",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    live_hash = hashlib.sha256(response.read()).hexdigest()
                if live_hash == expected_hash:
                    print(f"Verified live article: {url}")
                    pending.pop(public_slug)
                    continue
                errors[public_slug] = (
                    f"hash {live_hash} did not match {expected_hash}"
                )
            except (urllib.error.URLError, TimeoutError) as error:
                errors[public_slug] = str(error)
        if pending:
            time.sleep(5)

    if pending:
        details = "; ".join(
            f"{public_slug}: {errors[public_slug]}"
            for public_slug in sorted(pending)
        )
        raise RuntimeError(f"Deployment did not match all variants: {details}")


def main(argv=None):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare-source")
    prepare.add_argument("--bundle", required=True)
    prepare.add_argument("--metadata", required=True)
    prepare.add_argument("--source", required=True)
    prepare.add_argument("--base-url", default="https://ujnotes.com")
    prepare.set_defaults(func=prepare_source)

    github = subparsers.add_parser("prepare-github")
    github.add_argument(
        "--slug",
        default="",
        help="Article slug to publish; * (or omit) to render all published articles",
    )
    github.add_argument("--metadata", required=True)
    github.add_argument("--source", required=True)
    github.add_argument("--base-url", default="https://ujnotes.com")
    github.set_defaults(func=prepare_github)

    stage = subparsers.add_parser("create-stage")
    stage.add_argument("--metadata", required=True)
    stage.add_argument("--source", required=True)
    stage.add_argument("--stage", required=True)
    stage.set_defaults(func=create_stage)

    publish = subparsers.add_parser("publish-artifacts")
    publish.add_argument("--metadata", required=True)
    publish.add_argument("--stage", required=True)
    publish.add_argument("--public-repo", required=True)
    publish.add_argument("--base-url", default="https://ujnotes.com")
    publish.set_defaults(func=publish_artifacts)

    verify = subparsers.add_parser("verify-live")
    verify.add_argument("--metadata", required=True)
    verify.add_argument("--base-url", default="https://ujnotes.com")
    verify.add_argument("--timeout", type=int, default=600)
    verify.set_defaults(func=verify_live)

    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"Publication error: {error}", file=sys.stderr)
        sys.exit(1)
