"""Test exact analytic alternatives to the failing edge-chain R2 fillet.

The candidate is not a sampled loft.  It is the exact union of:
* the outer profile prism up to the fillet spring plane,
* the exact 2-D inward offset profile extruded to the top plane, and
* a true quarter-disk swept around the outer profile.

A round sweep transition creates the exact spherical corner patches while
straight and circular path edges generate cylindrical and toroidal surfaces.
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
    Mode,
    Plane,
    Rectangle,
    Transition,
    Vector,
    add,
    export_step,
    export_stl,
    extrude,
    offset,
    sweep,
)

from top_parametric import (
    TOP_FILLET_RADIUS,
    Y_BODY_LOW,
    Y_FILLET_LOW,
    Y_TOP,
    outer_profile_sketch,
    xz_plane,
)

OUT = Path(__file__).resolve().parent / "generated"
OUT.mkdir(parents=True, exist_ok=True)
TARGET_TOP_OUTER_AREA = 1810.8227396526067
TARGET_BOUNDS = {
    "x_min": -26.28930283,
    "x_max": 17.57988834,
    "y_min": 62.5,
    "y_max": 67.2,
    "z_min": -34.66747665,
    "z_max": 14.84700298,
}


def _global_outer_face(y: float):
    with BuildSketch(xz_plane(y)) as sketch:
        add(outer_profile_sketch())
    return sketch.sketch.faces()[0]


def _quarter_disk_at_path_start(path, outer_face):
    start = Vector(path.position_at(0.0))
    tangent = Vector(path.tangent_at(0.0)).normalized()
    up = Vector(0.0, 1.0, 0.0)

    left = Vector(-tangent.Z, 0.0, tangent.X).normalized()
    to_center = Vector(outer_face.center()) - start
    inward = left if left.dot(to_center) >= 0.0 else -left

    # Plane local X = inward and local Y = global +Y.  Plane local Y is
    # z_dir cross x_dir, therefore z_dir = inward cross global_up.
    section_plane = Plane(
        origin=start,
        x_dir=inward,
        z_dir=inward.cross(up),
    )
    with BuildSketch(section_plane) as section:
        Circle(TOP_FILLET_RADIUS)
        Rectangle(
            TOP_FILLET_RADIUS,
            TOP_FILLET_RADIUS,
            align=(Align.MIN, Align.MIN),
            mode=Mode.INTERSECT,
        )
    return section.sketch.faces()[0], {
        "start": list(start),
        "tangent": list(tangent),
        "inward": list(inward),
        "section_area": section.sketch.faces()[0].area,
    }


def _top_planar_area(part) -> float:
    area = 0.0
    for face in part.faces():
        vertices = face.vertices()
        if vertices and all(abs(v.Y - Y_TOP) <= 1.0e-6 for v in vertices):
            area += face.area
    return area


def _candidate(transition: Transition, is_frenet: bool, use_normal: bool):
    outer_face = _global_outer_face(Y_FILLET_LOW)
    outer_wire = outer_face.outer_wire()
    inset = offset(
        outer_face,
        amount=-TOP_FILLET_RADIUS,
        kind=Kind.ARC,
        min_edge_length=1.0e-7,
    )
    inset_face = inset.faces()[0]
    quarter, frame = _quarter_disk_at_path_start(outer_wire, outer_face)

    lower = extrude(outer_face, amount=Y_FILLET_LOW - Y_BODY_LOW)
    core = extrude(inset_face, amount=-TOP_FILLET_RADIUS)
    kwargs = {
        "sections": quarter,
        "path": outer_wire,
        "is_frenet": is_frenet,
        "transition": transition,
    }
    if use_normal:
        kwargs["normal"] = Vector(0.0, 1.0, 0.0)
    rim = sweep(**kwargs)

    with BuildPart() as assembled:
        add(lower)
        add(core)
        add(rim)
    part = assembled.part
    bbox = part.bounding_box()
    result = {
        "frame": frame,
        "transition": transition.name,
        "is_frenet": is_frenet,
        "use_normal": use_normal,
        "valid": bool(part.is_valid),
        "solid_count": len(part.solids()),
        "volume": part.volume,
        "area": part.area,
        "top_planar_area": _top_planar_area(part),
        "top_area_error": abs(_top_planar_area(part) - TARGET_TOP_OUTER_AREA),
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
    stem = f"analytic_{transition.name.lower()}_f{int(is_frenet)}_n{int(use_normal)}"
    export_step(part, OUT / f"{stem}.step")
    export_stl(
        part,
        OUT / f"{stem}.stl",
        tolerance=0.002,
        angular_tolerance=0.1,
        ascii_format=False,
    )
    return result


def main() -> int:
    attempts = []
    for transition in (
        Transition.ROUND,
        Transition.RIGHT,
        Transition.TRANSFORMED,
    ):
        for is_frenet in (False, True):
            for use_normal in (False, True):
                try:
                    attempts.append(
                        {
                            "ok": True,
                            **_candidate(transition, is_frenet, use_normal),
                        }
                    )
                except Exception as exc:  # diagnostics must continue
                    attempts.append(
                        {
                            "ok": False,
                            "transition": transition.name,
                            "is_frenet": is_frenet,
                            "use_normal": use_normal,
                            "exception": f"{type(exc).__name__}: {exc}",
                            "traceback": traceback.format_exc(),
                        }
                    )
    report = {"target_bounds": TARGET_BOUNDS, "attempts": attempts}
    path = OUT / "analytic_fillet_diagnostic.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
