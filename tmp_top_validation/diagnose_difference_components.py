"""Localize bidirectional Boolean differences by component volume and bounds."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh

from validate_fast_manifold import topology_split_reference
from validate_feature_tree_manifold import (
    FEATURES,
    GENERATED,
    REFERENCE,
    as_mesh,
    build_feature_mesh_tree,
    mesh_stats,
)

OUT = GENERATED / "difference_components"
OUT.mkdir(parents=True, exist_ok=True)


def component_record(index: int, component: trimesh.Trimesh) -> dict:
    bounds = np.asarray(component.bounds, dtype=float)
    center_mass = np.asarray(component.center_mass, dtype=float)
    centroid = np.asarray(component.centroid, dtype=float)
    extents = bounds[1] - bounds[0]
    return {
        "index": int(index),
        "volume_mm3": float(abs(component.volume)),
        "area_mm2": float(component.area),
        "center_mass_mm": center_mass.tolist(),
        "centroid_mm": centroid.tolist(),
        "bounds_mm": bounds.tolist(),
        "extents_mm": extents.tolist(),
        "vertices": int(len(component.vertices)),
        "faces": int(len(component.faces)),
        "watertight": bool(component.is_watertight),
        "is_volume": bool(component.is_volume),
    }


def analyze_difference(
    first: trimesh.Trimesh,
    second: trimesh.Trimesh,
    label: str,
) -> dict:
    difference = as_mesh(
        trimesh.boolean.difference(
            [first, second],
            engine="manifold",
            check_volume=True,
        ),
        label,
    )
    path = OUT / f"{label}.stl"
    difference.export(path)
    components = list(difference.split(only_watertight=False))
    records = [component_record(index, component) for index, component in enumerate(components)]
    records.sort(key=lambda record: (-record["volume_mm3"], record["index"]))
    total = float(sum(record["volume_mm3"] for record in records))
    cumulative = 0.0
    for rank, record in enumerate(records, start=1):
        cumulative += record["volume_mm3"]
        record["rank"] = rank
        record["fraction_of_direction_percent"] = (
            record["volume_mm3"] / total * 100.0 if total else 0.0
        )
        record["cumulative_fraction_percent"] = (
            cumulative / total * 100.0 if total else 0.0
        )
    return {
        "label": label,
        "file": str(path.resolve()),
        "aggregate": mesh_stats(difference),
        "component_count": len(records),
        "total_component_volume_mm3": total,
        "top_components": records[:100],
    }


def spatial_buckets(records: list[dict]) -> dict:
    buckets = {
        "engraving_x_lt_minus10_z_gt_0": 0.0,
        "top_right_x_gt_9_z_gt_6": 0.0,
        "bottom_left_x_lt_minus10_z_lt_minus20": 0.0,
        "bottom_right_x_gt_5_z_lt_minus20": 0.0,
        "main_opening_radius_lt_23": 0.0,
        "other": 0.0,
    }
    main_x = -4.78930378
    main_z = -10.63847256
    for record in records:
        x, _, z = record["center_mass_mm"]
        volume = record["volume_mm3"]
        if x < -10.0 and z > 0.0:
            buckets["engraving_x_lt_minus10_z_gt_0"] += volume
        elif x > 9.0 and z > 6.0:
            buckets["top_right_x_gt_9_z_gt_6"] += volume
        elif x < -10.0 and z < -20.0:
            buckets["bottom_left_x_lt_minus10_z_lt_minus20"] += volume
        elif x > 5.0 and z < -20.0:
            buckets["bottom_right_x_gt_5_z_lt_minus20"] += volume
        elif (x - main_x) ** 2 + (z - main_z) ** 2 < 23.0 ** 2:
            buckets["main_opening_radius_lt_23"] += volume
        else:
            buckets["other"] += volume
    return buckets


def main() -> int:
    GENERATED.mkdir(parents=True, exist_ok=True)
    FEATURES.mkdir(parents=True, exist_ok=True)
    reference_raw = as_mesh(trimesh.load_mesh(REFERENCE, process=True), "reference")
    reference_mesh, topology_audit, topology_checks = topology_split_reference(reference_raw)
    if not all(topology_checks.values()):
        raise RuntimeError("Reference topology split failed")

    generated_mesh, feature_audit = build_feature_mesh_tree()
    generated_mesh.export(GENERATED / "localized_generated_feature_tree.stl")

    generated_minus_reference = analyze_difference(
        generated_mesh,
        reference_mesh,
        "generated_minus_reference",
    )
    reference_minus_generated = analyze_difference(
        reference_mesh,
        generated_mesh,
        "reference_minus_generated",
    )
    generated_minus_reference["spatial_buckets_mm3"] = spatial_buckets(
        generated_minus_reference["top_components"]
    )
    reference_minus_generated["spatial_buckets_mm3"] = spatial_buckets(
        reference_minus_generated["top_components"]
    )

    report = {
        "reference_topology_audit": topology_audit,
        "reference_topology_checks": topology_checks,
        "feature_tree_final_stats": mesh_stats(generated_mesh),
        "feature_audit": feature_audit,
        "generated_minus_reference": generated_minus_reference,
        "reference_minus_generated": reference_minus_generated,
        "symmetric_difference_volume_mm3": (
            generated_minus_reference["aggregate"]["volume_mm3"]
            + reference_minus_generated["aggregate"]["volume_mm3"]
        ),
    }
    path = OUT / "report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
