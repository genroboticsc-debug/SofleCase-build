"""Partition the best direct-solid Boolean residual by exact feature boxes."""

from __future__ import annotations

import json

import numpy as np
import trimesh

import validate_direct_final_solid as validator
from validate_fast_manifold import topology_split_reference
from validate_feature_tree_manifold import as_mesh

LINEAR = 0.006722
ANGULAR = 0.270
ROOT = validator.ROOT / "generated" / "direct_residual_partition"
CANDIDATE = ROOT / "candidate"
ROOT.mkdir(parents=True, exist_ok=True)
validator.OUTPUT = CANDIDATE
validator.ANGULAR_TOLERANCE = ANGULAR

reference_raw = as_mesh(trimesh.load_mesh(validator.REFERENCE, process=True), "reference")
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference topology audit failed")

candidate = validator.validate_candidate(LINEAR, reference_raw, reference)
result_dir = CANDIDATE / f"linear_{LINEAR:.12f}".replace(".", "p")
gmr = as_mesh(trimesh.load_mesh(result_dir / "generated_minus_reference.stl", process=True), "generated minus reference")
rmg = as_mesh(trimesh.load_mesh(result_dir / "reference_minus_generated.stl", process=True), "reference minus generated")


def aggregate_volume(mesh: trimesh.Trimesh | None) -> float:
    """Use the oriented aggregate volume retained by Manifold's closed shell set."""
    if mesh is None or len(mesh.faces) == 0:
        return 0.0
    return float(abs(mesh.volume))


def clipped_volume(mesh: trimesh.Trimesh, lower, upper, label: str) -> float:
    lower_array = np.asarray(lower, dtype=float)
    upper_array = np.asarray(upper, dtype=float)
    box = trimesh.creation.box(
        extents=upper_array - lower_array,
        transform=trimesh.transformations.translation_matrix(
            (upper_array + lower_array) / 2.0
        ),
    )
    clipped = trimesh.boolean.intersection(
        [mesh, box],
        engine="manifold",
        check_volume=False,
    )
    if clipped is None:
        volume = 0.0
    else:
        if isinstance(clipped, trimesh.Scene):
            clipped = clipped.to_mesh()
        volume = aggregate_volume(clipped)
    print(json.dumps({"clip": label, "volume_mm3": volume}), flush=True)
    return volume


def partition(mesh: trimesh.Trimesh, direction: str) -> dict:
    y_bins = [55.9, 57.5, 61.0, 62.5, 63.5, 64.2, 65.2, 67.3]
    y_slabs = [
        {
            "y_low": low,
            "y_high": high,
            "volume_mm3": clipped_volume(
                mesh,
                [-26.4, low, -34.8],
                [17.8, high, 15.0],
                f"{direction} y {low} {high}",
            ),
        }
        for low, high in zip(y_bins[:-1], y_bins[1:])
    ]

    x_bins = [-26.4, -20.0, -13.0, -6.0, 1.0, 8.0, 17.8]
    z_bins = [-34.8, -27.0, -19.0, -11.0, -3.0, 5.0, 15.0]
    xz_cells = []
    for x_low, x_high in zip(x_bins[:-1], x_bins[1:]):
        for z_low, z_high in zip(z_bins[:-1], z_bins[1:]):
            xz_cells.append(
                {
                    "x_low": x_low,
                    "x_high": x_high,
                    "z_low": z_low,
                    "z_high": z_high,
                    "volume_mm3": clipped_volume(
                        mesh,
                        [x_low, 55.9, z_low],
                        [x_high, 67.3, z_high],
                        f"{direction} x {x_low} {x_high} z {z_low} {z_high}",
                    ),
                }
            )

    feature_boxes = {
        "bottom_left_boss_corner": ([-22.0, 55.9, -35.0], [-10.0, 64.3, -24.0]),
        "bottom_right_boss_corner": ([6.0, 55.9, -35.0], [17.8, 64.3, -24.0]),
        "top_right_boss_corner": ([8.0, 55.9, 5.0], [17.8, 67.3, 15.0]),
        "engraving": ([-26.4, 62.49, 5.0], [-10.0, 63.51, 15.0]),
        "main_opening_left_half": ([-26.4, 60.9, -32.3], [-4.78930378, 67.3, 11.0]),
        "main_opening_right_half": ([-4.78930378, 60.9, -32.3], [16.8, 67.3, 11.0]),
        "top_fillet_full": ([-26.4, 65.19, -34.8], [17.8, 67.3, 15.0]),
    }
    features = {
        name: clipped_volume(mesh, lower, upper, f"{direction} {name}")
        for name, (lower, upper) in feature_boxes.items()
    }

    return {
        "total_volume_mm3": aggregate_volume(mesh),
        "y_slabs": y_slabs,
        "y_slab_sum_mm3": float(sum(item["volume_mm3"] for item in y_slabs)),
        "xz_cells": xz_cells,
        "xz_cell_sum_mm3": float(sum(item["volume_mm3"] for item in xz_cells)),
        "feature_boxes": features,
    }


report = {
    "linear_tolerance_mm": LINEAR,
    "angular_tolerance_rad": ANGULAR,
    "candidate_validation": candidate,
    "reference_topology_audit": topology_audit,
    "reference_topology_checks": topology_checks,
    "generated_minus_reference": partition(gmr, "generated_minus_reference"),
    "reference_minus_generated": partition(rmg, "reference_minus_generated"),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2), flush=True)
