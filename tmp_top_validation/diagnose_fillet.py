"""Identify the exact valid OpenCascade R2 fillet seed chain for the top body."""

from __future__ import annotations

import itertools
import json
from pathlib import Path

from build123d import BuildPart, BuildSketch, add, extrude

import top_parametric as model

TARGET_TOP_OUTER_AREA_MM2 = 1810.8227396526067
TARGET_TOP_BOUNDS = {
    "x_min": -24.28930283,
    "x_max": 15.57988834,
    "z_min": -32.66747665,
    "z_max": 12.84700298,
}


def make_base():
    with BuildPart() as base:
        with BuildSketch(model.xz_plane(model.Y_BODY_LOW)):
            add(model.outer_profile_sketch())
        extrude(amount=-(model.Y_TOP - model.Y_BODY_LOW))
    return base.part


def top_face_signature(shape):
    top_faces = []
    for face in shape.faces():
        box = face.bounding_box()
        if (
            abs(box.min.Y - model.Y_TOP) <= 1.0e-6
            and abs(box.max.Y - model.Y_TOP) <= 1.0e-6
        ):
            top_faces.append(face)
    if not top_faces:
        return None
    area = sum(face.area for face in top_faces)
    x_min = min(face.bounding_box().min.X for face in top_faces)
    x_max = max(face.bounding_box().max.X for face in top_faces)
    z_min = min(face.bounding_box().min.Z for face in top_faces)
    z_max = max(face.bounding_box().max.Z for face in top_faces)
    return {
        "area_mm2": area,
        "area_error_mm2": area - TARGET_TOP_OUTER_AREA_MM2,
        "bounds": {"x_min": x_min, "x_max": x_max, "z_min": z_min, "z_max": z_max},
        "bounds_abs_error_mm": {
            key: abs(value - TARGET_TOP_BOUNDS[key])
            for key, value in {
                "x_min": x_min,
                "x_max": x_max,
                "z_min": z_min,
                "z_max": z_max,
            }.items()
        },
    }


def main(output_dir: Path | str = Path("generated")) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = make_base()
    top_edges = [
        edge for edge in base.edges() if abs(edge.center().Y - model.Y_TOP) <= 1.0e-6
    ]
    top_edges.sort(
        key=lambda edge: (
            round(edge.length, 12),
            round(edge.center().X, 12),
            round(edge.center().Z, 12),
        )
    )
    edge_table = [
        {
            "index": index,
            "length_mm": edge.length,
            "center": [edge.center().X, edge.center().Y, edge.center().Z],
        }
        for index, edge in enumerate(top_edges)
    ]

    successes = []
    failures = 0
    all_indices = tuple(range(len(top_edges)))
    # Test the complete chain and all chains formed by omitting up to four
    # identified edges. This covers 256 deterministic edge combinations.
    omitted_sets = [tuple()]
    for count in range(1, min(4, len(top_edges)) + 1):
        omitted_sets.extend(itertools.combinations(all_indices, count))

    for omitted in omitted_sets:
        selected_indices = [i for i in all_indices if i not in omitted]
        if not selected_indices:
            continue
        try:
            candidate = base.fillet(
                model.TOP_FILLET_RADIUS,
                [top_edges[i] for i in selected_indices],
            )
        except Exception:
            failures += 1
            continue
        signature = top_face_signature(candidate)
        record = {
            "selected": selected_indices,
            "omitted": list(omitted),
            "volume_mm3": candidate.volume,
            "surface_area_mm2": candidate.area,
            "top": signature,
        }
        if signature is not None:
            score = abs(signature["area_error_mm2"]) + 1000.0 * sum(
                signature["bounds_abs_error_mm"].values()
            )
        else:
            score = float("inf")
        record["score"] = score
        successes.append(record)

    successes.sort(key=lambda record: record["score"])
    report = {
        "target_top_outer_area_mm2": TARGET_TOP_OUTER_AREA_MM2,
        "target_top_bounds": TARGET_TOP_BOUNDS,
        "edges": edge_table,
        "attempts": len(omitted_sets),
        "failure_count": failures,
        "success_count": len(successes),
        "best_successes": successes[:50],
    }
    (output_dir / "fillet_diagnostic.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    main(Path(__file__).resolve().parent / "generated")
