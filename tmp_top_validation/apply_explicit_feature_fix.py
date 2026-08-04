"""Convert downstream Build123d operations to explicit robust operands.

This deterministic source transformation removes implicit pending-sketch state
and replaces the numerically fragile coincident 2-D boss intersection with its
exact 3-D equivalent: an analytic cylinder intersected by the analytic outer-
profile prism. It changes no dimensions, coordinates, radii, feature order, or
intended Boolean result.
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
    """Add an exact cylindrical boss clipped by the outer-profile prism.

    The 3-D Boolean is geometrically identical to the intended 2-D profile
    intersection but remains well-defined where a boss circle shares an exact
    coincident arc with the recovered outer profile.
    """
    with BuildPart() as cylinder_builder:
        with BuildSketch(xz_plane(y0)):
            with Locations((x, z)):
                Circle(BOSS_RADIUS)
        extrude(amount=-(y1 - y0))

    with BuildPart() as envelope_builder:
        with BuildSketch(xz_plane(y0)):
            add(outer_profile_sketch())
        extrude(amount=-(y1 - y0))

    clipped_boss = cylinder_builder.part & envelope_builder.part
    if not clipped_boss.solids():
        raise RuntimeError(f"Empty clipped boss solid at {(x, z, y0, y1)}")
    add(clipped_boss, mode=Mode.ADD)
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
print(f"Patched explicit robust feature operands in {PATH}")
