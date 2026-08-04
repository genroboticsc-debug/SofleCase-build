"""Replace the parent BuildPart accumulator with an explicit solid tree.

Every F001-F012 operation becomes a regularized Boolean on one named result
solid.  All operands remain independently generated from the identified
analytic parameters.  This removes implicit builder state while preserving the
feature order, dimensions, surfaces, and Boolean intent.
"""

from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).with_name("top_parametric.py")
text = PATH.read_text(encoding="utf-8")

if "Explicit ordered solid Boolean feature tree" in text:
    print(f"Explicit solid Boolean tree already present in {PATH}")
    raise SystemExit(0)

old_bore = '''def _subtract_cylindrical_bore(
    x: float,
    z: float,
    radius: float,
    y0: float,
    y1: float,
) -> None:
    with BuildSketch(xz_plane(y0)) as bore_profile:
        with Locations((x, z)):
            Circle(radius)
    extrude(
        bore_profile.sketch,
        amount=-(y1 - y0),
        mode=Mode.SUBTRACT,
    )
'''
new_bore = '''def _subtract_cylindrical_bore(
    x: float,
    z: float,
    radius: float,
    y0: float,
    y1: float,
):
    """Return an independent exact cylindrical cutting solid."""
    with BuildSketch() as bore_profile:
        with Locations((x, z)):
            Circle(radius)
    return _solid_from_sketch(bore_profile.sketch, y0, y1)


def _anti_rotation_key_solid():
    """Return the exact 2 mm key retained in the Ø43/Ø39 annulus."""
    with BuildSketch() as key_profile:
        with Locations((MAIN_X, MAIN_Z)):
            Circle(COUNTERBORE_RADIUS)
            Circle(THROUGH_RADIUS, mode=Mode.SUBTRACT)
            Rectangle(
                KEY_WIDTH,
                COUNTERBORE_RADIUS,
                align=(Align.CENTER, Align.MIN),
                mode=Mode.INTERSECT,
            )
    if not key_profile.sketch.faces():
        raise RuntimeError("Empty anti-rotation key profile")
    return _solid_from_sketch(
        key_profile.sketch,
        Y_BODY_LOW,
        Y_COUNTERBORE_HIGH,
    )
'''

start = text.index("def build_top():")
end = text.index("\n\ndef export_model", start)
old_build = text[start:end]
new_build = '''def build_top():
    """Build the reconstructed top as an explicit ordered solid Boolean tree."""
    # Explicit ordered solid Boolean feature tree. Each operand is generated
    # independently from analytic parameters before being applied to `result`.

    # F001 — exact main rolling body: lower prism + R2 inset core + sweep
    main_rolling_body = _main_rolling_body()

    # F002 — exact clipped R4.3 top-right cap and toroidal R2 ledge blend
    top_right_clipped_cap = _top_right_clipped_cap()
    result = main_rolling_body.fuse(top_right_clipped_cap)
    if len(result.solids()) != 1 or not result.is_valid:
        raise RuntimeError("F001-F002 exact outer-body union is invalid")

    # F003-F005 — exact clipped cylindrical mounting bosses
    boss_solids = [
        _clipped_boss_solid(bx, bz, y0, y1)
        for _, bx, bz, y0, y1 in BOSSES
    ]
    for feature_index, boss_solid in enumerate(boss_solids, start=3):
        result = result.fuse(boss_solid)
        if len(result.solids()) != 1 or not result.is_valid:
            raise RuntimeError(f"F{feature_index:03d} boss union is invalid")

    # F006 — Ø43 counterbore from Y=61.0 through Y=64.2
    counterbore = _subtract_cylindrical_bore(
        MAIN_X,
        MAIN_Z,
        COUNTERBORE_RADIUS,
        Y_COUNTERBORE_LOW,
        Y_COUNTERBORE_HIGH,
    )
    result = result.cut(counterbore)

    # F007 — 2 mm anti-rotation key retained in Ø43/Ø39 annulus
    key_solid = _anti_rotation_key_solid()
    result = result.fuse(key_solid)

    # F008 — Ø39 upper through-bore from Y=64.2 to Y=67.2
    through_bore = _subtract_cylindrical_bore(
        MAIN_X,
        MAIN_Z,
        THROUGH_RADIUS,
        Y_COUNTERBORE_HIGH,
        Y_TOP,
    )
    result = result.cut(through_bore)

    # F009-F011 — three Ø4.6 mounting bores
    for feature_index, (_, bx, bz, y0, y1) in enumerate(
        MOUNT_BORES,
        start=9,
    ):
        mount_bore = _subtract_cylindrical_bore(
            bx,
            bz,
            MOUNT_BORE_RADIUS,
            y0,
            y1,
        )
        result = result.cut(mount_bore)
        if len(result.solids()) != 1 or not result.is_valid:
            raise RuntimeError(f"F{feature_index:03d} mounting-bore cut is invalid")

    # F012 — 1 mm deep, +25° underside engraving
    engraving_solid = _solid_from_sketch(
        _engraving_profile_sketch(),
        Y_BODY_LOW,
        Y_ENGRAVE_HIGH,
    )
    result = result.cut(engraving_solid)

    if len(result.solids()) != 1 or not result.is_valid:
        raise RuntimeError("Final explicit feature-tree solid is invalid")
    result.label = "top_parametric"
    return result
'''

count = text.count(old_bore)
if count != 1:
    raise RuntimeError(f"Expected one bore helper block, found {count}")
text = text.replace(old_bore, new_bore)
text = text[:start] + new_build + text[end:]
PATH.write_text(text, encoding="utf-8")
print(f"Patched explicit ordered solid Boolean tree in {PATH}")
