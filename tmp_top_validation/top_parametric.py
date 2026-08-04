"""Parametric reconstruction of top.stl using build123d 0.11.1.

The model is generated only from analytic CAD features recovered from the
reference mesh: lines, circular arcs, extrusions, cylinders, a constant-radius
edge fillet, a stepped bore, an anti-rotation key, and a parametric text pocket.
The reference STL is never imported by this generator.

Coordinate convention
---------------------
The reference mesh uses Y as the thickness/extrusion axis. Custom workplanes
map local sketch (x, y) to global (X, Z), with the workplane normal along -Y.
All dimensions are millimetres.
"""

from __future__ import annotations

import math
from pathlib import Path

from build123d import (
    Align,
    BuildLine,
    BuildPart,
    BuildSketch,
    CenterArc,
    Circle,
    FontStyle,
    Line,
    Locations,
    Mode,
    Plane,
    Pos,
    Rectangle,
    Rot,
    Text,
    add,
    export_step,
    export_stl,
    extrude,
    fillet,
    make_face,
)

# Principal Y planes
Y_BOSS_LOW = 56.00000000
Y_TR_BOSS_LOW = 57.50000000
Y_COUNTERBORE_LOW = 61.00000000
Y_BODY_LOW = 62.50000000
Y_ENGRAVE_HIGH = 63.50000000
Y_COUNTERBORE_HIGH = 64.20000000
Y_FILLET_LOW = 65.20000000
Y_TOP = 67.20000000

# Outer profile
X_LEFT = -26.28930283
X_RIGHT_WALL = 17.57988739
Z_BOTTOM = -34.66747665
Z_TOP = 14.84700298
OUTER_RADIUS = 4.30000000

# Top-right blended boss/corner arc and straight-wall junction
TR_X = 13.60985870
TR_Z = 10.54700352
TR_STEP_Z = 12.002760887
TR_STEP_X = TR_X + math.sqrt(
    OUTER_RADIUS**2 - (TR_STEP_Z - TR_Z) ** 2
)
TR_ARC_START_DEG = math.degrees(
    math.atan2(TR_STEP_Z - TR_Z, TR_STEP_X - TR_X)
)

# Main opening
MAIN_X = -4.78930378
MAIN_Z = -10.63847256
COUNTERBORE_RADIUS = 21.50000000
THROUGH_RADIUS = 19.50000000
KEY_WIDTH = 2.00000000

# Mounting bosses / bores
BOSS_RADIUS = 4.30000000
MOUNT_BORE_RADIUS = 2.30000000
BOSSES = (
    ("bottom_left", -15.92011177, -30.46747725, 56.0, 62.5),
    ("bottom_right", 12.07988817, -30.46747725, 56.0, 62.5),
    ("top_right", 13.60985870, 10.54700352, 57.5, 62.5),
)
MOUNT_BORES = (
    ("bottom_left", -15.92011177, -30.46747725, 56.0, 62.5),
    ("bottom_right", 12.07988817, -30.46747725, 56.0, 62.5),
    ("top_right", 13.60985870, 10.54700352, 57.5, 64.2),
)

TOP_FILLET_RADIUS = 2.00000000

# Underside engraving
ENGRAVING_TEXT = "V4_17"
ENGRAVING_FONT = "Arial"
ENGRAVING_FONT_SIZE = 5.00000000
ENGRAVING_ROTATION_DEG = 25.00000000
ENGRAVING_U_MAX = -6.71720048
ENGRAVING_V_MAX = 19.18538800
ENGRAVING_DEPTH = 1.00000000


def xz_plane(y: float) -> Plane:
    """Plane whose local X/Y coordinates map to global X/Z at global Y=y."""
    return Plane(
        origin=(0.0, y, 0.0),
        x_dir=(1.0, 0.0, 0.0),
        z_dir=(0.0, -1.0, 0.0),
    )


def outer_profile_sketch():
    """Return the exact analytic outer profile as a build123d Sketch."""
    with BuildSketch() as profile:
        with BuildLine():
            CenterArc(
                (X_LEFT + OUTER_RADIUS, Z_BOTTOM + OUTER_RADIUS),
                OUTER_RADIUS,
                180.0,
                90.0,
            )
            Line(
                (X_LEFT + OUTER_RADIUS, Z_BOTTOM),
                (X_RIGHT_WALL - OUTER_RADIUS, Z_BOTTOM),
            )
            CenterArc(
                (X_RIGHT_WALL - OUTER_RADIUS, Z_BOTTOM + OUTER_RADIUS),
                OUTER_RADIUS,
                270.0,
                90.0,
            )
            Line(
                (X_RIGHT_WALL, Z_BOTTOM + OUTER_RADIUS),
                (X_RIGHT_WALL, TR_STEP_Z),
            )
            Line((X_RIGHT_WALL, TR_STEP_Z), (TR_STEP_X, TR_STEP_Z))
            CenterArc(
                (TR_X, TR_Z),
                OUTER_RADIUS,
                TR_ARC_START_DEG,
                90.0 - TR_ARC_START_DEG,
            )
            Line((TR_X, Z_TOP), (X_LEFT + OUTER_RADIUS, Z_TOP))
            CenterArc(
                (X_LEFT + OUTER_RADIUS, Z_TOP - OUTER_RADIUS),
                OUTER_RADIUS,
                90.0,
                90.0,
            )
            Line(
                (X_LEFT, Z_TOP - OUTER_RADIUS),
                (X_LEFT, Z_BOTTOM + OUTER_RADIUS),
            )
        make_face()
    return profile.sketch


def _add_clipped_boss(x: float, z: float, y0: float, y1: float) -> None:
    """Add a circular boss clipped by the exact outer boundary."""
    with BuildSketch(xz_plane(y0)):
        add(outer_profile_sketch())
        with Locations((x, z)):
            Circle(BOSS_RADIUS, mode=Mode.INTERSECT)
    extrude(amount=-(y1 - y0), mode=Mode.ADD)


def _subtract_cylindrical_bore(
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


def build_top():
    """Build and return the reconstructed top part as one parametric solid."""
    with BuildPart() as top:
        # F001 — main outer-profile extrusion
        with BuildSketch(xz_plane(Y_BODY_LOW)):
            add(outer_profile_sketch())
        extrude(amount=-(Y_TOP - Y_BODY_LOW))

        # F002 — R2 fillet on maximum-Y perimeter edges
        top_edges = [
            edge
            for edge in top.edges()
            if abs(edge.center().Y - Y_TOP) <= 1.0e-6
        ]
        if not top_edges:
            raise RuntimeError("Unable to identify Y=67.2 top perimeter edges")
        fillet(top_edges, radius=TOP_FILLET_RADIUS)

        # F003–F005 — clipped cylindrical mounting bosses
        for _, bx, bz, y0, y1 in BOSSES:
            _add_clipped_boss(bx, bz, y0, y1)

        # F006 — Ø43 counterbore from Y=61.0 through Y=64.2
        _subtract_cylindrical_bore(
            MAIN_X,
            MAIN_Z,
            COUNTERBORE_RADIUS,
            Y_COUNTERBORE_LOW,
            Y_COUNTERBORE_HIGH,
        )

        # F007 — 2 mm anti-rotation key retained in Ø43/Ø39 annulus
        with BuildSketch(xz_plane(Y_BODY_LOW)):
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

        # F008 — Ø39 upper through-bore from Y=64.2 to Y=67.2
        _subtract_cylindrical_bore(
            MAIN_X,
            MAIN_Z,
            THROUGH_RADIUS,
            Y_COUNTERBORE_HIGH,
            Y_TOP,
        )

        # F009–F011 — three Ø4.6 mounting bores
        for _, bx, bz, y0, y1 in MOUNT_BORES:
            _subtract_cylindrical_bore(
                bx,
                bz,
                MOUNT_BORE_RADIUS,
                y0,
                y1,
            )

        # F012 — 1 mm deep, +25° underside engraving
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
        with BuildSketch(xz_plane(Y_BODY_LOW)):
            add(text_profile)
        extrude(amount=-ENGRAVING_DEPTH, mode=Mode.SUBTRACT)

    result = top.part
    result.label = "top_parametric"
    return result


def export_model(output_dir: Path | str = Path("generated")) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model = build_top()
    step_path = output_dir / "top_parametric.step"
    stl_path = output_dir / "top_parametric.stl"
    export_step(model, step_path)
    export_stl(
        model,
        stl_path,
        tolerance=0.001,
        angular_tolerance=0.1,
        ascii_format=False,
    )
    return step_path, stl_path


if __name__ == "__main__":
    step, stl = export_model(Path(__file__).resolve().parent / "generated")
    print(f"STEP: {step}")
    print(f"STL : {stl}")
