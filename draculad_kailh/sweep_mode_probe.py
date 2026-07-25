from __future__ import annotations

"""Compare OCC pipe orientation modes for one canal-fillet cutter span."""

import json
import os
from pathlib import Path

from build123d import Face, Solid, Vector, export_step, sweep

from candidate_joint import MAIN_ROLL_RADIUS, UNFILLETED_END_X, _resolved
from swept_cutter_candidate import authored_profile_edges, corner_cutter_face


def bbox(shape):
    b = shape.bounding_box()
    return [b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z]


def main() -> None:
    mode_name = os.environ["SWEEP_MODE"]
    edge_index = int(os.environ.get("EDGE_INDEX", "0"))
    out = Path("artifacts/sweep_modes")
    out.mkdir(parents=True, exist_ok=True)

    path = authored_profile_edges(UNFILLETED_END_X)[edge_index]
    section = corner_cutter_face(path, MAIN_ROLL_RADIUS)
    tangent = Vector(path.tangent_at(0)).normalized()
    normal = Vector(section.normal_at(section.center())).normalized()

    kwargs = {"sections": section, "path": path, "clean": False}
    if mode_name == "frenet":
        kwargs.update(is_frenet=True)
    elif mode_name == "corrected":
        kwargs.update(is_frenet=False)
    elif mode_name == "binormal_pos_x":
        kwargs.update(is_frenet=False, normal=(1, 0, 0))
    elif mode_name == "binormal_neg_x":
        kwargs.update(is_frenet=False, normal=(-1, 0, 0))
    else:
        raise ValueError(mode_name)

    cutter = sweep(**kwargs)
    report = {
        "mode": mode_name,
        "edge_index": edge_index,
        "path_length": float(_resolved(path.length)),
        "path_bbox": bbox(path),
        "section_area": float(_resolved(section.area)),
        "section_bbox": bbox(section),
        "section_normal": list(normal.to_tuple()),
        "start_tangent": list(tangent.to_tuple()),
        "normal_dot_tangent": normal.dot(tangent),
        "cutter_valid": bool(_resolved(cutter.is_valid)),
        "cutter_volume": float(_resolved(cutter.volume)),
        "cutter_area": float(_resolved(cutter.area)),
        "cutter_bbox": bbox(cutter),
        "cutter_faces": len(cutter.faces()),
        "cutter_shells": len(cutter.shells()),
        "cutter_solids": len(cutter.solids()),
    }
    export_step(cutter, out / f"mode_{mode_name}_edge_{edge_index}.step")
    (out / f"mode_{mode_name}_edge_{edge_index}.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
