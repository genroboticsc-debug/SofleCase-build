"""Convert downstream Build123d operations to explicit sketch operands.

This is a deterministic source transformation used once by CI to remove
implicit pending-sketch state across helper-function boundaries.  It changes
no dimensions, coordinates, radii, feature order, or Boolean modes.
"""

from pathlib import Path

PATH = Path(__file__).with_name("top_parametric.py")
text = PATH.read_text(encoding="utf-8")

replacements = [
    (
'''def _add_clipped_boss(x: float, z: float, y0: float, y1: float) -> None:
    """Add a circular boss clipped by the exact outer boundary."""
    with BuildSketch(xz_plane(y0)):
        add(outer_profile_sketch())
        with Locations((x, z)):
            Circle(BOSS_RADIUS, mode=Mode.INTERSECT)
    extrude(amount=-(y1 - y0), mode=Mode.ADD)
''',
'''def _add_clipped_boss(x: float, z: float, y0: float, y1: float) -> None:
    """Add a circular boss clipped by the exact outer boundary."""
    with BuildSketch(xz_plane(y0)) as boss_profile:
        add(outer_profile_sketch())
        with Locations((x, z)):
            Circle(BOSS_RADIUS, mode=Mode.INTERSECT)
    if not boss_profile.sketch.faces():
        raise RuntimeError(f"Empty clipped boss profile at {(x, z, y0, y1)}")
    extrude(
        boss_profile.sketch,
        amount=-(y1 - y0),
        mode=Mode.ADD,
    )
''',
    ),
    (
'''def _subtract_cylindrical_bore(
    x: float,
    z: float,
    radius: float,
    y0: float,
    y1: float,
) -> None:
    with BuildSketch(xz_plane(y0)):
        with Locations((x, z)):
            Circle(radius)
    extrude(amount=-(y1 - y0), mode=Mode.SUBTRACT)
''',
'''def _subtract_cylindrical_bore(
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
''',
    ),
    (
'''        with BuildSketch(xz_plane(Y_BODY_LOW)):
            with Locations((MAIN_X, MAIN_Z)):
                Circle(COUNTERBORE_RADIUS)
                Circle(THROUGH_RADIUS, mode=Mode.SUBTRACT)
                Rectangle(
                    KEY_WIDTH,
                    COUNTERBORE_RADIUS,
                    align=(Align.CENTER, Align.MIN),
                    mode=Mode.INTERSECT,
                )
        extrude(
            amount=-(Y_COUNTERBORE_HIGH - Y_BODY_LOW),
            mode=Mode.ADD,
        )
''',
'''        with BuildSketch(xz_plane(Y_BODY_LOW)) as key_profile:
            with Locations((MAIN_X, MAIN_Z)):
                Circle(COUNTERBORE_RADIUS)
                Circle(THROUGH_RADIUS, mode=Mode.SUBTRACT)
                Rectangle(
                    KEY_WIDTH,
                    COUNTERBORE_RADIUS,
                    align=(Align.CENTER, Align.MIN),
                    mode=Mode.INTERSECT,
                )
        extrude(
            key_profile.sketch,
            amount=-(Y_COUNTERBORE_HIGH - Y_BODY_LOW),
            mode=Mode.ADD,
        )
''',
    ),
    (
'''        with BuildSketch(xz_plane(Y_BODY_LOW)):
            add(text_profile)
        extrude(amount=-ENGRAVING_DEPTH, mode=Mode.SUBTRACT)
''',
'''        with BuildSketch(xz_plane(Y_BODY_LOW)) as engraving_profile:
            add(text_profile)
        extrude(
            engraving_profile.sketch,
            amount=-ENGRAVING_DEPTH,
            mode=Mode.SUBTRACT,
        )
''',
    ),
]

for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Expected exactly one source block, found {count}: {old.splitlines()[0]}"
        )
    text = text.replace(old, new)

PATH.write_text(text, encoding="utf-8")
print(f"Patched explicit feature operands in {PATH}")
