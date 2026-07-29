#!/usr/bin/env python3
"""Cross-platform helpers for the guarded Notion publication workflow."""

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


SAFE_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]*$")
PHP_DIAGNOSTIC = re.compile(
    r"\b(?:PHP\s+)?(?:warning|fatal error|parse error|notice|deprecated)\s*:",
    re.IGNORECASE,
)


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


def read_metadata(path):
    metadata_path = Path(path).resolve()
    with metadata_path.open(encoding="utf-8") as source:
        metadata = json.load(source)
    if not metadata.get("no_work"):
        validate_slug(metadata.get("slug", ""))
        if not metadata.get("page_id"):
            raise RuntimeError("NCMS metadata does not contain page_id")
    return metadata_path, metadata


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
    """Resolve a relative path without changing or duplicating the source tree."""
    root = Path(root).resolve()
    current = root
    for requested_part in Path(relative).parts:
        if not current.is_dir():
            return None
        matches = [
            child
            for child in current.iterdir()
            if child.name.casefold() == requested_part.casefold()
        ]
        if not matches:
            return None
        exact = next((match for match in matches if match.name == requested_part), None)
        if exact is not None:
            current = exact
        elif len(matches) > 1:
            resolved_matches = {match.resolve() for match in matches}
            if len(resolved_matches) > 1:
                raise RuntimeError(
                    f"Ambiguous case-insensitive path below {current}: {requested_part}"
                )
            current = matches[0]
        else:
            current = matches[0]
    return current


def parent_slug(slug):
    if slug == "root":
        return None
    if "/" not in slug:
        return "root"
    return slug.rsplit("/", 1)[0]


def affected_navigation_slugs(path, slug):
    """Return the article, its ancestors, and adjacent siblings."""
    rows = []
    for line in read_lines(path)[1:]:
        fields = line.split("\t")
        if len(fields) >= 2 and fields[0] == "published":
            rows.append(fields[1])

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
        raise RuntimeError(f"URL file is empty: {path}")
    output = [lines[0]]
    for line in lines[1:]:
        first = line.split("\t", 1)[0].replace("\\", "/").rstrip("/")
        if first != slug:
            output.append(line)
    if has_cover:
        output.append(f"{slug}/\tindex\tjpg")
    write_lines(path, output)


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


def prepare_source(args):
    metadata_path, metadata = read_metadata(args.metadata)
    if metadata.get("no_work"):
        return
    slug = metadata["slug"]
    language = metadata.get("language", "en")
    bundle = Path(args.bundle).resolve()
    source = Path(args.source).resolve()

    generated_component = safe_target(bundle, metadata["component"])
    component_parts = ["Root", "HTML", "Component"]
    if language != "en":
        component_parts.append(language)
    component_parts.extend(slug.split("/"))
    component_parts.append("index.php")
    source_component = safe_target(source, Path(*component_parts))
    source_component.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(generated_component, source_component)

    cover_relative = Path("Root", "Resource", *slug.split("/"), "index.jpg")
    cover = resolve_case_insensitive(source, cover_relative)
    component_text = source_component.read_text(encoding="utf-8")
    cover_is_file = cover is not None and cover.is_file()
    has_cover = cover_is_file or "Component_cover.php" in component_text
    if cover_is_file and "Component_cover.php" not in component_text:
        alt = metadata.get("title", "").replace("\\", "\\\\").replace("'", "\\'")
        markup = f"<?php $alt='{alt}'; require('../HTML/Fragment/Component_cover.php') ?>"
        source_component.write_text(
            markup + "\n\n" + component_text,
            encoding="utf-8",
            newline="\n",
        )

    suffix = "" if language == "en" else f"_{language}"
    bundle_id = safe_target(bundle, Path("Config", f"ID{suffix}.tsv"))
    source_id = safe_target(source, Path("Config", f"ID{suffix}.tsv"))
    _, generated_row = find_article_row(bundle_id, slug)
    # NCMS renders queued pages with Status=publish. The source repository is
    # the durable post-publication state, so never commit that transient status:
    # navigation only exposes rows marked published.
    merged_row = merge_id_row(source_id, slug, generated_row, status="published")
    source_url = safe_target(source, Path("Config", f"Url{suffix}.tsv"))
    merge_url_row(source_url, slug, has_cover)

    source_sitemap = safe_target(source, Path("Root", "Site", "SiteMap.xml"))
    add_sitemap_url(source_sitemap, f"{args.base_url.rstrip('/')}/{slug}")
    affected_slugs = affected_navigation_slugs(source_id, slug)

    metadata.update(
        {
            "has_cover": has_cover,
            "source_cover": (
                cover.relative_to(source).as_posix() if cover_is_file else None
            ),
            "source_component": source_component.relative_to(source).as_posix(),
            "source_id": source_id.relative_to(source).as_posix(),
            "source_url": source_url.relative_to(source).as_posix(),
            "source_sitemap": source_sitemap.relative_to(source).as_posix(),
            "article_row": merged_row,
            "affected_slugs": affected_slugs,
        }
    )
    write_metadata(metadata_path, metadata)


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

    source_id = safe_target(stage, metadata["source_id"])
    id_lines = read_lines(source_id)
    affected = set(metadata.get("affected_slugs", [metadata["slug"]]))
    selected_id_lines = [id_lines[0]]
    for line in id_lines[1:]:
        fields = line.split("\t")
        if len(fields) >= 2 and fields[1] in affected:
            selected_id_lines.append(line)
    write_lines(source_id, selected_id_lines)

    # A cover may use legacy title casing in the source repository. Place it
    # directly at its public build destination before selecting download URLs.
    if metadata.get("source_cover"):
        source_cover = safe_target(source, metadata["source_cover"])
        staged_cover = safe_target(
            stage, Path("public", *metadata["slug"].split("/"), "index.jpg")
        )
        staged_cover.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_cover, staged_cover)

    source_url = safe_target(stage, metadata["source_url"])
    url_header = read_lines(source_url)[0]
    url_lines = [url_header]
    for line in read_lines(source_url)[1:]:
        fields = line.split("	")
        row_path = fields[0].replace("\\", "/").rstrip("/")
        is_script = len(fields) >= 3 and fields[1:3] == ["script", "js"]
        selected = row_path == metadata["slug"] or (not row_path and is_script)
        artifact = staged_url_artifact(stage, fields)
        if selected and not (artifact and artifact.is_file()):
            url_lines.append(line)
    write_lines(source_url, url_lines)

def merge_firebase(path, slug, has_cover):
    path = Path(path)
    with path.open(encoding="utf-8") as source:
        data = json.load(source)
    hosting = data.setdefault("hosting", {})
    redirects = hosting.setdefault("redirects", [])
    rewrites = hosting.setdefault("rewrites", [])

    if "/" in slug:
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

    required = [{"source": f"/{slug}.json", "destination": f"/{slug}/index.json"}]
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
    if PHP_DIAGNOSTIC.search(visible_text):
        raise RuntimeError(f"Rendered artifact contains PHP diagnostic: {path}")


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


def publish_artifacts(args):
    metadata_path, metadata = read_metadata(args.metadata)
    slug = metadata["slug"]
    stage = Path(args.stage).resolve()
    public_repo = Path(args.public_repo).resolve()
    stage_public = stage / "public"
    public_root = public_repo / "public"
    public_paths = ["firebase.json", "public/sitemap.xml"]
    article_json = None

    for affected_slug in metadata.get("affected_slugs", [slug]):
        stage_html, stage_json = rendered_page_paths(stage_public, affected_slug)
        for artifact in (stage_html, stage_json):
            if artifact.stat().st_size == 0:
                raise RuntimeError(f"Required build artifact is empty: {artifact}")
            validate_rendered_artifact(artifact)

        public_html, public_json = public_page_paths(
            public_root, affected_slug, stage_html, stage_json
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
        if affected_slug == slug:
            article_json = stage_json

    if article_json is None:
        raise RuntimeError(f"Published article was not in affected pages: {slug}")
    with article_json.open(encoding="utf-8") as source:
        built_json = json.load(source)
    if str(built_json.get("desc", "")) != str(metadata.get("description", "")):
        raise RuntimeError("Built JSON description does not match Notion")
    content = str(built_json.get("content", ""))
    for queued_slug in metadata.get("queued_slugs", []):
        if queued_slug and queued_slug != slug and queued_slug in content:
            raise RuntimeError(
                f"Built article links to queued unpublished page {queued_slug!r}"
            )

    stage_jpg = safe_target(stage, Path("public", *slug.split("/"), "index.jpg"))
    if metadata["has_cover"]:
        if not stage_jpg.is_file() or stage_jpg.stat().st_size == 0:
            raise RuntimeError(f"Expected cover artifact is missing: {stage_jpg}")
        public_jpg = safe_target(
            public_repo, Path("public", *slug.split("/"), "index.jpg")
        )
        public_jpg.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stage_jpg, public_jpg)
        public_paths.append(public_jpg.relative_to(public_repo).as_posix())

    firebase_path = public_repo / "firebase.json"
    merge_firebase(firebase_path, slug, metadata["has_cover"])
    public_sitemap = public_repo / "public" / "sitemap.xml"
    add_sitemap_url(public_sitemap, f"{args.base_url.rstrip('/')}/{slug}")

    metadata["public_paths"] = list(dict.fromkeys(public_paths))
    metadata["json_sha256"] = hashlib.sha256(article_json.read_bytes()).hexdigest()
    write_metadata(metadata_path, metadata)


def verify_live(args):
    _, metadata = read_metadata(args.metadata)
    slug = metadata["slug"]
    expected_hash = metadata["json_sha256"]
    url = f"{args.base_url.rstrip('/')}/{slug}.json"
    deadline = time.monotonic() + args.timeout
    last_error = "no response"

    while time.monotonic() < deadline:
        request = urllib.request.Request(
            f"{url}?ncms_verify={int(time.time())}",
            headers={"Cache-Control": "no-cache", "User-Agent": "ujnotes-ncms-publisher"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                live_hash = hashlib.sha256(response.read()).hexdigest()
            if live_hash == expected_hash:
                print(f"Verified live article: {url}")
                return
            last_error = f"hash {live_hash} did not match {expected_hash}"
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = str(error)
        time.sleep(5)
    raise RuntimeError(f"Deployment did not match {url}: {last_error}")


def main(argv=None):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare-source")
    prepare.add_argument("--bundle", required=True)
    prepare.add_argument("--metadata", required=True)
    prepare.add_argument("--source", required=True)
    prepare.add_argument("--base-url", default="https://ujnotes.com")
    prepare.set_defaults(func=prepare_source)

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
