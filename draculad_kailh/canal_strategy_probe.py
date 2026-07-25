from __future__ import annotations

"""Compare whole-contour canal-fillet construction strategies."""

import json
import os
from pathlib import Path

from build123d import Face, Transition, Wire, export_step, extrude, sweep

from candidate_joint import (
    MAIN_ROLL_RADIUS,
    UNFILLETED_END_X,
    X_START,
    _resolved,
    profile_wire,
)
from swept_cutter_candidate import authored_profile_edges, corner_cutter_face


def metrics(shape):
    bb = shape.bounding_box()
    return {
        "valid": bool(_resolved(shape.is_valid)),
        "volume": float(_resolved(shape.volume)),
        "area": float(_resolved(shape.area)),
        "solids": len(shape.solids()),
        "shells": len(shape.shells()),
        "faces": len(shape.faces()),
        "bbox": [bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z],
    }


def main():
    strategy = os.environ["CANAL_STRATEGY"]
    out = Path("artifacts/canal_strategy")
    out.mkdir(parents=True, exist_ok=True)

    raw = extrude(
        Face(profile_wire(X_START)),
        UNFILLETED_END_X - X_START,
        dir=(1, 0, 0),
        clean=True,
    )
    edges = authored_profile_edges(UNFILLETED_END_X)
    section = corner_cutter_face(edges[0], MAIN_ROLL_RADIUS)
    report = {"strategy": strategy, "raw": metrics(raw)}

    if strategy in {"wire_frenet", "wire_corrected", "wire_round"}:
        path = Wire(edges)
        cutter = sweep(
            sections=section,
            path=path,
            is_frenet=strategy != "wire_corrected",
            transition=(Transition.ROUND if strategy == "wire_round" else Transition.TRANSFORMED),
            clean=True,
        )
    elif strategy == "individual_union":
        cutters = []
        rows = []
        for index, edge in enumerate(edges):
            local_section = corner_cutter_face(edge, MAIN_ROLL_RADIUS)
            local = sweep(
                sections=local_section,
                path=edge,
                is_frenet=True,
                clean=True,
            )
            rows.append({"index": index, **metrics(local)})
            cutters.append(local)
        report["individual_cutters"] = rows
        cutter = cutters[0].fuse(*cutters[1:]).clean()
    else:
        raise ValueError(strategy)

    report["cutter"] = metrics(cutter)
    rolled = raw.cut(cutter).clean()
    report["rolled"] = metrics(rolled)

    export_step(cutter, out / f"cutter_{strategy}.step")
    export_step(rolled, out / f"rolled_{strategy}.step")
    (out / f"strategy_{strategy}.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
