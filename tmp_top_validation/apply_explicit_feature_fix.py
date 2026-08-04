"""Apply deterministic SROT-compliant feature-tree corrections.

The transformation makes every downstream Boolean operand explicit and builds
all clipped boss solids before entering the parent BuildPart context.  This
avoids Build123d pending-sketch/context contamination while preserving the
identified analytic geometry, dimensions, feature order, and Boolean intent.
No reference mesh, sampled profile, cached B-Rep, or serialized topology is
introduced.
"""

from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).with_name("top_parametric.py")
text = PATH.read_text(encoding="utf-8")

if "def _clipped_boss_solid(" in text:
    print(f"Explicit robust feature operands already present in {PATH}")
    raise SystemExit(0)

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
'''def _clipped_boss_solid(x: float, z: float, y0: float, y1: float):
    """Return an exact cylindrical boss clipped by the outer-profile prism.

    The cylinder and envelope are generated as independent analytic solids
    before the parent feature tree is opened.  Their 3-D regularized common is
    geometrically equivalent to the intended profile intersection and remains
    isolated from BuildPart pending-object state.
    """
    with BuildSketch() as circle_profile:
        with Locations((x, z)):
            Circle(BOSS_RADIUS)

    cylinder = _solid_from_sketch(circle_profile.sketch, y0, y1)
    envelope = _solid_from_sketch(outer_profile_sketch(), y0, y1)
    clipped_boss = cylinder & envelope
    if not clipped_boss.solids():
        raise RuntimeError(f"Empty clipped boss solid at {(x, z, y0, y1)}")
    if len(clipped_boss.solids()) != 1 or not clipped_boss.is_valid:
        raise RuntimeError(f"Invalid clipped boss solid at {(x, z, y0, y1)}")
    return clipped_boss
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
'''def build_top():
    """Build and return the reconstructed top part as one parametric solid."""
    with BuildPart() as top:
''',
'''def build_top():
    """Build and return the reconstructed top part as one parametric solid."""
    # Build independent F003-F005 operands before opening the parent context.
    # This is still a genuine parametric feature tree: each operand is an
    # identified analytic cylinder clipped by the identified analytic envelope.
    boss_solids = [
        _clipped_boss_solid(bx, bz, y0, y1)
        for _, bx, bz, y0, y1 in BOSSES
    ]

    with BuildPart() as top:
''',
    ),
    (
'''        # F003–F005 — clipped cylindrical mounting bosses
        for _, bx, bz, y0, y1 in BOSSES:
            _add_clipped_boss(bx, bz, y0, y1)
''',
'''        # F003–F005 — exact independently generated clipped boss operands
        for boss_solid in boss_solids:
            add(boss_solid, mode=Mode.ADD)
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
            f"Expected exactly one source block, found {count}: "
            f"{old.splitlines()[0]}"
        )
    text = text.replace(old, new)

PATH.write_text(text, encoding="utf-8")
print(f"Patched explicit robust feature operands in {PATH}")
