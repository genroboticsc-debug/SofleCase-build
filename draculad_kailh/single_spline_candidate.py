from __future__ import annotations

"""Single-spline Kailh solder meniscus candidate.

The eleven datums are exact engineering points on the five reference fillet
branches at the straight-to-roll tangent plane. They define one compact design
curve; no STEP poles, knots, pcurves, section stack, or topology are copied.
"""

import json
from pathlib import Path

from build123d import Edge, Face, GeomType, Solid, Vector, Wire, export_step, export_stl, extrude

from candidate_joint import (
    MAIN_ROLL_RADIUS,
    PAD_Z_MAX,
    TOP_Z,
    UNFILLETED_END_X,
    X_START,
    _resolved,
    closed_wire,
    pad_face,
)

PROFILE_DATUMS_YZ = (
    (3.90576480246421, 1.75000000000000),
    (4.023984011820813, 1.714516755368501),
    (4.12087378923583, 1.57689067591220),
    (4.248311078629781, 0.712055311788421),
    (4.70235196349251, 1.43492679304686),
    (5.069210154715189, 1.561664633732182),
    (5.46862670809520, 1.38160563822046),
    (5.91101907367040, 0.740430800709123),
    (6.05561815841550, 1.52891560478045),
    (6.166310258452469, 1.708854666930473),
    (6.26449204350269, 1.75000000000000),
)


def spline_edge(x: float) -> Edge:
    return Edge.make_spline(
        [Vector(x, y, z) for y, z in PROFILE_DATUMS_YZ],
        tol=1.0e-9,
    )


def profile_face(x: float) -> Face:
    curve = spline_edge(x)
    return Face(Wire([
        curve,
        Edge.make_line(curve.end_point(), curve.start_point()),
    ]))


def build_joint() -> tuple[Solid, dict]:
    profile = profile_face(X_START)
    raw = extrude(profile, UNFILLETED_END_X - X_START, dir=(1, 0, 0)).clean()
    terminal = []
    for edge in raw.edges():
        bb = edge.bounding_box()
        if (
            abs(bb.min.X - UNFILLETED_END_X) < 1.0e-6
            and abs(bb.max.X - UNFILLETED_END_X) < 1.0e-6
            and edge.geom_type == GeomType.BSPLINE
        ):
            terminal.append(edge)
    debug = {
        "profile_curve_length": float(_resolved(spline_edge(X_START).length)),
        "profile_area": float(_resolved(profile.area)),
        "raw_volume": float(_resolved(raw.volume)),
        "raw_valid": bool(_resolved(raw.is_valid)),
        "terminal_edges": len(terminal),
    }
    if len(terminal) != 1:
        raise RuntimeError(f"expected one terminal spline edge, got {len(terminal)}")
    rolled = raw.fillet(MAIN_ROLL_RADIUS, terminal)
    debug.update({
        "rolled_valid": bool(_resolved(rolled.is_valid)),
        "rolled_volume": float(_resolved(rolled.volume)),
        "rolled_area": float(_resolved(rolled.area)),
        "rolled_faces": len(rolled.faces()),
    })
    pad = extrude(pad_face(), PAD_Z_MAX - TOP_Z, dir=(0, 0, 1))
    joint = rolled.fuse(pad).clean()
    debug.update({
        "pad_volume": float(_resolved(pad.volume)),
        "joint_valid": bool(_resolved(joint.is_valid)),
        "joint_volume": float(_resolved(joint.volume)),
        "joint_area": float(_resolved(joint.area)),
        "joint_faces": len(joint.faces()),
        "joint_solids": len(joint.solids()),
    })
    if not bool(_resolved(joint.is_valid)) or len(joint.solids()) != 1:
        raise RuntimeError("single-spline candidate is invalid")
    return joint, debug


def main():
    out = Path("artifacts/single_spline")
    out.mkdir(parents=True, exist_ok=True)
    joint, debug = build_joint()
    export_step(joint, out / "candidate_joint.step")
    export_stl(joint, out / "candidate_joint.stl", tolerance=0.005, angular_tolerance=0.02)
    (out / "candidate_build.json").write_text(json.dumps(debug, indent=2))
    print(json.dumps(debug, indent=2))


if __name__ == "__main__":
    main()
