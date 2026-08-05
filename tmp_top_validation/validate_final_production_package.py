"""Authoritative clean-build validation for the final production package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh

import top_production_export as production
import validate_direct_final_solid as validator
from validate_fast_manifold import topology_split_reference
from validate_feature_tree_manifold import as_mesh

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "reference" / "top.stl"
PRODUCTION_DIR = ROOT / "generated" / "final_top"
VALIDATION_DIR = ROOT / "generated" / "final_authoritative_validation"
REPORT = PRODUCTION_DIR / "final_validation_report.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_triangle_digest(path: Path) -> str:
    mesh = trimesh.load_mesh(path, process=False)
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.to_mesh()
    triangles = np.asarray(mesh.triangles, dtype=np.float64)
    triangles = np.round(triangles, decimals=9)
    canonical = []
    for triangle in triangles:
        ordered = sorted(tuple(float(value) for value in point) for point in triangle)
        canonical.append(tuple(value for point in ordered for value in point))
    canonical.sort()
    array = np.asarray(canonical, dtype=np.float64)
    return hashlib.sha256(array.tobytes()).hexdigest()


def main() -> int:
    PRODUCTION_DIR.mkdir(parents=True, exist_ok=True)
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

    step_path, stl_path, export_audit_path = production.export_production(
        PRODUCTION_DIR
    )

    reference_raw = as_mesh(
        trimesh.load_mesh(REFERENCE, process=True),
        "reference",
    )
    reference, reference_audit, reference_checks = topology_split_reference(
        reference_raw
    )
    if not all(reference_checks.values()):
        raise RuntimeError("Reference topology-preservation audit failed")

    original_close = validator.close_generated_planar_crack
    original_output = validator.OUTPUT
    original_angular_tolerance = validator.ANGULAR_TOLERANCE

    def production_close_and_refine(raw_mesh: trimesh.Trimesh):
        closed, crack_audit = production.close_generated_planar_crack(raw_mesh)
        refined = closed
        bore_audits = []
        for name in production.ADAPTIVE_BORE_NAMES:
            refined, bore_audit = production.refine_cylindrical_bore_wall(
                refined,
                name,
            )
            bore_audits.append(bore_audit)
        return refined, {
            "planar_crack_repair": crack_audit,
            "analytic_bore_wall_refinement": bore_audits,
        }

    try:
        validator.close_generated_planar_crack = production_close_and_refine
        validator.OUTPUT = VALIDATION_DIR
        validator.ANGULAR_TOLERANCE = production.ANGULAR_DEFLECTION_RAD
        result = validator.validate_candidate(
            production.LINEAR_DEFLECTION_MM,
            reference_raw,
            reference,
        )
    finally:
        validator.close_generated_planar_crack = original_close
        validator.OUTPUT = original_output
        validator.ANGULAR_TOLERANCE = original_angular_tolerance

    candidate_dir = VALIDATION_DIR / (
        f"linear_{production.LINEAR_DEFLECTION_MM:.12f}".replace(".", "p")
    )
    validated_stl = candidate_dir / "top_direct_repaired.stl"
    if not validated_stl.exists():
        raise RuntimeError("Authoritative validator did not emit repaired STL")

    production_digest = canonical_triangle_digest(stl_path)
    validation_digest = canonical_triangle_digest(validated_stl)
    triangle_congruent = production_digest == validation_digest

    production_mesh = as_mesh(
        trimesh.load_mesh(stl_path, process=True),
        "production STL",
    )
    validation_mesh = as_mesh(
        trimesh.load_mesh(validated_stl, process=True),
        "authoritative STL",
    )
    scalar_congruent = (
        len(production_mesh.vertices) == len(validation_mesh.vertices)
        and len(production_mesh.faces) == len(validation_mesh.faces)
        and abs(float(production_mesh.volume) - float(validation_mesh.volume))
        <= 1.0e-9
        and abs(float(production_mesh.area) - float(validation_mesh.area))
        <= 1.0e-9
        and float(
            np.linalg.norm(
                np.asarray(production_mesh.center_mass)
                - np.asarray(validation_mesh.center_mass)
            )
        )
        <= 1.0e-9
        and float(
            np.max(
                np.abs(
                    np.asarray(production_mesh.bounds)
                    - np.asarray(validation_mesh.bounds)
                )
            )
        )
        <= 1.0e-9
    )

    final_checks = {
        "strict_srot_source_passed_before_validation": True,
        "reference_topology_preserved": bool(all(reference_checks.values())),
        "production_step_exists": step_path.exists(),
        "production_stl_exists": stl_path.exists(),
        "production_export_audit_exists": export_audit_path.exists(),
        "production_stl_canonical_triangle_congruent": triangle_congruent,
        "production_stl_scalar_congruent": scalar_congruent,
        "authoritative_geometry_strict_pass": bool(result["strict_pass"]),
    }
    overall_pass = all(final_checks.values())

    report = {
        "overall_pass": overall_pass,
        "reference_sha256": sha256(REFERENCE),
        "production_step_sha256": sha256(step_path),
        "production_stl_sha256": sha256(stl_path),
        "authoritative_stl_sha256": sha256(validated_stl),
        "production_stl_canonical_triangle_digest": production_digest,
        "authoritative_stl_canonical_triangle_digest": validation_digest,
        "production_angular_tolerance_rad": production.ANGULAR_DEFLECTION_RAD,
        "authoritative_angular_tolerance_rad": result["angular_tolerance_rad"],
        "reference_topology_audit": reference_audit,
        "reference_topology_checks": reference_checks,
        "production_export_audit": json.loads(
            export_audit_path.read_text(encoding="utf-8")
        ),
        "authoritative_validation": result,
        "final_checks": final_checks,
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
