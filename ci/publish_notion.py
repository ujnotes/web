#!/usr/bin/env python3
"""Cross-platform helpers for the guarded Notion publication workflow."""

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
from pathlib import Path


SAFE_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]*$")


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


def find_article_row(path, slug):
    lines = read_lines(path)
    if not lines:
        raise RuntimeError(f"TSV is empty: {path}")
    for line in lines[1:]:
        fields = line.split("\t")
        if len(fields) >= 2 and fields[1] == slug:
            return lines[0], line
    raise RuntimeError(f"No generated ID row for {slug!r} in {path}")


def merge_id_row(path, slug, new_row):
    lines = read_lines(path)
    if not lines:
        raise RuntimeError(f"ID file is empty: {path}")
    header = lines[0].split("\t")
    fields = new_row.split("\t")
    fields.extend([""] * (len(header) - len(fields)))
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

    cover = safe_target(source, Path("Root", "Resource", *slug.split("/"), "index.jpg"))
    component_text = source_component.read_text(encoding="utf-8")
    has_cover = cover.is_file() or "Component_cover.php" in component_text
    if cover.is_file() and "Component_cover.php" not in component_text:
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
    merged_row = merge_id_row(source_id, slug, generated_row)
    source_url = safe_target(source, Path("Config", f"Url{suffix}.tsv"))
    merge_url_row(source_url, slug, has_cover)

    source_sitemap = safe_target(source, Path("Root", "Site", "SiteMap.xml"))
    add_sitemap_url(source_sitemap, f"{args.base_url.rstrip('/')}/{slug}")

    metadata.update(
        {
            "has_cover": has_cover,
            "source_component": source_component.relative_to(source).as_posix(),
            "source_id": source_id.relative_to(source).as_posix(),
            "source_url": source_url.relative_to(source).as_posix(),
            "source_sitemap": source_sitemap.relative_to(source).as_posix(),
            "article_row": merged_row,
        }
    )
    write_metadata(metadata_path, metadata)


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

    source_id = safe_target(stage, metadata["source_id"])
    id_header = read_lines(source_id)[0]
    write_lines(source_id, [id_header, metadata["article_row"]])

    source_url = safe_target(stage, metadata["source_url"])
    url_header = read_lines(source_url)[0]
    url_lines = [url_header]
    for line in read_lines(source_url)[1:]:
        fields = line.split("\t")
        row_path = fields[0].replace("\\", "/").rstrip("/")
        is_script = len(fields) >= 3 and fields[1:3] == ["script", "js"]
        if row_path == metadata["slug"] or (not row_path and is_script):
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


def publish_artifacts(args):
    metadata_path, metadata = read_metadata(args.metadata)
    slug = metadata["slug"]
    stage = Path(args.stage).resolve()
    public_repo = Path(args.public_repo).resolve()
    stage_target = safe_target(stage, Path("public", *slug.split("/")))
    public_target = safe_target(public_repo, Path("public", *slug.split("/")))

    stage_html = stage_target / "index.html"
    stage_json = stage_target / "index.json"
    for artifact in (stage_html, stage_json):
        if not artifact.is_file() or artifact.stat().st_size == 0:
            raise RuntimeError(f"Required build artifact is missing or empty: {artifact}")

    with stage_json.open(encoding="utf-8") as source:
        built_json = json.load(source)
    if str(built_json.get("desc", "")) != str(metadata.get("description", "")):
        raise RuntimeError("Built JSON description does not match Notion")
    content = str(built_json.get("content", ""))
    for queued_slug in metadata.get("queued_slugs", []):
        if queued_slug and queued_slug != slug and queued_slug in content:
            raise RuntimeError(
                f"Built article links to queued unpublished page {queued_slug!r}"
            )

    public_target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(stage_html, public_target / "index.html")
    shutil.copy2(stage_json, public_target / "index.json")
    stage_jpg = stage_target / "index.jpg"
    if metadata["has_cover"]:
        if not stage_jpg.is_file() or stage_jpg.stat().st_size == 0:
            raise RuntimeError(f"Expected cover artifact is missing: {stage_jpg}")
        shutil.copy2(stage_jpg, public_target / "index.jpg")

    firebase_path = public_repo / "firebase.json"
    merge_firebase(firebase_path, slug, metadata["has_cover"])
    public_sitemap = public_repo / "public" / "sitemap.xml"
    add_sitemap_url(public_sitemap, f"{args.base_url.rstrip('/')}/{slug}")

    metadata["public_paths"] = [
        "firebase.json",
        "public/sitemap.xml",
        f"public/{slug}/index.html",
        f"public/{slug}/index.json",
    ]
    if metadata["has_cover"]:
        metadata["public_paths"].append(f"public/{slug}/index.jpg")
    metadata["json_sha256"] = hashlib.sha256(stage_json.read_bytes()).hexdigest()
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
