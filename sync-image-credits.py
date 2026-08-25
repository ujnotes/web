#!/usr/bin/env python3
"""Sync Computer/Philosophy covers and Image_credits.csv."""
from __future__ import annotations

import csv
import importlib.util
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(r"H:\Website")
SITE_RESOURCE = ROOT / "site" / "project" / "root" / "Resource"
CONFIG = ROOT / "site" / "project" / "config"
ID_TSV = CONFIG / "ID.tsv"
URL_TSV = CONFIG / "Url.tsv"
OLD_CSV = CONFIG / "Computer_image_credits.csv"
NEW_CSV = CONFIG / "Image_credits.csv"
NOTES_SVG = SITE_RESOURCE / "Computer" / "notes.svg"
COMPUTER = SITE_RESOURCE / "Computer"
PHILOSOPHY = SITE_RESOURCE / "World" / "Philosophy"
THIS_MONTH = datetime(2026, 8, 1)

spec = importlib.util.spec_from_file_location(
    "replace_computer_covers", ROOT / "project" / "replace-computer-covers.py"
)
mod = importlib.util.module_from_spec(spec)
sys.modules["replace_computer_covers"] = mod
spec.loader.exec_module(mod)

CSV_FIELDS = [
    "relative_path",
    "slug",
    "title",
    "category",
    "status",
    "repository",
    "file_page_url",
    "source_url",
    "author",
    "license",
    "license_url",
    "attribution_required",
    "restrictions",
    "brand_source",
    "notes",
]

NOTES_RECORD = {
    "repository": "Ujnotes",
    "file_page_url": "",
    "source_url": "",
    "author": "Ujnotes",
    "license": "CC0 1.0",
    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
    "attribution_required": "no",
    "restrictions": "",
    "brand_source": "",
    "notes": "generic notes icon",
}


def load_id_slugs() -> list[tuple[str, str]]:
    out = []
    for line in ID_TSV.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        slug, title = parts[1], parts[2]
        out.append((slug, title))
    return out


def title_of(slug: str, fallback: str = "") -> str:
    return fallback or slug.rsplit("/", 1)[-1].replace("_", " ").title()


def category_of(slug: str) -> str:
    bits = slug.split("/")
    if len(bits) >= 2:
        return bits[1].replace("_", " ").title()
    return ""


def relative_of(path: Path) -> str:
    try:
        return path.relative_to(SITE_RESOURCE).as_posix()
    except ValueError:
        return path.as_posix()


def record(**kwargs) -> dict:
    row = {k: "" for k in CSV_FIELDS}
    row.update(kwargs)
    return row


def delete_recent_extras(keep_paths: set[str]) -> int:
    removed = 0
    backup = COMPUTER / "_uncited_backup"
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
        removed += 1
        print("removed _uncited_backup")
    algo = COMPUTER / "Technology" / "Algorithms"
    if algo.is_dir():
        for p in algo.glob("index-*.jpg"):
            p.unlink()
            removed += 1
            print(f"removed {relative_of(p)}")
    keep_l = {k.lower() for k in keep_paths}
    for p in COMPUTER.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in {".jpg", ".png", ".gif", ".svg"}:
            continue
        if p.name.lower() == "notes.svg" and p.parent == COMPUTER:
            continue
        rel = relative_of(p)
        if rel.lower() in keep_l:
            continue
        # Authored diagrams and older listing/game covers stay.
        if p.suffix.lower() == ".svg" and p.parent == COMPUTER:
            continue
        if p.suffix.lower() == ".css":
            continue
        rel_posix = rel.lower()
        if rel_posix.startswith("computer/game/"):
            continue
        if p.name.lower() in {"index.jpg"} and p.parent in {
            COMPUTER,
            COMPUTER / "OS",
            COMPUTER / "Program",
            COMPUTER / "Programming",
            COMPUTER / "Technology",
            COMPUTER / "Game",
        }:
            continue
        # Numbered algorithm frames already handled; drop other uncredited extras
        # only when they are numbered stills or sit in folders created for the
        # CSV scrape but are not themselves CSV rows.
        if p.stem.lower().startswith("index-"):
            p.unlink()
            removed += 1
            print(f"removed {rel}")
    return removed


NESTED_DENY = {
    "buffer",
    "icon",
    "cnn",
    "note",
    "license",
    "shortcut",
    "solid",
    "msi",
    "mac",
    "alchemy",
}


def pick_nested_icon(last: str, title: str, icons: dict) -> dict | None:
    if not icons:
        return None
    if last.lower() in NESTED_DENY:
        return None
    override = mod.SIMPLE_SLUG_OVERRIDE.get(last, "AUTO")
    if override is None:
        return None
    if override != "AUTO":
        return mod.pick_simple_icon(last, title, icons)
    key = "".join(ch for ch in last.lower() if ch.isalnum())
    if key in icons:
        return mod.pick_simple_icon(last, title, icons)
    return None


def info_from_csv_row(row: dict) -> dict | None:
    url = row.get("source_url") or ""
    if not url:
        return None
    return {
        "url": url,
        "original_url": url,
        "mime": "image/svg+xml" if url.lower().endswith(".svg") else "",
        "author": row.get("author") or "",
        "license": row.get("license") or "",
        "license_url": row.get("license_url") or "",
        "file_page": row.get("file_page_url") or "",
        "restrictions": row.get("restrictions") or "",
        "attribution_required": (row.get("attribution_required") or "").lower() in ("yes", "true", "1"),
        "brand_source": row.get("brand_source") or "",
        "repository": row.get("repository") or "",
        "colorize": (row.get("repository") or "") == "Simple Icons",
    }


_HTTP_CACHE: dict[str, bytes] = {}


def http_bytes_cached(url: str) -> bytes:
    if url not in _HTTP_CACHE:
        _HTTP_CACHE[url] = mod.http_bytes(url)
    return _HTTP_CACHE[url]


def place_cover(slug: str, info: dict, tmp: Path, colorize: bool | None = None) -> tuple[Path, str] | None:
    dest_dir = mod.slug_to_resource_dir(slug, SITE_RESOURCE)
    url = info["url"]
    mime = info.get("mime") or ""
    do_color = info.get("colorize") if colorize is None else colorize
    try:
        raw = http_bytes_cached(url)
    except Exception as exc:
        print(f"download failed {slug}: {exc}")
        return None
    ext = ".svg" if mod.is_svg_source(url, mime) else ".bin"
    if "png" in mime or url.lower().endswith(".png"):
        ext = ".png"
    elif "jpeg" in mime or url.lower().endswith((".jpg", ".jpeg")):
        ext = ".jpg"
    elif "gif" in mime or url.lower().endswith(".gif"):
        ext = ".gif"
    src = tmp / (slug.replace("/", "_") + ext)
    src.write_bytes(raw)
    if ext == ".svg":
        text = raw.decode("utf-8", errors="replace")
        path = mod.save_svg_cover(dest_dir, text, bool(do_color))
        return path, "svg"
    dest = dest_dir / "index.jpg"
    try:
        mod.to_jpeg(src, dest)
    except Exception as exc:
        print(f"convert failed {slug}: {exc}")
        return None
    svg = dest_dir / "index.svg"
    if svg.exists():
        svg.unlink()
    return dest, "jpg"


def notes_cover(slug: str) -> Path:
    dest_dir = mod.slug_to_resource_dir(slug, SITE_RESOURCE)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "index.svg"
    shutil.copyfile(NOTES_SVG, dest)
    jpg = dest_dir / "index.jpg"
    if jpg.exists():
        jpg.unlink()
    return dest


def philosophy_rows() -> list[dict]:
    rows = []
    for path in sorted(PHILOSOPHY.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".jpg", ".png", ".svg"}:
            continue
        rel = relative_of(path)
        parts = path.relative_to(SITE_RESOURCE / "World" / "Philosophy").parts
        if path.name.lower().startswith("index"):
            slug_bits = ["world", "philosophy", *[p.lower() for p in parts[:-1]]]
        else:
            stem = path.stem.lower()
            slug_bits = ["world", "philosophy", *[p.lower() for p in parts[:-1]], stem]
        slug = "/".join(b for b in slug_bits if b)
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        title = slug.rsplit("/", 1)[-1].replace("_", " ").replace("-", " ").title()
        if path.suffix.lower() == ".svg":
            rows.append(
                record(
                    relative_path=rel,
                    slug=slug,
                    title=title,
                    category="Philosophy",
                    status="replaced",
                    repository="Ujnotes",
                    author="Ujnotes",
                    license="CC0 1.0",
                    license_url="https://creativecommons.org/publicdomain/zero/1.0/",
                    attribution_required="no",
                    notes="site diagram",
                )
            )
            continue
        if mtime < THIS_MONTH:
            rows.append(
                record(
                    relative_path=rel,
                    slug=slug,
                    title=title,
                    category="Philosophy",
                    status="replaced",
                    repository="Pexels",
                    file_page_url="https://www.pexels.com/",
                    source_url="https://www.pexels.com/",
                    author="Pexels",
                    license="Pexels License",
                    license_url="https://www.pexels.com/license/",
                    attribution_required="yes",
                    notes="credited to Pexels for images from before August 2026",
                )
            )
        else:
            rows.append(
                record(
                    relative_path=rel,
                    slug=slug,
                    title=title,
                    category="Philosophy",
                    status="uncredited",
                    notes="added this month; not attributed to Pexels",
                )
            )
    return rows


def main() -> int:
    old_rows = []
    if OLD_CSV.exists():
        with OLD_CSV.open(encoding="utf-8", newline="") as fh:
            old_rows = list(csv.DictReader(fh))
    elif NEW_CSV.exists():
        with NEW_CSV.open(encoding="utf-8", newline="") as fh:
            old_rows = list(csv.DictReader(fh))

    csv_by_slug = {r["slug"].lower(): r for r in old_rows if r.get("slug")}
    keep_paths = {r.get("relative_path", "") for r in old_rows if r.get("status") == "replaced"}
    deleted = delete_recent_extras(keep_paths)
    print(f"removed extras={deleted}")

    icons = {}
    try:
        icons = mod.load_simple_icons()
        print(f"Loaded {len(icons)} Simple Icons")
    except Exception as exc:
        print(f"Simple Icons catalog failed: {exc}")

    tmp = Path(tempfile.mkdtemp(prefix="ujnotes-covers-"))
    rows: list[dict] = []
    seen = set()

    def add_row(row: dict) -> None:
        slug = row["slug"].lower()
        if slug in seen:
            return
        seen.add(slug)
        rows.append(row)

    # Existing credited first-child covers from CSV: keep SVG when the source is SVG.
    for old in old_rows:
        slug = (old.get("slug") or "").lower()
        if not slug.startswith("computer/") or old.get("status") != "replaced":
            continue
        info = info_from_csv_row(old)
        if info is None:
            continue
        placed = place_cover(slug, info, tmp)
        if placed is None:
            add_row(old)
            continue
        path, ext = placed
        old = dict(old)
        old["relative_path"] = relative_of(path)
        old["status"] = "replaced"
        add_row(old)
        mod.upsert_url_tsv(URL_TSV, slug, ext)
        print(f"kept {ext:3} {slug}")

    slugs = load_id_slugs()
    for slug, title in slugs:
        if not slug.startswith("computer/") or slug.startswith("computer/game"):
            continue
        last = slug.rsplit("/", 1)[-1].lower()
        if last in {"notes", "ide_notes"} or title.strip().lower() == "notes":
            path = notes_cover(slug)
            add_row(
                record(
                    relative_path=relative_of(path),
                    slug=slug,
                    title=title or "Notes",
                    category=category_of(slug),
                    status="replaced",
                    **NOTES_RECORD,
                )
            )
            mod.upsert_url_tsv(URL_TSV, slug, "svg")
            print(f"notes svg {slug}")
            continue
        if slug.lower() in seen:
            continue
        # Nested last child: use a logo when Simple Icons has that leaf name.
        if slug.count("/") < 3:
            continue
        info = None
        try:
            info = pick_nested_icon(last, title or last, icons)
        except Exception:
            info = None
        if info is None:
            continue
        placed = place_cover(slug, info, tmp, colorize=True)
        if placed is None:
            continue
        path, ext = placed
        add_row(
            record(
                relative_path=relative_of(path),
                slug=slug,
                title=title or title_of(slug),
                category=category_of(slug),
                status="replaced",
                repository="Simple Icons",
                file_page_url=info.get("file_page", ""),
                source_url=info.get("original_url") or info.get("url", ""),
                author=info.get("author", ""),
                license=info.get("license", ""),
                license_url=info.get("license_url", ""),
                attribution_required="no",
                restrictions=info.get("restrictions", ""),
                brand_source=info.get("brand_source", ""),
                notes="nested last-child logo",
            )
        )
        mod.upsert_url_tsv(URL_TSV, slug, ext)
        print(f"nested {ext:3} {slug}")

    for prow in philosophy_rows():
        add_row(prow)
        print(f"philosophy {prow['status']:11} {prow['slug']}")

    NEW_CSV.parent.mkdir(parents=True, exist_ok=True)
    with NEW_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    if OLD_CSV.exists() and OLD_CSV != NEW_CSV:
        OLD_CSV.unlink()
        print(f"replaced {OLD_CSV.name} with {NEW_CSV.name}")
    print(f"Wrote {NEW_CSV} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
