"""Validate the exact clipped-cap decomposition of the top-right ledge.

The reference ledge is bounded by two identified analytical surfaces:

* the R2 cylindrical top roll of the X=17.57988739 right wall; and
* the R2 toroidal top roll of the R4.3 circular cap centred at
  (13.60985870, 10.54700352).

The complete outer body is therefore built as the union of the exact main
rolling-ball body and an independently top-filleted R4.3 cylinder clipped by
Z >= 12.002760887.  This preserves the 0.076052190114 mm ledge at the spring
plane and lets the cylindrical/toroidal envelopes eliminate it naturally.
No sampled loft, spline fit, mesh replay, or approximated profile is used.
"""

from __future__ import annotations

import json
import traceback
from pathlib import Path

from build123d import (
    Align,
    BuildPart,
    BuildSketch,
    Circle,
    Kind,
    Locations,
    Mode,
    Rectangle,
    Transition,
    Vector,
    add,
    export_step,
    export_stl,
    extrude,
    fillet,
    offset,
    sweep,
)

from top_parametric import (
    OUTER_RADIUS,
    TOP_FILLET_RADIUS,
    TR_STEP_Z,
    TR_X,
    TR_Z,
    Y_BODY_LOW,
    Y_FILLET_LOW,
    Y_TOP,
    outer_profile_sketch,
    xz_plane,
)

OUT = Path(__file__).resolve().parent / "generated"
OUT.mkdir(parents=True, exist_ok=True)


def _placed_face(sketch, y: float):
    with BuildSketch(xz_plane(y)) as placed:
        add(sketch)
    return placed.sketch.faces()[0]


def _solid_from(sketch, y0: float, y1: float):
    return extrude(_placed_face(sketch, y0), amount=-(y1 - y0))


def _quarter_disk_outward(path, inset_face):
    start = Vector(path.position_at(0.0))
    tangent = Vector(path.tangent_at(0.0)).normalized()
    up = Vector(0.0, 1.0, 0.0)
    left = Vector(-tangent.Z, 0.0, tangent.X).normalized()
    toward_center = Vector(inset_face.center()) - start
    inward = left if left.dot(toward_center) >= 0.0 else -left
    outward = -inward
    section_plane = xz_section_plane(start, outward, up)
    with BuildSketch(section_plane) as section:
        Circle(TOP_FILLET_RADIUS)
        Rectangle(
            TOP_FILLET_RADIUS,
            TOP_FILLET_RADIUS,
            align=(Align.MIN, Align.MIN),
            mode=Mode.INTERSECT,
        )
    return section.sketch.faces()[0]


def xz_section_plane(origin: Vector, outward: Vector, up: Vector):
    from build123d import Plane

    return Plane(
        origin=origin,
        x_dir=outward,
        z_dir=outward.cross(up),
    )


def _main_rolling_body():
    outer = outer_profile_sketch()
    inset = offset(
        outer,
        amount=-TOP_FILLET_RADIUS,
        kind=Kind.ARC,
        min_edge_length=1.0e-7,
    )
    inset_face = _placed_face(inset, Y_FILLET_LOW)
    path = inset_face.outer_wire()
    section = _quarter_disk_outward(path, inset_face)
    rim = sweep(
        sections=section,
        path=path,
        transition=Transition.ROUND,
        is_frenet=False,
    )
    lower = _solid_from(outer, Y_BODY_LOW, Y_FILLET_LOW)
    core = _solid_from(inset, Y_FILLET_LOW, Y_TOP)
    return lower.fuse(core, rim)


def _native_filleted_cap():
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
                f"Expected one circular cap edge at Y={Y_TOP}, got "
                f"{[(edge.length, list(edge.center())) for edge in top_edges]}"
            )
        fillet(top_edges, radius=TOP_FILLET_RADIUS)
    return cap_builder.part


def _clipping_prism():
    # Exact half-space surrogate containing the cap and bounded only outside
    # the part envelope.  Its lower local-sketch edge is the identified
    # Z=TR_STEP_Z clipping plane.
    with BuildSketch(xz_plane(Y_BODY_LOW)) as clip_sketch:
        with Locations((TR_X, TR_STEP_Z)):
            Rectangle(
                4.0 * OUTER_RADIUS,
                4.0 * OUTER_RADIUS,
                align=(Align.CENTER, Align.MIN),
            )
    return extrude(
        clip_sketch.sketch.faces()[0],
        amount=-(Y_TOP - Y_BODY_LOW),
    )


def _top_planar_area(part) -> float:
    return sum(
        face.area
        for face in part.faces()
        if face.vertices()
        and all(abs(vertex.Y - Y_TOP) <= 1.0e-6 for vertex in face.vertices())
    )


def _metrics(name: str, part):
    bbox = part.bounding_box()
    record = {
        "name": name,
        "valid": bool(part.is_valid),
        "solid_count": len(part.solids()),
        "volume": part.volume,
        "area": part.area,
        "top_planar_area": _top_planar_area(part),
        "bounds": {
            "x_min": bbox.min.X,
            "x_max": bbox.max.X,
            "y_min": bbox.min.Y,
            "y_max": bbox.max.Y,
            "z_min": bbox.min.Z,
            "z_max": bbox.max.Z,
        },
        "face_types": sorted(face.geom_type.name for face in part.faces()),
    }
    export_step(part, OUT / f"{name}.step")
    export_stl(
        part,
        OUT / f"{name}.stl",
        tolerance=0.0005,
        angular_tolerance=0.05,
        ascii_format=False,
    )
    return record


def main() -> int:
    report = {}
    try:
        main_body = _main_rolling_body()
        full_cap = _native_filleted_cap()
        clip = _clipping_prism()
        clipped_cap = full_cap & clip
        corrected = main_body.fuse(clipped_cap)
        report = {
            "ok": True,
            "main_body": _metrics("clipped_cap_main", main_body),
            "full_cap": _metrics("clipped_cap_full", full_cap),
            "clipped_cap": _metrics("clipped_cap_only", clipped_cap),
            "corrected": _metrics("clipped_cap_corrected", corrected),
        }
    except Exception as exc:
        report = {
            "ok": False,
            "exception": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
    (OUT / "clipped_cap_union_diagnostic.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
