"""Independent metric and OpenCascade bidirectional Boolean validator."""

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


def shape_valid(shape: Any) -> bool:
    value = getattr(shape, "is_valid", False)
    return bool(value() if callable(value) else value)


def shape_count(shape: Any, name: str) -> int:
    value = getattr(shape, name)
    return len(value() if callable(value) else value)


def total_occt_volume(shape: Any) -> float:
    """Return the absolute volume of an OCCT Shape, including empty results."""
    if shape is None:
        return 0.0
    try:
        value = float(abs(shape.volume))
        if np.isfinite(value):
            return value
    except Exception:
        pass
    try:
        return float(sum(abs(float(solid.volume)) for solid in shape.solids()))
    except Exception as exc:
        raise RuntimeError(f"Unable to calculate OCCT result volume: {exc}") from exc


def occt_symmetric_difference(
    generated_model: Any,
    reference_stl: Path,
) -> dict[str, Any]:
    """Calculate real bidirectional B-Rep differences against the STL solid.

    The immutable STL is imported by Build123d's OpenCascade Mesher.  This
    preserves every source triangle as a planar B-Rep face and avoids imposing
    a manifold-mesh prerequisite on the reference's known tangency singularity.
    """
    from build123d import Mesher

    imported = Mesher().read(reference_stl)
    if len(imported) != 1:
        raise RuntimeError(
            f"Expected one OpenCascade reference shape, imported {len(imported)}"
        )
    reference_shape = imported[0]
    reference_valid = shape_valid(reference_shape)
    reference_solids = shape_count(reference_shape, "solids")
    if not reference_valid or reference_solids != 1:
        raise RuntimeError(
            "Reference did not import as one valid OpenCascade solid: "
            f"valid={reference_valid}, solids={reference_solids}"
        )

    generated_valid = shape_valid(generated_model)
    generated_solids = shape_count(generated_model, "solids")
    if not generated_valid or generated_solids != 1:
        raise RuntimeError(
            "Generated model is not one valid OpenCascade solid: "
            f"valid={generated_valid}, solids={generated_solids}"
        )

    generated_minus_reference = generated_model.cut(reference_shape)
    reference_minus_generated = reference_shape.cut(generated_model)

    generated_minus_reference_volume = total_occt_volume(
        generated_minus_reference
    )
    reference_minus_generated_volume = total_occt_volume(
        reference_minus_generated
    )

    return {
        "reference_import_count": len(imported),
        "reference_occt_valid": reference_valid,
        "reference_occt_solid_count": reference_solids,
        "reference_occt_volume_mm3": float(reference_shape.volume),
        "reference_occt_area_mm2": float(reference_shape.area),
        "generated_occt_valid": generated_valid,
        "generated_occt_solid_count": generated_solids,
        "generated_minus_reference_valid": shape_valid(
            generated_minus_reference
        ),
        "reference_minus_generated_valid": shape_valid(
            reference_minus_generated
        ),
        "generated_minus_reference_volume_mm3": (
            generated_minus_reference_volume
        ),
        "reference_minus_generated_volume_mm3": (
            reference_minus_generated_volume
        ),
        "symmetric_difference_volume_mm3": (
            generated_minus_reference_volume
            + reference_minus_generated_volume
        ),
    }


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

    occt_boolean = occt_symmetric_difference(model, reference_stl)
    symmetric_difference_volume = float(
        occt_boolean["symmetric_difference_volume_mm3"]
    )
    symmetric_difference_percent = symmetric_difference_volume / ref_volume * 100.0

    metrics = {
        "reference_sha256": reference_sha256,
        "reference_raw_mesh_watertight": bool(reference.is_watertight),
        "generated_stl_watertight": bool(generated.is_watertight),
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
        "occt_boolean": occt_boolean,
    }
    checks = {
        "reference_checksum": reference_sha256 == EXPECTED_REFERENCE_SHA256,
        "reference_occt_single_valid_solid": (
            occt_boolean["reference_occt_valid"]
            and occt_boolean["reference_occt_solid_count"] == 1
        ),
        "generated_occt_single_valid_solid": (
            occt_boolean["generated_occt_valid"]
            and occt_boolean["generated_occt_solid_count"] == 1
        ),
        "generated_stl_watertight": bool(generated.is_watertight),
        "directional_booleans_valid": (
            occt_boolean["generated_minus_reference_valid"]
            and occt_boolean["reference_minus_generated_valid"]
        ),
        "volume": metrics["volume_difference_percent"] < 0.1,
        "surface_area": metrics["area_difference_percent"] < 0.1,
        "center_of_mass": metrics["com_shift_percent_of_bbox_diagonal"] < 0.1,
        "symmetric_difference": metrics["symmetric_difference_percent"] < 0.01,
    }
    report = {
        "reference": str(reference_stl.resolve()),
        "generated_stl": str(generated_stl.resolve()),
        "boolean_engine": (
            "Build123d/OpenCascade bidirectional regularized B-Rep difference"
        ),
        "reference_topology_note": (
            "The immutable STL has a known raw-mesh tangency singularity; "
            "its checksum-verified OpenCascade import is one valid solid."
        ),
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
