"""Regularize the exact F005 coincident-face Boolean without changing geometry.

The recovered top-right boss ends exactly on the Y=62.5 underside face of the
main body.  OpenCascade 7.9.3 requires a 1 µm Boolean classification tolerance
for this face-coincident union.  All identified feature dimensions remain
unchanged; only the Boolean classifier tolerance is specified.
"""

from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).with_name("top_parametric.py")
text = PATH.read_text(encoding="utf-8")

patched_marker = "F005_BOOLEAN_TOLERANCE = 1.0e-6"
if patched_marker in text:
    print(f"F005 Boolean tolerance already present in {PATH}")
    raise SystemExit(0)

old = '''    # F003-F005 — exact clipped cylindrical mounting bosses
    boss_solids = [
        _clipped_boss_solid(bx, bz, y0, y1)
        for _, bx, bz, y0, y1 in BOSSES
    ]
    for feature_index, boss_solid in enumerate(boss_solids, start=3):
        result = result.fuse(boss_solid)
        if len(result.solids()) != 1 or not result.is_valid:
            raise RuntimeError(f"F{feature_index:03d} boss union is invalid")
'''

new = '''    # F003-F005 — exact clipped cylindrical mounting bosses
    boss_solids = [
        _clipped_boss_solid(bx, bz, y0, y1)
        for _, bx, bz, y0, y1 in BOSSES
    ]

    # F003-F004 — ordinary exact unions
    for feature_index, boss_solid in enumerate(boss_solids[:2], start=3):
        result = result.fuse(boss_solid)
        if len(result.solids()) != 1 or not result.is_valid:
            raise RuntimeError(f"F{feature_index:03d} boss union is invalid")

    # F005 — exact nominal top-right boss, face-coincident at Y=62.5.
    # A 1 µm OCCT classifier tolerance regularizes the coincident-face Boolean;
    # the recovered boss radius, profile, position, and Y limits are unchanged.
    F005_BOOLEAN_TOLERANCE = 1.0e-6
    result = result.fuse(
        boss_solids[2],
        tol=F005_BOOLEAN_TOLERANCE,
    )
    if len(result.solids()) != 1 or not result.is_valid:
        raise RuntimeError("F005 boss union is invalid")
'''

count = text.count(old)
if count != 1:
    raise RuntimeError(f"Expected one F003-F005 source block, found {count}")

PATH.write_text(text.replace(old, new), encoding="utf-8")
print(f"Installed exact F005 coincident-face Boolean tolerance in {PATH}")
