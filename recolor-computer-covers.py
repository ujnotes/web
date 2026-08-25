#!/usr/bin/env python3
"""Replace near-black logo ink with Ujnotes brand blue on Computer JPEGs."""
from __future__ import annotations

from pathlib import Path

from PIL import Image
import numpy as np

RESOURCE = Path(r"H:\Website\site\project\root\Resource\Computer")
BRAND = np.array([0x56, 0xB4, 0xD1], dtype=np.uint8)


def recolor(path: Path) -> bool:
    with Image.open(path) as im:
        rgb_im = im.convert("RGB")
    arr = np.asarray(rgb_im).copy()
    del rgb_im
    rgb = arr.astype(np.int16)
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    chroma = mx - mn
    luma = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]).astype(np.int16)

    fg = luma < 235
    if not np.any(fg):
        return False
    if chroma[fg].mean() >= 22:
        return False

    dark = luma <= 48
    if not np.any(dark):
        return False
    arr[dark] = BRAND
    tmp = path.with_name(path.stem + ".recolor-tmp.jpg")
    Image.fromarray(arr).save(tmp, "JPEG", quality=88, optimize=True)
    tmp.replace(path)
    return True


def main() -> int:
    changed = 0
    skipped = 0
    failed = 0
    for path in sorted(RESOURCE.rglob("*.jpg")):
        if "_uncited_backup" in path.parts:
            continue
        try:
            if recolor(path):
                changed += 1
                print(f"recolored {path.relative_to(RESOURCE)}")
            else:
                skipped += 1
        except OSError as exc:
            failed += 1
            print(f"failed {path.relative_to(RESOURCE)}: {exc}")
    print(f"recolored={changed} left_in_place={skipped} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
