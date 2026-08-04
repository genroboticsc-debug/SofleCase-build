"""Fast strict validation using OpenCascade sewing + Manifold3D Boolean.

The immutable reference STL is checksum-verified, imported as one valid
OpenCascade solid, and re-exported solely to restore shared topology across the
known tangent edge.  Geometry preservation is audited before any Boolean.
The parametric generator remains independent and is audited separately by the
Strict SROT checker.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from build123d import CenterOf, Mesher, export_stl

from strict_srot_check import run as run_srot
from top_parametric import build_top, export_model

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "reference" / "top.stl"
GENERATED = ROOT / "generated"
EXPECTED_SHA256 = "d9cd3e5cae398287140e92136a87a7aa1ed6ec4433434fca0cf0b661ca869cac"


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def vector3(value: Any) -> np.ndarray:
    if hasattr(value, "X"):
        return np.array([value.X, value.Y, value.Z], dtype=float)
    return np.asarray(value, dtype=float).reshape(3)


def pct(delta: float, reference: float) -> float:
    return abs(delta) / abs(reference) * 100.0


def mesh_volume(mesh: trimesh.Trimesh | None) -> float:
    if mesh is None:
        return 0.0
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)
    if not isinstance(mesh, trimesh.Trimesh):
        raise RuntimeError(f"Unexpected Boolean result type: {type(mesh)!r}")
    return float(abs(mesh.volume))


def main() -> int:
    GENERATED.mkdir(parents=True, exist_ok=True)
    report_path = GENERATED / "fast_validation_report.json"

    reference_sha = hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
    if reference_sha != EXPECTED_SHA256:
        raise RuntimeError(
            f"Reference checksum mismatch: expected {EXPECTED_SHA256}, got {reference_sha}"
        )

    log("Running machine-enforced Strict SROT audit")
    srot = run_srot(GENERATED / "strict_srot_report.json")
    if not srot["pass"]:
        raise RuntimeError("Strict SROT audit failed")

    log("Loading immutable reference metrics")
    reference_raw = trimesh.load_mesh(REFERENCE, process=True)
    if not isinstance(reference_raw, trimesh.Trimesh):
        raise RuntimeError("Reference did not load as one Trimesh")

    log("Importing checksum-verified STL as one OpenCascade solid")
    imported = Mesher().read(REFERENCE)
    if len(imported) != 1:
        raise RuntimeError(f"Expected one imported shape, got {len(imported)}")
    reference_shape = imported[0]
    if not reference_shape.is_valid or len(reference_shape.solids()) != 1:
        raise RuntimeError("Reference is not one valid OpenCascade solid")

    regularized_path = GENERATED / "reference_occt_sewn.stl"
    log("Exporting topology-sewn reference triangle solid")
    export_stl(
        reference_shape,
        regularized_path,
        tolerance=1.0e-6,
        angular_tolerance=0.01,
        ascii_format=False,
    )
    reference_sewn = trimesh.load_mesh(regularized_path, process=True)
    if not isinstance(reference_sewn, trimesh.Trimesh):
        raise RuntimeError("Sewn reference did not load as one Trimesh")

    ref_raw_bounds = np.asarray(reference_raw.bounds, dtype=float)
    ref_sewn_bounds = np.asarray(reference_sewn.bounds, dtype=float)
    ref_raw_com = np.asarray(reference_raw.center_mass, dtype=float)
    ref_sewn_com = np.asarray(reference_sewn.center_mass, dtype=float)
    sewing_audit = {
        "raw_watertight": bool(reference_raw.is_watertight),
        "sewn_watertight": bool(reference_sewn.is_watertight),
        "raw_faces": int(len(reference_raw.faces)),
        "sewn_faces": int(len(reference_sewn.faces)),
        "raw_volume_mm3": float(abs(reference_raw.volume)),
        "sewn_volume_mm3": float(abs(reference_sewn.volume)),
        "volume_delta_mm3": float(abs(reference_sewn.volume) - abs(reference_raw.volume)),
        "volume_delta_percent": pct(
            float(abs(reference_sewn.volume) - abs(reference_raw.volume)),
            float(abs(reference_raw.volume)),
        ),
        "raw_area_mm2": float(reference_raw.area),
        "sewn_area_mm2": float(reference_sewn.area),
        "area_delta_mm2": float(reference_sewn.area - reference_raw.area),
        "area_delta_percent": pct(
            float(reference_sewn.area - reference_raw.area),
            float(reference_raw.area),
        ),
        "com_shift_mm": float(np.linalg.norm(ref_sewn_com - ref_raw_com)),
        "bbox_max_abs_delta_mm": float(
            np.max(np.abs(ref_sewn_bounds - ref_raw_bounds))
        ),
    }
    sewing_checks = {
        "occt_reference_single_valid_solid": bool(
            reference_shape.is_valid and len(reference_shape.solids()) == 1
        ),
        "sewn_reference_watertight": bool(reference_sewn.is_watertight),
        "triangle_count_preserved": len(reference_sewn.faces) == len(reference_raw.faces),
        "volume_preserved": sewing_audit["volume_delta_percent"] < 1.0e-6,
        "area_preserved": sewing_audit["area_delta_percent"] < 1.0e-6,
        "com_preserved": sewing_audit["com_shift_mm"] < 1.0e-6,
        "bounds_preserved": sewing_audit["bbox_max_abs_delta_mm"] < 1.0e-6,
    }
    if not all(sewing_checks.values()):
        partial = {
            "reference_sha256": reference_sha,
            "strict_srot": srot,
            "sewing_audit": sewing_audit,
            "sewing_checks": sewing_checks,
            "overall_pass": False,
        }
        report_path.write_text(json.dumps(partial, indent=2), encoding="utf-8")
        raise RuntimeError("OpenCascade topology sewing changed reference geometry")

    log("Building and exporting complete F001-F012 parametric model")
    step_path, stl_path = export_model(GENERATED)
    model = build_top()
    generated_mesh = trimesh.load_mesh(stl_path, process=True)
    if not isinstance(generated_mesh, trimesh.Trimesh):
        raise RuntimeError("Generated STL did not load as one Trimesh")
    if not model.is_valid or len(model.solids()) != 1:
        raise RuntimeError("Generated CAD is not one valid solid")

    ref_volume = float(abs(reference_raw.volume))
    ref_area = float(reference_raw.area)
    ref_com = np.asarray(reference_raw.center_mass, dtype=float)
    gen_volume = float(model.volume)
    gen_area = float(model.area)
    gen_com = vector3(model.center(CenterOf.MASS))
    bbox_diagonal = float(np.linalg.norm(ref_raw_bounds[1] - ref_raw_bounds[0]))

    log("Computing generated-minus-reference Manifold3D difference")
    generated_minus_reference = trimesh.boolean.difference(
        [generated_mesh, reference_sewn],
        engine="manifold",
        check_volume=True,
    )
    log("Computing reference-minus-generated Manifold3D difference")
    reference_minus_generated = trimesh.boolean.difference(
        [reference_sewn, generated_mesh],
        engine="manifold",
        check_volume=True,
    )

    gen_minus_ref_volume = mesh_volume(generated_minus_reference)
    ref_minus_gen_volume = mesh_volume(reference_minus_generated)
    symmetric_volume = gen_minus_ref_volume + ref_minus_gen_volume
    com_shift_mm = float(np.linalg.norm(gen_com - ref_com))

    metrics = {
        "reference_volume_mm3": ref_volume,
        "generated_volume_mm3": gen_volume,
        "volume_difference_mm3": gen_volume - ref_volume,
        "volume_difference_percent": pct(gen_volume - ref_volume, ref_volume),
        "reference_area_mm2": ref_area,
        "generated_area_mm2": gen_area,
        "area_difference_mm2": gen_area - ref_area,
        "area_difference_percent": pct(gen_area - ref_area, ref_area),
        "reference_com_mm": ref_com.tolist(),
        "generated_com_mm": gen_com.tolist(),
        "com_delta_mm": (gen_com - ref_com).tolist(),
        "com_shift_mm": com_shift_mm,
        "com_shift_percent_of_bbox_diagonal": com_shift_mm / bbox_diagonal * 100.0,
        "reference_bbox_mm": ref_raw_bounds.tolist(),
        "generated_bbox_mm": np.asarray(generated_mesh.bounds, dtype=float).tolist(),
        "generated_minus_reference_volume_mm3": gen_minus_ref_volume,
        "reference_minus_generated_volume_mm3": ref_minus_gen_volume,
        "symmetric_difference_volume_mm3": symmetric_volume,
        "symmetric_difference_percent": symmetric_volume / ref_volume * 100.0,
    }
    checks = {
        "strict_srot": bool(srot["pass"]),
        "reference_checksum": reference_sha == EXPECTED_SHA256,
        "reference_sewing_audit": all(sewing_checks.values()),
        "generated_cad_single_valid_solid": bool(
            model.is_valid and len(model.solids()) == 1
        ),
        "generated_stl_watertight": bool(generated_mesh.is_watertight),
        "volume": metrics["volume_difference_percent"] < 0.1,
        "surface_area": metrics["area_difference_percent"] < 0.1,
        "center_of_mass": metrics["com_shift_percent_of_bbox_diagonal"] < 0.1,
        "symmetric_difference": metrics["symmetric_difference_percent"] < 0.01,
    }
    report = {
        "reference_sha256": reference_sha,
        "generator": str((ROOT / "top_parametric.py").resolve()),
        "generated_step": str(step_path.resolve()),
        "generated_stl": str(stl_path.resolve()),
        "boolean_engine": "Manifold3D via Trimesh, two directional differences",
        "reference_regularization": (
            "Checksum-verified STL imported as one valid OpenCascade solid and "
            "re-exported with original planar triangle geometry; preservation "
            "audited before Boolean."
        ),
        "thresholds": {
            "volume_difference_percent_max": 0.1,
            "surface_area_difference_percent_max": 0.1,
            "com_shift_percent_of_bbox_diagonal_max": 0.1,
            "symmetric_difference_percent_max": 0.01,
        },
        "strict_srot": srot,
        "sewing_audit": sewing_audit,
        "sewing_checks": sewing_checks,
        "metrics": metrics,
        "checks": checks,
        "overall_pass": all(checks.values()),
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(json.dumps(report, indent=2))
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
