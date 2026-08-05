from __future__ import annotations

"""Kailh solder joint built with an analytical canal-fillet cutter.

The main R0.375 terminal roll is produced by sweeping the standard engineering
corner-removal section along the authored meniscus contour. This is the
constructive equivalent of a rolling-ball edge fillet and contains no reference
B-Rep, pcurve, spline-pole, mesh, or sampled-section replay.
"""

import json
from math import sqrt
from pathlib import Path

from build123d import Edge, Face, Part, Plane, Vector, export_step, export_stl, extrude, sweep

from candidate_joint import (
    MAIN_ROLL_RADIUS,
    PAD_Z_MAX,
    PROFILE_SPANS_YZ,
    TOP_Z,
    UNFILLETED_END_X,
    X_START,
    _resolved,
    closed_wire,
    pad_face,
    profile_wire,
)


def authored_profile_edges(x: float) -> list[Edge]:
    return [Edge.make_bezier(*((x, y, z) for y, z in span)) for span in PROFILE_SPANS_YZ]


def local_point(plane: Plane, x: float, y: float) -> Vector:
    return Vector(plane.from_local_coords(Vector(x, y, 0)))


def corner_cutter_face(path_edge: Edge, radius: float) -> Face:
    origin = path_edge.position_at(0)
    tangent = Vector(path_edge.tangent_at(0)).normalized()

    # The authored contour runs from the right top corner toward the left top
    # corner. Plane +Y is the inward profile normal and plane -X points into
    # the two-millimetre extrusion.
    plane = Plane(origin=origin, x_dir=(1, 0, 0), z_dir=tangent)

    tangent_side = local_point(plane, -radius, 0)
    sharp_corner = local_point(plane, 0, 0)
    tangent_end = local_point(plane, 0, radius)
    arc_mid = local_point(
        plane,
        -radius + radius / sqrt(2.0),
        radius - radius / sqrt(2.0),
    )
    return Face(
        closed_wire(
            [
                Edge.make_line(tangent_side, sharp_corner),
                Edge.make_line(sharp_corner, tangent_end),
                Edge.make_three_point_arc(tangent_end, arc_mid, tangent_side),
            ]
        )
    )


def metric(value):
    return _resolved(value)


def build_joint() -> tuple[Part, dict]:
    raw = extrude(
        Face(profile_wire(X_START)),
        UNFILLETED_END_X - X_START,
        dir=(1, 0, 0),
        clean=True,
    )
    profile_edges = authored_profile_edges(UNFILLETED_END_X)
    debug: dict = {
        "raw_valid": bool(metric(raw.is_valid)),
        "raw_volume": float(metric(raw.volume)),
        "profile_edge_count": len(profile_edges),
        "cutter_results": [],
    }

    rolled = raw
    for index, path_edge in enumerate(profile_edges):
        row = {"index": index, "path_length": float(metric(path_edge.length))}
        try:
            section = corner_cutter_face(path_edge, MAIN_ROLL_RADIUS)
            cutter = sweep(
                sections=section,
                path=path_edge,
                is_frenet=True,
                clean=True,
            )
            row.update(
                {
                    "sweep_success": True,
                    "cutter_valid": bool(metric(cutter.is_valid)),
                    "cutter_volume": float(metric(cutter.volume)),
                    "cutter_solids": len(cutter.solids()),
                }
            )
            rolled = rolled.cut(cutter).clean()
            row.update(
                {
                    "cut_success": True,
                    "rolled_valid": bool(metric(rolled.is_valid)),
                    "rolled_volume": float(metric(rolled.volume)),
                    "rolled_solids": len(rolled.solids()),
                }
            )
            if not row["rolled_valid"] or row["rolled_solids"] != 1:
                raise RuntimeError(f"invalid roll after cutter {index}")
        except Exception as exc:
            row.update(
                {
                    "sweep_success": row.get("sweep_success", False),
                    "cut_success": row.get("cut_success", False),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            debug["cutter_results"].append(row)
            raise
        debug["cutter_results"].append(row)

    pad = extrude(pad_face(), PAD_Z_MAX - TOP_Z, dir=(0, 0, 1), clean=True)
    joint = rolled.fuse(pad).clean()
    debug.update(
        {
            "rolled_valid": bool(metric(rolled.is_valid)),
            "rolled_volume": float(metric(rolled.volume)),
            "rolled_area": float(metric(rolled.area)),
            "rolled_faces": len(rolled.faces()),
            "pad_volume": float(metric(pad.volume)),
            "joint_valid": bool(metric(joint.is_valid)),
            "joint_volume": float(metric(joint.volume)),
            "joint_area": float(metric(joint.area)),
            "joint_faces": len(joint.faces()),
            "joint_solids": len(joint.solids()),
        }
    )
    if not bool(metric(joint.is_valid)) or len(joint.solids()) != 1:
        raise RuntimeError("analytical canal-fillet candidate is invalid")
    return joint, debug


def main() -> None:
    out = Path("artifacts/swept_cutter")
    out.mkdir(parents=True, exist_ok=True)
    try:
        joint, debug = build_joint()
        export_step(joint, out / "candidate_joint.step")
        export_stl(joint, out / "candidate_joint.stl", tolerance=0.005, angular_tolerance=0.02)
    except Exception as exc:
        debug = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
        (out / "candidate_build.json").write_text(json.dumps(debug, indent=2))
        print(json.dumps(debug, indent=2))
        raise
    debug["success"] = True
    (out / "candidate_build.json").write_text(json.dumps(debug, indent=2))
    print(json.dumps(debug, indent=2))


if __name__ == "__main__":
    main()
