"""Install the explicit F001-F012 solid Boolean feature tree.

The entire downstream section is replaced between two stable function markers,
so the transformation is deterministic, offset-safe, and repairs any prior
partial splice.  Every operand remains analytic and independently generated.
"""

from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).with_name("top_parametric.py")
text = PATH.read_text(encoding="utf-8")

section_start = text.index("def _subtract_cylindrical_bore(")
section_end = text.index("def export_model(", section_start)

replacement = '''def _subtract_cylindrical_bore(
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


def _engraving_profile_sketch():
    """Return the exact standalone parametric underside engraving sketch."""
    with BuildSketch() as raw_text:
        Text(
            ENGRAVING_TEXT,
            ENGRAVING_FONT_SIZE,
            font=ENGRAVING_FONT,
            font_style=FontStyle.REGULAR,
            align=(Align.MAX, Align.MAX),
        )
    return Rot(0.0, 0.0, ENGRAVING_ROTATION_DEG) * (
        Pos(ENGRAVING_U_MAX, ENGRAVING_V_MAX, 0.0) * raw_text.sketch
    )


def build_top():
    """Build the reconstructed top as an explicit ordered solid Boolean tree."""
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

text = text[:section_start] + replacement + text[section_end:]
PATH.write_text(text, encoding="utf-8")
print(f"Installed offset-safe explicit solid Boolean tree in {PATH}")
