from __future__ import annotations

"""Analysis-only proof of the R0.375 canal-fillet construction.

This script may inspect and reuse one reference contour edge because its output
is validation evidence only. It is never imported by a production builder.
"""

import json
from pathlib import Path

from build123d import Edge, Face, GeomType, Location, Vector, Wire, export_step, extrude, import_step, sweep

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
from swept_cutter_candidate import corner_cutter_face


def isolate_right_solder(reference):
    matches = []
    for index, solid in enumerate(reference.solids()):
        bb = solid.bounding_box()
        if 1.0 < float(_resolved(solid.volume)) < 3.0 and bb.min.X > 4.0:
            matches.append((index, solid))
    if len(matches) != 1:
        raise RuntimeError(f"expected one right solder body, got {len(matches)}")
    return matches[0]


def find_profile_edge(solder) -> Edge:
    matches = []
    for edge in solder.edges():
        bb = edge.bounding_box()
        length = float(_resolved(edge.length))
        if (
            edge.geom_type == GeomType.BSPLINE
            and abs(length - 4.851046962108225) < 1.0e-6
            and abs(bb.min.X - X_START) < 1.0e-5
            and abs(bb.max.X - X_START) < 1.0e-5
        ):
            matches.append(edge)
    if len(matches) != 1:
        raise RuntimeError(f"expected one exact start profile edge, got {len(matches)}")
    return matches[0]


def face_from_contour(contour: Edge) -> Face:
    return Face(Wire([contour, Edge.make_line(contour.end_point(), contour.start_point())]))


def main():
    out = Path("artifacts/reference_canal")
    out.mkdir(parents=True, exist_ok=True)
    reference = import_step("reference.step")
    ref_index, solder = isolate_right_solder(reference)
    contour_start = find_profile_edge(solder)
    profile = face_from_contour(contour_start)
    raw = extrude(profile, UNFILLETED_END_X - X_START, dir=(1, 0, 0), clean=True)
    contour_end = contour_start.moved(Location((UNFILLETED_END_X - X_START, 0, 0)))
    cutter_face = corner_cutter_face(contour_end, MAIN_ROLL_RADIUS)
    cutter = sweep(
        sections=cutter_face,
        path=contour_end,
        is_frenet=True,
        normal=(1, 0, 0),
        clean=True,
    )
    rolled = raw.cut(cutter).clean()
    pad = extrude(pad_face(), PAD_Z_MAX - TOP_Z, dir=(0, 0, 1), clean=True)
    joint = rolled.fuse(pad).clean()
    report = {
        "analysis_only": True,
        "reference_solid_index": ref_index,
        "contour_length": float(_resolved(contour_start.length)),
        "profile_area": float(_resolved(profile.area)),
        "raw_valid": bool(_resolved(raw.is_valid)),
        "raw_volume": float(_resolved(raw.volume)),
        "cutter_valid": bool(_resolved(cutter.is_valid)),
        "cutter_volume": float(_resolved(cutter.volume)),
        "rolled_valid": bool(_resolved(rolled.is_valid)),
        "rolled_volume": float(_resolved(rolled.volume)),
        "rolled_area": float(_resolved(rolled.area)),
        "rolled_faces": len(rolled.faces()),
        "joint_valid": bool(_resolved(joint.is_valid)),
        "joint_volume": float(_resolved(joint.volume)),
        "joint_area": float(_resolved(joint.area)),
        "joint_faces": len(joint.faces()),
    }
    export_step(raw, out / "exact_profile_unfilleted.step")
    export_step(cutter, out / "exact_profile_cutter.step")
    export_step(rolled, out / "exact_profile_main_roll.step")
    export_step(joint, out / "exact_profile_main_roll_with_pad.step")
    (out / "reference_canal_probe.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
