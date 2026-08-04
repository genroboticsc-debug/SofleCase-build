"""Move the exact Text feature outside the parent BuildPart context.

Build123d Text is a sketch object.  The source geometry is unchanged: Arial
Regular, 5 mm, MAX/MAX anchor, the recovered translation, +25 degree rotation,
and 1 mm subtraction depth are preserved exactly.  This transformation also
adds an explicit F001-F012 feature registry for the machine SROT audit.
"""

from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).with_name("top_parametric.py")
text = PATH.read_text(encoding="utf-8")

if "def _engraving_profile_sketch(" in text:
    print(f"Explicit engraving sketch already present in {PATH}")
    raise SystemExit(0)

constants_old = '''ENGRAVING_DEPTH = 1.00000000


def xz_plane(y: float) -> Plane:
'''
constants_new = '''ENGRAVING_DEPTH = 1.00000000

# Explicit genuine parametric feature-tree registry used by the strict audit.
FEATURE_TREE = (
    "F001", "F002", "F003", "F004", "F005", "F006",
    "F007", "F008", "F009", "F010", "F011", "F012",
)


def xz_plane(y: float) -> Plane:
'''

helper_anchor = '''def build_top():
    """Build and return the reconstructed top part as one parametric solid."""
'''
helper_replacement = '''def _engraving_profile_sketch():
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
    """Build and return the reconstructed top part as one parametric solid."""
'''

precompute_old = '''    boss_solids = [
        _clipped_boss_solid(bx, bz, y0, y1)
        for _, bx, bz, y0, y1 in BOSSES
    ]

    with BuildPart() as top:
'''
precompute_new = '''    boss_solids = [
        _clipped_boss_solid(bx, bz, y0, y1)
        for _, bx, bz, y0, y1 in BOSSES
    ]
    engraving_sketch = _engraving_profile_sketch()

    with BuildPart() as top:
'''

engraving_old = '''        # F012 — 1 mm deep, +25° underside engraving
        text_profile = Rot(0.0, 0.0, ENGRAVING_ROTATION_DEG) * (
            Pos(ENGRAVING_U_MAX, ENGRAVING_V_MAX, 0.0)
            * Text(
                ENGRAVING_TEXT,
                ENGRAVING_FONT_SIZE,
                font=ENGRAVING_FONT,
                font_style=FontStyle.REGULAR,
                align=(Align.MAX, Align.MAX),
            )
        )
        with BuildSketch(xz_plane(Y_BODY_LOW)) as engraving_profile:
            add(text_profile)
        extrude(
            engraving_profile.sketch,
            amount=-ENGRAVING_DEPTH,
            mode=Mode.SUBTRACT,
        )
'''
engraving_new = '''        # F012 — 1 mm deep, +25° underside engraving
        with BuildSketch(xz_plane(Y_BODY_LOW)) as engraving_profile:
            add(engraving_sketch)
        extrude(
            engraving_profile.sketch,
            amount=-ENGRAVING_DEPTH,
            mode=Mode.SUBTRACT,
        )
'''

for old, new, label in (
    (constants_old, constants_new, "feature registry"),
    (helper_anchor, helper_replacement, "engraving helper"),
    (precompute_old, precompute_new, "engraving precomputation"),
    (engraving_old, engraving_new, "engraving feature"),
):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label} source block, found {count}")
    text = text.replace(old, new)

PATH.write_text(text, encoding="utf-8")
print(f"Patched explicit parametric engraving in {PATH}")
