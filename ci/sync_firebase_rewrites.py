#!/usr/bin/env python3
"""Synchronize canonical Firebase rewrites with baked index artifacts."""

import json
import sys
from pathlib import Path


EXTENSIONS = ("json", "jpg", "svg")


def canonical_rewrites(public_root: Path):
    rewrites = []
    for extension in EXTENSIONS:
        for artifact in sorted(public_root.rglob(f"index.{extension}")):
            relative = artifact.relative_to(public_root)
            slug = relative.parent.as_posix()
            if slug == ".":
                continue
            canonical = public_root / f"{slug}.{extension}"
            if canonical.is_file():
                continue
            rewrites.append(
                {
                    "source": f"/{slug}.{extension}",
                    "destination": f"/{slug}/index.{extension}",
                }
            )
    return rewrites


def synchronize(firebase_path: Path, public_root: Path):
    config = json.loads(firebase_path.read_text(encoding="utf-8"))
    hosting = config.setdefault("hosting", {})
    existing = hosting.setdefault("rewrites", [])

    generated = canonical_rewrites(public_root)
    generated_sources = {item["source"] for item in generated}
    preserved = [
        item
        for item in existing
        if item.get("source") not in generated_sources
        and item.get("regex")
        not in {
            r"^/(.+)\.json$",
            r"^/(.+)\.jpg$",
            r"^/(.+)\.svg$",
        }
    ]
    hosting["rewrites"] = generated + preserved
    firebase_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return len(generated)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: sync_firebase_rewrites.py FIREBASE_JSON PUBLIC_DIR")
    count = synchronize(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"Synchronized {count} canonical Firebase rewrites.")


if __name__ == "__main__":
    main()
