from __future__ import annotations

import hashlib
import sys
from pathlib import Path

EXPECTED_BEFORE = "754f8937e6471f9a391182fe10357b4420f040560d3b960650c952ae3066d4b8"
EXPECTED_AFTER = "1b45d865f98e2fcbd23fc12eeda3c9f8783dff5ec6daf2f81f20a1ff70f22578"

OLD = """    ((79.48765417417098, -12.0),
     (77.48765417417098, -12.0),
     (77.48765417417098, -6.0),
     (79.48765417417098, -6.0),
     (79.48765417417098, 22.858184814453125)),
"""
NEW = """    ((79.48765417417098, -12.0),
     (77.48765417417098, -12.0),
     (77.48765417417098, -6.0),
     (79.48765417417098, -6.0)),
"""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    path = Path(sys.argv[1])
    before = digest(path)
    if before != EXPECTED_BEFORE:
        raise RuntimeError(f"unexpected pre-patch source SHA-256: {before}")
    text = path.read_text(encoding="utf-8")
    if text.count(OLD) != 1:
        raise RuntimeError("redundant collinear web point block not found exactly once")
    path.write_text(text.replace(OLD, NEW), encoding="utf-8")
    after = digest(path)
    if after != EXPECTED_AFTER:
        raise RuntimeError(f"unexpected post-patch source SHA-256: {after}")
    print(f"patched source SHA-256: {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
