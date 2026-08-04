"""Cut every disconnected face of the recovered F012 engraving sketch.

Build123d Text("V4_17") produces five disconnected parametric sketch faces.
The previous generic helper selected faces()[0], cutting only one glyph.  This
migration preserves all recovered text parameters and cuts every face as one
ordered F012 feature.
"""

from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).with_name("top_parametric.py")
text = PATH.read_text(encoding="utf-8")

marker = "F012_ENGRAVING_FACE_COUNT = 5"
if marker in text:
    print(f"Complete F012 engraving already present in {PATH}")
    raise SystemExit(0)

old = '''    # F012 — 1 mm deep, +25° underside engraving
    engraving_solid = _solid_from_sketch(
        _engraving_profile_sketch(),
        Y_BODY_LOW,
        Y_ENGRAVE_HIGH,
    )
    result = result.cut(engraving_solid)
'''

new = '''    # F012 — complete five-face, 1 mm deep, +25° underside engraving
    F012_ENGRAVING_FACE_COUNT = 5
    with BuildSketch(xz_plane(Y_BODY_LOW)) as engraving_placed:
        add(_engraving_profile_sketch())
    engraving_faces = list(engraving_placed.sketch.faces())
    if len(engraving_faces) != F012_ENGRAVING_FACE_COUNT:
        raise RuntimeError(
            "F012 engraving face count mismatch: "
            f"expected {F012_ENGRAVING_FACE_COUNT}, got {len(engraving_faces)}"
        )
    for engraving_face in engraving_faces:
        engraving_cutter = extrude(
            engraving_face,
            amount=-(Y_ENGRAVE_HIGH - Y_BODY_LOW),
        )
        result = result.cut(engraving_cutter)
        if len(result.solids()) != 1 or not result.is_valid:
            raise RuntimeError("F012 engraving cut is invalid")
'''

count = text.count(old)
if count != 1:
    raise RuntimeError(f"Expected one legacy F012 block, found {count}")

PATH.write_text(text.replace(old, new), encoding="utf-8")
print(f"Installed complete five-face F012 engraving in {PATH}")
