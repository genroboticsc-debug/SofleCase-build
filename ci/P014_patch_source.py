from __future__ import annotations

import hashlib
import sys
from pathlib import Path

EXPECTED_BEFORE = "754f8937e6471f9a391182fe10357b4420f040560d3b960650c952ae3066d4b8"
EXPECTED_AFTER = "4751c60624373d51a80eca8f47faca0a30cc21e969850cc1706a39068f8608d9"

REDUNDANT_OLD = """    ((79.48765417417098, -12.0),
     (77.48765417417098, -12.0),
     (77.48765417417098, -6.0),
     (79.48765417417098, -6.0),
     (79.48765417417098, 22.858184814453125)),
"""
REDUNDANT_NEW = """    ((79.48765417417098, -12.0),
     (77.48765417417098, -12.0),
     (77.48765417417098, -6.0),
     (79.48765417417098, -6.0)),
"""
OFFSET_OLD = "    inner_core = outer.offset_2d(-(width + depth))\n"
OFFSET_NEW = "    inner_core = cavity.offset_2d(-depth)\n"
FUSE_OLD = """    for index, addition in enumerate(additions, start=1):
        fused = profile.fuse(addition)
        if len(fused.faces()) != 1:
            raise RuntimeError(f"support profile addition {index} did not join")
        profile = fused.faces()[0]
"""
FUSE_NEW = """    reference_float32_ulp = 2.0 ** -17
    for index, addition in enumerate(additions, start=1):
        fused = profile.fuse(addition)
        if len(fused.faces()) != 1:
            # The reference STL stores coordinates as float32.  Preserve both
            # identified feature boundaries and join only within one exact ULP
            # at the model's 64–128 mm coordinate scale.
            fused = profile.fuse(addition, tol=reference_float32_ulp)
        if len(fused.faces()) != 1:
            raise RuntimeError(f"support profile addition {index} did not join")
        profile = fused.faces()[0]
"""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"{label} block not found exactly once")
    return text.replace(old, new)


def main() -> int:
    path = Path(sys.argv[1])
    before = digest(path)
    if before != EXPECTED_BEFORE:
        raise RuntimeError(f"unexpected pre-patch source SHA-256: {before}")
    text = path.read_text(encoding="utf-8")
    text = replace_once(text, REDUNDANT_OLD, REDUNDANT_NEW, "redundant collinear web point")
    text = replace_once(text, OFFSET_OLD, OFFSET_NEW, "sequential exact cavity offset")
    text = replace_once(text, FUSE_OLD, FUSE_NEW, "float32-ULP fuzzy feature fuse")
    path.write_text(text, encoding="utf-8")
    after = digest(path)
    if after != EXPECTED_AFTER:
        raise RuntimeError(f"unexpected post-patch source SHA-256: {after}")
    print(f"patched source SHA-256: {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
