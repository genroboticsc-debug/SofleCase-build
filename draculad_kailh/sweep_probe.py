from __future__ import annotations

"""Run one analytical R0.375 cutter sweep in an isolated process."""

import json
import os
from pathlib import Path

from build123d import Face, export_step, extrude, sweep

from candidate_joint import (
    MAIN_ROLL_RADIUS,
    PROFILE_SPANS_YZ,
    UNFILLETED_END_X,
    X_START,
    _resolved,
    profile_wire,
)
from swept_cutter_candidate import authored_profile_edges, corner_cutter_face


def main() -> None:
    index = int(os.environ["EDGE_INDEX"])
    out = Path("artifacts/sweep_probe")
    out.mkdir(parents=True, exist_ok=True)

    raw = extrude(
        Face(profile_wire(X_START)),
        UNFILLETED_END_X - X_START,
        dir=(1, 0, 0),
        clean=True,
    )
    path = authored_profile_edges(UNFILLETED_END_X)[index]
    report = {
        "index": index,
        "path_length": float(_resolved(path.length)),
        "raw_volume": float(_resolved(raw.volume)),
    }
    section = corner_cutter_face(path, MAIN_ROLL_RADIUS)
    report["section_area"] = float(_resolved(section.area))
    cutter = sweep(
        sections=section,
        path=path,
        is_frenet=True,
        normal=(1, 0, 0),
        clean=True,
    )
    report.update({
        "sweep_success": True,
        "cutter_valid": bool(_resolved(cutter.is_valid)),
        "cutter_volume": float(_resolved(cutter.volume)),
        "cutter_solids": len(cutter.solids()),
    })
    rolled = raw.cut(cutter).clean()
    report.update({
        "cut_success": True,
        "rolled_valid": bool(_resolved(rolled.is_valid)),
        "rolled_volume": float(_resolved(rolled.volume)),
        "rolled_solids": len(rolled.solids()),
    })
    export_step(cutter, out / f"cutter_{index}.step")
    export_step(rolled, out / f"rolled_{index}.step")
    (out / f"probe_{index}.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
