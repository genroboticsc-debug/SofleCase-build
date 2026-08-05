from __future__ import annotations

"""Probe the native OCC fillet feasibility of the authored terminal edge chain."""

import json
from pathlib import Path

from build123d import Face, export_step, extrude

from candidate_joint import (
    MAIN_ROLL_RADIUS,
    UNFILLETED_END_X,
    X_START,
    _resolved,
    edge_record,
    geom_type_name,
    profile_wire,
)


def terminal_edges(raw):
    result = []
    for edge in raw.edges():
        bb = edge.bounding_box()
        if abs(bb.min.X - UNFILLETED_END_X) < 1.0e-6 and abs(bb.max.X - UNFILLETED_END_X) < 1.0e-6:
            if "line" not in geom_type_name(edge):
                result.append(edge)
    return result


def try_fillet(raw, edges, radius):
    try:
        shape = raw.fillet(radius, edges)
        return {
            "success": True,
            "valid": bool(_resolved(shape.is_valid)),
            "volume": float(_resolved(shape.volume)),
            "faces": len(shape.faces()),
            "solids": len(shape.solids()),
        }, shape
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}, None


def main():
    out = Path("artifacts")
    out.mkdir(exist_ok=True)
    raw = extrude(Face(profile_wire(X_START)), UNFILLETED_END_X - X_START, dir=(1, 0, 0))
    edges = terminal_edges(raw)
    report = {
        "raw_valid": bool(_resolved(raw.is_valid)),
        "raw_volume": float(_resolved(raw.volume)),
        "edge_count": len(edges),
        "edges": [edge_record(e) for e in edges],
        "individual": [],
        "pairs": [],
        "triples": [],
        "all": None,
    }
    export_step(raw, out / "raw_unfilleted_joint.step")

    for i, edge in enumerate(edges):
        result, shape = try_fillet(raw, [edge], MAIN_ROLL_RADIUS)
        result["edge"] = i
        report["individual"].append(result)
        if shape is not None:
            export_step(shape, out / f"fillet_edge_{i}.step")

    for size, key in [(2, "pairs"), (3, "triples")]:
        for start in range(len(edges) - size + 1):
            indices = list(range(start, start + size))
            result, _ = try_fillet(raw, [edges[i] for i in indices], MAIN_ROLL_RADIUS)
            result["edges"] = indices
            report[key].append(result)

    report["all"], _ = try_fillet(raw, edges, MAIN_ROLL_RADIUS)
    (out / "fillet_probe.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
