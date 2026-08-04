#!/usr/bin/env python3
"""Validate Ujnotes sitemap routes before and after deployment."""

import argparse
import csv
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

METADATA_PREAMBLE_FIELDS = ("Language", "Label", "Title", "Description")


def sitemap_page_url(base_url, public_slug):
    base = base_url.rstrip("/")
    return base if public_slug == "root" else f"{base}/{public_slug}"


def sitemap_urls(path):
    root = ET.parse(path).getroot()
    urls = [(node.text or "").strip() for node in root.findall(".//{*}loc") if (node.text or "").strip()]
    duplicates = sorted({url for url in urls if urls.count(url) > 1})
    if duplicates:
        raise RuntimeError(f"Duplicate sitemap URLs: {duplicates}")
    return urls


def expected_translation_urls(path, base_url, slugs=None):
    expected = set()
    wanted = {slug.strip().strip("/") for slug in (slugs or []) if slug}
    with Path(path).open(encoding="utf-8", newline="") as source:
        rows = csv.reader(source, delimiter="\t")
        header = next(rows, None)
        if not header or header[0] != "TranslationGroup":
            raise RuntimeError(f"Invalid translation manifest header: {path}")
        for row in rows:
            if not row:
                continue
            slug = row[0].strip().strip("/")
            if wanted and slug not in wanted:
                continue
            for index, language in enumerate(header[1:], start=1):
                status = row[index].strip().lower() if index < len(row) else ""
                if status == "published":
                    public_slug = slug if language == "en" else f"{language}/{slug}"
                    expected.add(sitemap_page_url(base_url, public_slug))
    return expected


def has_metadata_preamble(content):
    sample = str(content or "")[:5000].lower()
    positions = [sample.find(f"{field.lower()}:") for field in METADATA_PREAMBLE_FIELDS]
    return all(position >= 0 for position in positions) and positions == sorted(positions)


def relative_slug(url, base_url):
    parsed = urllib.parse.urlsplit(url)
    base = urllib.parse.urlsplit(base_url)
    if parsed.netloc != base.netloc or parsed.scheme not in ("http", "https"):
        raise RuntimeError(f"Sitemap URL is outside {base_url}: {url}")
    return parsed.path.strip("/")


def local_page_paths(public_root, slug):
    root = Path(public_root)
    if not slug:
        return root / "index.html", root / "root.json"
    relative = Path(*slug.split("/"))
    candidates = (
        (root / relative / "index.html", root / relative / "index.json"),
        (root / f"{relative}.html", root / f"{relative}.json"),
    )
    return next(
        ((html, data) for html, data in candidates if html.is_file() and data.is_file()),
        candidates[0],
    )


def firebase_routes(path):
    if not path:
        return {}, set()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    hosting = data.get("hosting", {})
    rewrites = {item.get("source"): item.get("destination") for item in hosting.get("rewrites", []) if item.get("source") and item.get("destination")}
    redirects = {item.get("source") for item in hosting.get("redirects", []) if item.get("source") and item.get("destination")}
    return rewrites, redirects


def validate_local(urls, base_url, public_root, firebase_path=None):
    errors = []
    rewrites, redirects = firebase_routes(firebase_path)
    for url in urls:
        try:
            slug = relative_slug(url, base_url)
        except RuntimeError as error:
            errors.append(str(error))
            continue
        if f"/{slug}" in redirects:
            continue
        html_path, json_path = local_page_paths(public_root, slug)
        for artifact in (html_path, json_path):
            if not artifact.is_file() or artifact.stat().st_size == 0:
                errors.append(f"Missing sitemap artifact for {url}: {artifact}")
        if html_path.is_file() and has_metadata_preamble(html_path.read_text(encoding="utf-8", errors="replace")):
            errors.append(f"Translation metadata leaked into HTML: {url}")
        if json_path.is_file():
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
                if has_metadata_preamble(payload.get("content", "")):
                    errors.append(f"Translation metadata leaked into JSON: {url}.json")
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                errors.append(f"Invalid JSON for {url}: {error}")
        flat_json = Path(public_root, f"{Path(*slug.split('/'))}.json") if slug else json_path
        if firebase_path and slug and not flat_json.is_file():
            source = f"/{slug}.json"
            destination = rewrites.get(source)
            if not destination:
                errors.append(f"Missing Firebase JSON rewrite: {source}")
            elif not Path(public_root).joinpath(destination.lstrip("/")).is_file():
                errors.append(f"Firebase rewrite target is missing: {destination}")
    return errors


def fetch(url, timeout):
    separator = "&" if "?" in url else "?"
    request = urllib.request.Request(f"{url}{separator}sitemap_audit=1", headers={"Cache-Control": "no-cache", "User-Agent": "ujnotes-sitemap-audit"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read(), response.headers.get_content_charset()


def validate_live_url(url, timeout, skip_json=False):
    errors = []
    try:
        status, html, charset = fetch(url, timeout)
        if status != 200:
            errors.append(f"HTTP {status}: {url}")
        elif has_metadata_preamble(html.decode(charset or "utf-8", errors="replace")):
            errors.append(f"Translation metadata leaked into live HTML: {url}")
    except (urllib.error.URLError, TimeoutError) as error:
        errors.append(f"Live request failed for {url}: {error}")
    if skip_json:
        return errors
    json_url = (
        f"{url.rstrip('/')}/root.json"
        if not urllib.parse.urlsplit(url).path.strip("/")
        else f"{url}.json"
    )
    try:
        status, body, charset = fetch(json_url, timeout)
        if status != 200:
            errors.append(f"HTTP {status}: {json_url}")
        else:
            payload = json.loads(body.decode(charset or "utf-8"))
            if has_metadata_preamble(payload.get("content", "")):
                errors.append(f"Translation metadata leaked into live JSON: {json_url}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        errors.append(f"Live JSON request failed for {json_url}: {error}")
    return errors


def validate_live(urls, timeout, workers, base_url, redirects=()):
    errors = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(
                validate_live_url,
                url,
                timeout,
                f"/{relative_slug(url, base_url)}" in redirects,
            )
            for url in urls
        ]
        for future in as_completed(futures):
            errors.extend(future.result())
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--sitemap", required=True)
    parser.add_argument("--base-url", default="https://ujnotes.com")
    parser.add_argument("--translations")
    parser.add_argument(
        "--slug",
        action="append",
        default=[],
        help="Only require these TranslationGroup slugs in the sitemap",
    )
    parser.add_argument("--public-root")
    parser.add_argument("--firebase")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    urls = sitemap_urls(args.sitemap)
    errors = []
    if args.translations:
        missing = expected_translation_urls(
            args.translations, args.base_url, args.slug
        ) - set(urls)
        errors.extend(
            f"Published translation missing from sitemap: {url}"
            for url in sorted(missing)
        )
    if args.public_root:
        errors.extend(validate_local(urls, args.base_url, args.public_root, args.firebase))
    if args.live:
        _, redirects = firebase_routes(args.firebase)
        errors.extend(validate_live(urls, args.timeout, args.workers, args.base_url, redirects))
    if errors:
        for error in errors:
            print(f"Sitemap validation error: {error}", file=sys.stderr)
        return 1
    print(f"Validated {len(urls)} sitemap URLs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
