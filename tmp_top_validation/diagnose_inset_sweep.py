"""Build the R2 top roll as an exact rolling-ball sweep around the inset core.

At height h above the spring plane, the reference cross-section is the exact
2-D dilation of the identified R2 inset contour by sqrt(R^2-h^2).  This is
constructed as an inset-core extrusion plus a true quarter-disk sweep directed
outward from the inset boundary.  No sampled sections or fitted surfaces are
used.
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


def _face_at(sketch, y: float):
    with BuildSketch(xz_plane(y)) as placed:
        add(sketch)
    return placed.sketch.faces()[0]


def _solid_from(sketch, y0: float, y1: float):
    return extrude(_face_at(sketch, y0), amount=-(y1 - y0))


def _quarter_disk_outward(path, inset_face):
    start = Vector(path.position_at(0.0))
    tangent = Vector(path.tangent_at(0.0)).normalized()
    up = Vector(0.0, 1.0, 0.0)
    left = Vector(-tangent.Z, 0.0, tangent.X).normalized()
    toward_center = Vector(inset_face.center()) - start
    inward = left if left.dot(toward_center) >= 0.0 else -left
    outward = -inward

    section_plane = Plane(
        origin=start,
        x_dir=outward,
        z_dir=outward.cross(up),
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
        "outward": list(outward),
        "area": section.sketch.faces()[0].area,
    }


def _top_planar_area(part) -> float:
    return sum(
        face.area
        for face in part.faces()
        if face.vertices()
        and all(abs(vertex.Y - Y_TOP) <= 1.0e-6 for vertex in face.vertices())
    )


def _metrics(name: str, part):
    bbox = part.bounding_box()
    result = {
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
        tolerance=0.001,
        angular_tolerance=0.1,
        ascii_format=False,
    )
    return result


def _candidate(transition, is_frenet: bool, use_normal: bool):
    outer = outer_profile_sketch()
    inset = offset(
        outer,
        amount=-TOP_FILLET_RADIUS,
        kind=Kind.ARC,
        min_edge_length=1.0e-7,
    )
    inset_face = _face_at(inset, Y_FILLET_LOW)
    path = inset_face.outer_wire()
    quarter, frame = _quarter_disk_outward(path, inset_face)

    kwargs = {
        "sections": quarter,
        "path": path,
        "transition": transition,
        "is_frenet": is_frenet,
    }
    if use_normal:
        kwargs["normal"] = Vector(0.0, 1.0, 0.0)
    rim = sweep(**kwargs)
    core = _solid_from(inset, Y_FILLET_LOW, Y_TOP)
    lower = _solid_from(outer, Y_BODY_LOW, Y_FILLET_LOW)

    with BuildPart() as assembled:
        add(lower)
        add(core)
        add(rim)
    final = assembled.part
    return frame, inset.faces()[0].area, rim, core, final


def main() -> int:
    attempts = []
    for transition in (
        Transition.ROUND,
        Transition.RIGHT,
        Transition.TRANSFORMED,
    ):
        for is_frenet in (False, True):
            for use_normal in (False, True):
                stem = (
                    f"inset_{transition.name.lower()}_"
                    f"f{int(is_frenet)}_n{int(use_normal)}"
                )
                try:
                    frame, inset_area, rim, core, final = _candidate(
                        transition, is_frenet, use_normal
                    )
                    attempts.append(
                        {
                            "ok": True,
                            "transition": transition.name,
                            "is_frenet": is_frenet,
                            "use_normal": use_normal,
                            "frame": frame,
                            "inset_area": inset_area,
                            "rim": _metrics(f"{stem}_rim", rim),
                            "core": _metrics(f"{stem}_core", core),
                            "final": _metrics(f"{stem}_final", final),
                        }
                    )
                except Exception as exc:
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

    report = {"attempts": attempts}
    (OUT / "inset_sweep_diagnostic.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
