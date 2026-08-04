"""Independent metric and exact-polyhedral Boolean validator for top_parametric.py."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from top_parametric import build_top

EXPECTED_REFERENCE_SHA256 = "d9cd3e5cae398287140e92136a87a7aa1ed6ec4433434fca0cf0b661ca869cac"


def percent_error(generated: float, reference: float) -> float:
    return abs(generated - reference) / abs(reference) * 100.0


def as_vector3(value: Any) -> np.ndarray:
    if hasattr(value, "X"):
        return np.array([value.X, value.Y, value.Z], dtype=float)
    return np.asarray(value, dtype=float).reshape(3)


def mesh_volume(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, trimesh.Scene):
        value = value.dump(concatenate=True)
    if isinstance(value, (list, tuple)):
        return float(sum(abs(mesh.volume) for mesh in value))
    return float(abs(value.volume))


def manifold_symmetric_difference_volume(
    generated_stl: Path,
    reference_stl: Path,
) -> float:
    generated = trimesh.load_mesh(generated_stl, process=True)
    reference = trimesh.load_mesh(reference_stl, process=True)
    if not isinstance(generated, trimesh.Trimesh):
        raise RuntimeError("Generated STL is not a single Trimesh")
    if not isinstance(reference, trimesh.Trimesh):
        raise RuntimeError("Reference STL is not a single Trimesh")
    if not generated.is_watertight or not reference.is_watertight:
        raise RuntimeError(
            f"Boolean inputs must be watertight: generated={generated.is_watertight}, "
            f"reference={reference.is_watertight}"
        )
    generated_minus_reference = trimesh.boolean.difference(
        [generated, reference], engine="manifold"
    )
    reference_minus_generated = trimesh.boolean.difference(
        [reference, generated], engine="manifold"
    )
    return mesh_volume(generated_minus_reference) + mesh_volume(reference_minus_generated)


def validate(reference_stl: Path, output_dir: Path) -> dict[str, Any]:
    from build123d import CenterOf, export_stl

    output_dir.mkdir(parents=True, exist_ok=True)
    reference_bytes = reference_stl.read_bytes()
    reference_sha256 = hashlib.sha256(reference_bytes).hexdigest()
    if reference_sha256 != EXPECTED_REFERENCE_SHA256:
        raise RuntimeError(
            "Reference STL checksum mismatch: "
            f"expected {EXPECTED_REFERENCE_SHA256}, got {reference_sha256}"
        )

    reference = trimesh.load_mesh(reference_stl, process=True)
    if not isinstance(reference, trimesh.Trimesh):
        raise RuntimeError("Reference STL did not load as one Trimesh")

    model = build_top()
    generated_stl = output_dir / "top_parametric_validation.stl"
    export_stl(
        model,
        generated_stl,
        tolerance=0.001,
        angular_tolerance=0.1,
        ascii_format=False,
    )
    generated = trimesh.load_mesh(generated_stl, process=True)
    if not isinstance(generated, trimesh.Trimesh):
        raise RuntimeError("Generated STL did not load as one Trimesh")

    ref_volume = float(abs(reference.volume))
    gen_volume = float(model.volume)
    ref_area = float(reference.area)
    gen_area = float(model.area)
    ref_com = np.asarray(reference.center_mass, dtype=float)
    gen_com = as_vector3(model.center(CenterOf.MASS))
    ref_bounds = np.asarray(reference.bounds, dtype=float)
    model_bbox = model.bounding_box()
    gen_bounds = np.array(
        [
            [model_bbox.min.X, model_bbox.min.Y, model_bbox.min.Z],
            [model_bbox.max.X, model_bbox.max.Y, model_bbox.max.Z],
        ],
        dtype=float,
    )
    bbox_diagonal = float(np.linalg.norm(ref_bounds[1] - ref_bounds[0]))
    com_shift_mm = float(np.linalg.norm(gen_com - ref_com))
    com_shift_percent = com_shift_mm / bbox_diagonal * 100.0

    symmetric_difference_volume = manifold_symmetric_difference_volume(
        generated_stl,
        reference_stl,
    )
    symmetric_difference_percent = symmetric_difference_volume / ref_volume * 100.0

    metrics = {
        "reference_sha256": reference_sha256,
        "reference_watertight": bool(reference.is_watertight),
        "generated_watertight": bool(generated.is_watertight),
        "reference_volume_mm3": ref_volume,
        "generated_volume_mm3": gen_volume,
        "volume_difference_mm3": gen_volume - ref_volume,
        "volume_difference_percent": percent_error(gen_volume, ref_volume),
        "reference_area_mm2": ref_area,
        "generated_area_mm2": gen_area,
        "area_difference_mm2": gen_area - ref_area,
        "area_difference_percent": percent_error(gen_area, ref_area),
        "reference_com_mm": ref_com.tolist(),
        "generated_com_mm": gen_com.tolist(),
        "com_delta_mm": (gen_com - ref_com).tolist(),
        "com_shift_mm": com_shift_mm,
        "com_shift_percent_of_bbox_diagonal": com_shift_percent,
        "reference_bbox_mm": ref_bounds.tolist(),
        "generated_bbox_mm": gen_bounds.tolist(),
        "bbox_absolute_delta_mm": np.abs(gen_bounds - ref_bounds).tolist(),
        "symmetric_difference_volume_mm3": symmetric_difference_volume,
        "symmetric_difference_percent": symmetric_difference_percent,
    }
    checks = {
        "reference_checksum": reference_sha256 == EXPECTED_REFERENCE_SHA256,
        "reference_watertight": bool(reference.is_watertight),
        "generated_watertight": bool(generated.is_watertight),
        "volume": metrics["volume_difference_percent"] < 0.1,
        "surface_area": metrics["area_difference_percent"] < 0.1,
        "center_of_mass": metrics["com_shift_percent_of_bbox_diagonal"] < 0.1,
        "symmetric_difference": metrics["symmetric_difference_percent"] < 0.01,
    }
    report = {
        "reference": str(reference_stl.resolve()),
        "generated_stl": str(generated_stl.resolve()),
        "boolean_engine": "manifold3d exact-polyhedral bidirectional difference",
        "thresholds": {
            "volume_difference_percent_max": 0.1,
            "surface_area_difference_percent_max": 0.1,
            "com_shift_percent_of_bbox_diagonal_max": 0.1,
            "symmetric_difference_percent_max": 0.01,
        },
        "metrics": metrics,
        "checks": checks,
        "overall_pass": all(checks.values()),
    }
    (output_dir / "validation_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reference",
        type=Path,
        default=Path(__file__).resolve().parent / "reference" / "top.stl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "generated",
    )
    args = parser.parse_args()
    report = validate(args.reference, args.output_dir)
    print(json.dumps(report, indent=2))
    if report["overall_pass"]:
        print("PASS: every requested threshold is satisfied.")
        return 0
    print("FAIL: one or more requested thresholds are not satisfied.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
