"""Parametric reconstruction of top.stl using build123d 0.11.1.

The model is generated only from analytic CAD features recovered from the
reference mesh: lines, circular arcs, extrusions, cylinders, an exact rolling-
body R2 blend with a clipped toroidal cap, a stepped bore, an anti-rotation key,
and a parametric text pocket. The reference STL is never imported by this
generator.

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
    Circle,
    FontStyle,
    Kind,
    Line,
    Locations,
    Mode,
    Plane,
    Pos,
    Rectangle,
    Rot,
    Text,
    ThreePointArc,
    Transition,
    Vector,
    add,
    export_step,
    export_stl,
    extrude,
    fillet,
    make_face,
    offset,
    sweep,
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
TR_JUNCTION_EDGE_LENGTH = TR_STEP_X - X_RIGHT_WALL

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


def _circle_point(
    center_x: float,
    center_z: float,
    radius: float,
    angle_degrees: float,
) -> tuple[float, float]:
    """Exact analytic point on an identified circular feature."""
    angle = math.radians(angle_degrees)
    return (
        center_x + radius * math.cos(angle),
        center_z + radius * math.sin(angle),
    )


def outer_profile_sketch():
    """Return the exact analytic outer profile as a build123d Sketch.

    Every adjacent edge is constructed from the same endpoint object. Circular
    edges are true OpenCascade arcs defined by their identified centres,
    radii, endpoints, and an exact analytic midpoint; no sampled polyline or
    fitted spline is used.
    """
    radius = OUTER_RADIUS

    bottom_left_center = (X_LEFT + radius, Z_BOTTOM + radius)
    bottom_right_center = (X_RIGHT_WALL - radius, Z_BOTTOM + radius)
    top_left_center = (X_LEFT + radius, Z_TOP - radius)

    p0 = (X_LEFT, Z_BOTTOM + radius)
    p1 = (X_LEFT + radius, Z_BOTTOM)
    p2 = (X_RIGHT_WALL - radius, Z_BOTTOM)
    p3 = (X_RIGHT_WALL, Z_BOTTOM + radius)
    p4 = (X_RIGHT_WALL, TR_STEP_Z)
    p5 = (TR_STEP_X, TR_STEP_Z)
    p6 = (TR_X, Z_TOP)
    p7 = (X_LEFT + radius, Z_TOP)
    p8 = (X_LEFT, Z_TOP - radius)

    mid_bottom_left = _circle_point(
        bottom_left_center[0], bottom_left_center[1], radius, 225.0
    )
    mid_bottom_right = _circle_point(
        bottom_right_center[0], bottom_right_center[1], radius, 315.0
    )
    mid_top_right = _circle_point(
        TR_X,
        TR_Z,
        radius,
        (TR_ARC_START_DEG + 90.0) / 2.0,
    )
    mid_top_left = _circle_point(
        top_left_center[0], top_left_center[1], radius, 135.0
    )

    with BuildSketch() as profile:
        with BuildLine():
            ThreePointArc(p0, mid_bottom_left, p1)
            Line(p1, p2)
            ThreePointArc(p2, mid_bottom_right, p3)
            Line(p3, p4)
            Line(p4, p5)
            ThreePointArc(p5, mid_top_right, p6)
            Line(p6, p7)
            ThreePointArc(p7, mid_top_left, p8)
            Line(p8, p0)
        make_face()
    return profile.sketch


def _placed_face(sketch, y: float):
    """Place a recovered XZ sketch on an exact global-Y plane."""
    with BuildSketch(xz_plane(y)) as placed:
        add(sketch)
    return placed.sketch.faces()[0]


def _solid_from_sketch(sketch, y0: float, y1: float):
    """Extrude an identified XZ profile between two exact Y planes."""
    return extrude(_placed_face(sketch, y0), amount=-(y1 - y0))


def _outward_quarter_disk(path, inset_face):
    """Return the exact R2 quarter-disk section for the top rolling blend."""
    start = Vector(path.position_at(0.0))
    tangent = Vector(path.tangent_at(0.0)).normalized()
    global_up = Vector(0.0, 1.0, 0.0)
    left = Vector(-tangent.Z, 0.0, tangent.X).normalized()
    toward_profile = Vector(inset_face.center()) - start
    inward = left if left.dot(toward_profile) >= 0.0 else -left
    outward = -inward
    section_plane = Plane(
        origin=start,
        x_dir=outward,
        z_dir=outward.cross(global_up),
    )
    with BuildSketch(section_plane) as section:
        Circle(TOP_FILLET_RADIUS)
        Rectangle(
            TOP_FILLET_RADIUS,
            TOP_FILLET_RADIUS,
            align=(Align.MIN, Align.MIN),
            mode=Mode.INTERSECT,
        )
    return section.sketch.faces()[0]


def _main_rolling_body():
    """Build the exact R2 rolling-body blend for the complete outer profile.

    The body is decomposed into its exact spring-plane prism, exact R2 inward
    offset core, and a true quarter-disk sweep. Straight profile segments
    generate cylinders, circular segments generate tori, and ROUND transition
    patches resolve the identified profile vertices without sampled lofts.
    """
    outer = outer_profile_sketch()
    inset = offset(
        outer,
        amount=-TOP_FILLET_RADIUS,
        kind=Kind.ARC,
        min_edge_length=1.0e-7,
    )
    inset_face = _placed_face(inset, Y_FILLET_LOW)
    inset_path = inset_face.outer_wire()
    rim = sweep(
        sections=_outward_quarter_disk(inset_path, inset_face),
        path=inset_path,
        transition=Transition.ROUND,
        is_frenet=False,
    )
    lower = _solid_from_sketch(outer, Y_BODY_LOW, Y_FILLET_LOW)
    core = _solid_from_sketch(inset, Y_FILLET_LOW, Y_TOP)
    return lower.fuse(core, rim)


def _top_right_clipped_cap():
    """Build the exact local cap that preserves the 0.076052190114 mm ledge.

    The reference identifies an independently rolled R4.3 circular cap clipped
    by the Z=12.002760887 plane. Its R2 toroidal roll intersects the adjacent
    R2 right-wall cylinder and consumes the ledge continuously before Y=67.2.
    """
    with BuildPart() as cap_builder:
        with BuildSketch(xz_plane(Y_BODY_LOW)):
            with Locations((TR_X, TR_Z)):
                Circle(OUTER_RADIUS)
        extrude(amount=-(Y_TOP - Y_BODY_LOW))
        top_edges = [
            edge
            for edge in cap_builder.edges()
            if abs(edge.center().Y - Y_TOP) <= 1.0e-6
        ]
        if len(top_edges) != 1:
            raise RuntimeError(
                "Unable to identify the exact circular top-right cap edge"
            )
        fillet(top_edges, radius=TOP_FILLET_RADIUS)
    full_cap = cap_builder.part

    with BuildSketch(xz_plane(Y_BODY_LOW)) as clip_sketch:
        with Locations((TR_X, TR_STEP_Z)):
            Rectangle(
                4.0 * OUTER_RADIUS,
                4.0 * OUTER_RADIUS,
                align=(Align.CENTER, Align.MIN),
            )
    clip = extrude(
        clip_sketch.sketch.faces()[0],
        amount=-(Y_TOP - Y_BODY_LOW),
    )
    return full_cap & clip


def _clipped_boss_solid(x: float, z: float, y0: float, y1: float):
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


def _subtract_cylindrical_bore(
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


def build_top():
    """Build and return the reconstructed top part as one parametric solid."""
    # Build independent F003-F005 operands before opening the parent context.
    # This is still a genuine parametric feature tree: each operand is an
    # identified analytic cylinder clipped by the identified analytic envelope.
    boss_solids = [
        _clipped_boss_solid(bx, bz, y0, y1)
        for _, bx, bz, y0, y1 in BOSSES
    ]

    with BuildPart() as top:
        # F001 — exact main rolling body: lower prism + R2 inset core + sweep
        add(_main_rolling_body())

        # F002 — exact clipped R4.3 top-right cap and toroidal R2 ledge blend
        add(_top_right_clipped_cap())

        # F003–F005 — exact independently generated clipped boss operands
        for boss_solid in boss_solids:
            add(boss_solid, mode=Mode.ADD)

        # F006 — Ø43 counterbore from Y=61.0 through Y=64.2
        _subtract_cylindrical_bore(
            MAIN_X,
            MAIN_Z,
            COUNTERBORE_RADIUS,
            Y_COUNTERBORE_LOW,
            Y_COUNTERBORE_HIGH,
        )

        # F007 — 2 mm anti-rotation key retained in Ø43/Ø39 annulus
        with BuildSketch(xz_plane(Y_BODY_LOW)) as key_profile:
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
        with BuildSketch(xz_plane(Y_BODY_LOW)) as engraving_profile:
            add(text_profile)
        extrude(
            engraving_profile.sketch,
            amount=-ENGRAVING_DEPTH,
            mode=Mode.SUBTRACT,
        )

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
