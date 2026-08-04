"""Replace the coincident top-right boss common with an exact analytic clip.

The recovered top-right boss circle is identical to the R4.3 corner circle,
which makes a generic coincident-surface OCCT common ill-conditioned.  The
actual retained profile is exactly the boss disk minus the lower-right region
beyond the identified right wall and below the identified horizontal ledge.
This script encodes that profile as one circle and one rectilinear L-shaped
clip; it does not replay mesh entities or sampled sections.
"""

from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).with_name("top_parametric.py")
text = PATH.read_text(encoding="utf-8")

if "Exact analytic L-clip for the coincident top-right boss" in text:
    print(f"Top-right boss analytic clip already present in {PATH}")
    raise SystemExit(0)

old = '''def _clipped_boss_solid(x: float, z: float, y0: float, y1: float):
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
'''

new = '''def _clipped_boss_solid(x: float, z: float, y0: float, y1: float):
    """Return an exact cylindrical boss clipped by the recovered perimeter."""
    with BuildSketch() as circle_profile:
        with Locations((x, z)):
            Circle(BOSS_RADIUS)

    is_top_right = (
        abs(x - TR_X) <= 1.0e-12
        and abs(z - TR_Z) <= 1.0e-12
    )

    if is_top_right:
        # Exact analytic L-clip for the coincident top-right boss.
        # Below the recovered ledge the part ends at X_RIGHT_WALL; above the
        # ledge the complete R4.3 disk is retained up to its circular boundary.
        q0 = (TR_X - BOSS_RADIUS, TR_Z - BOSS_RADIUS)
        q1 = (X_RIGHT_WALL, TR_Z - BOSS_RADIUS)
        q2 = (X_RIGHT_WALL, TR_STEP_Z)
        q3 = (TR_X + BOSS_RADIUS, TR_STEP_Z)
        q4 = (TR_X + BOSS_RADIUS, TR_Z + BOSS_RADIUS)
        q5 = (TR_X - BOSS_RADIUS, TR_Z + BOSS_RADIUS)
        with BuildSketch() as clip_profile:
            with BuildLine():
                Line(q0, q1)
                Line(q1, q2)
                Line(q2, q3)
                Line(q3, q4)
                Line(q4, q5)
                Line(q5, q0)
            make_face()
        clipped_profile = circle_profile.sketch & clip_profile.sketch
        if not clipped_profile.faces():
            raise RuntimeError("Empty exact top-right boss L-clip profile")
        clipped_boss = _solid_from_sketch(clipped_profile, y0, y1)
    else:
        cylinder = _solid_from_sketch(circle_profile.sketch, y0, y1)
        envelope = _solid_from_sketch(outer_profile_sketch(), y0, y1)
        clipped_boss = cylinder & envelope

    if not clipped_boss.solids():
        raise RuntimeError(f"Empty clipped boss solid at {(x, z, y0, y1)}")
    if len(clipped_boss.solids()) != 1 or not clipped_boss.is_valid:
        raise RuntimeError(f"Invalid clipped boss solid at {(x, z, y0, y1)}")
    return clipped_boss
'''

count = text.count(old)
if count != 1:
    raise RuntimeError(f"Expected one clipped-boss source block, found {count}")

PATH.write_text(text.replace(old, new), encoding="utf-8")
print(f"Patched exact top-right boss L-clip in {PATH}")
