"""Test OCCT relative deflection on the immutable analytic final solid."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.StlAPI import StlAPI_Writer

import top_parametric as tp
import validate_direct_final_solid as validator
from validate_fast_manifold import topology_split_reference
from validate_feature_tree_manifold import as_mesh, mesh_stats

LINEAR_COEFFICIENTS = (
    0.000075,
    0.000085,
    0.000095,
    0.000100,
    0.000105,
    0.000115,
    0.000130,
)
ANGULAR_VALUES = (0.14, 0.18, 0.22, 0.27, 0.32, 0.40, 0.60)
BOOLEAN_LIMIT = 18
REFERENCE_FACE_COUNT = 7044
ROOT = validator.ROOT / "generated" / "relative_final_solid_sweep"
MESH_ROOT = ROOT / "meshes"
BOOLEAN_ROOT = ROOT / "booleans"
MESH_ROOT.mkdir(parents=True, exist_ok=True)
BOOLEAN_ROOT.mkdir(parents=True, exist_ok=True)


def robust_close(mesh: trimesh.Trimesh):
    """Use only generated topology to remove exact zero-area STL artifacts."""
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    area_faces = np.asarray(mesh.area_faces, dtype=float)
    zero_faces = np.where(area_faces <= 1.0e-14)[0]
    if len(zero_faces) == 0:
        if mesh.is_watertight and mesh.is_winding_consistent and mesh.is_volume:
            return mesh, {
                "method": "no repair required",
                "removed_zero_area_face_indices": [],
                "source_face_count": int(len(faces)),
                "final_face_count": int(len(faces)),
            }
        return validator.close_generated_planar_crack(mesh)

    keep = np.ones(len(faces), dtype=bool)
    keep[zero_faces] = False
    candidate = trimesh.Trimesh(
        vertices=vertices.copy(),
        faces=faces[keep].copy(),
        process=False,
        validate=False,
    )
    incidence = validator.edge_incidence(candidate.faces)
    abnormal = {edge: len(owners) for edge, owners in incidence.items() if len(owners) != 2}

    def finalize(closed: trimesh.Trimesh, method: str):
        trimesh.repair.fix_winding(closed)
        components = list(closed.split(only_watertight=False))
        if not (
            closed.is_watertight
            and closed.is_winding_consistent
            and closed.is_volume
            and len(components) == 1
        ):
            raise RuntimeError(f"{method} did not produce one valid volume")
        return closed, {
            "method": method,
            "removed_zero_area_face_indices": [int(value) for value in zero_faces],
            "removed_zero_area_mm2": float(np.sum(area_faces[zero_faces])),
            "source_face_count": int(len(faces)),
            "final_face_count": int(len(closed.faces)),
            "existing_vertex_coordinate_max_abs_delta_mm": 0.0,
            "added_vertex_count": int(len(closed.vertices) - len(vertices)),
            "final_watertight": bool(closed.is_watertight),
            "final_winding_consistent": bool(closed.is_winding_consistent),
            "final_is_volume": bool(closed.is_volume),
            "final_component_count": len(components),
        }

    if not abnormal:
        return finalize(candidate, "generated-only removal of exact zero-area triangles")

    filled = candidate.copy()
    trimesh.repair.fill_holes(filled)
    filled_abnormal = {
        edge: len(owners)
        for edge, owners in validator.edge_incidence(filled.faces).items()
        if len(owners) != 2
    }
    if not filled_abnormal:
        return finalize(filled, "generated-only zero-area removal plus planar hole fill")

    if len(zero_faces) == 1:
        return validator.close_generated_planar_crack(mesh)
    raise RuntimeError(
        "Relative mesh topology repair unresolved: "
        f"zero_faces={len(zero_faces)}, abnormal={len(abnormal)}, "
        f"filled_abnormal={len(filled_abnormal)}"
    )


def mesh_relative(linear: float, angular: float, output_path: Path):
    model = tp.build_top()
    if len(model.solids()) != 1 or not model.is_valid:
        raise RuntimeError("Analytic model is not one valid solid")
    mesher = BRepMesh_IncrementalMesh(
        model.wrapped,
        linear,
        True,
        angular,
        True,
    )
    mesher.Perform()
    if not mesher.IsDone():
        raise RuntimeError("Relative OCCT meshing failed")
    writer = StlAPI_Writer()
    writer.ASCIIMode = False
    if not writer.Write(model.wrapped, str(output_path)):
        raise RuntimeError("Relative OCCT STL write failed")
    raw = as_mesh(trimesh.load_mesh(output_path, process=True), "relative raw")
    return model, *robust_close(raw)


reference_raw = as_mesh(trimesh.load_mesh(validator.REFERENCE, process=True), "reference")
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference topology audit failed")
reference_volume = abs(float(reference_raw.volume))
reference_area = abs(float(reference_raw.area))
reference_diagonal = float(np.linalg.norm(reference_raw.extents))

scan_rows = []
for linear in LINEAR_COEFFICIENTS:
    for angular in ANGULAR_VALUES:
        tag = f"rel_{linear:.9f}_ang_{angular:.6f}".replace(".", "p")
        raw_path = MESH_ROOT / f"{tag}_raw.stl"
        repaired_path = MESH_ROOT / f"{tag}_repaired.stl"
        print(f"=== relative mesh linear={linear:.9f} angular={angular:.6f} ===", flush=True)
        try:
            model, generated, repair_audit = mesh_relative(linear, angular, raw_path)
            generated.export(repaired_path)
            stats = mesh_stats(generated)
            volume_error = abs(generated.volume - reference_raw.volume) / reference_volume * 100.0
            area_error = abs(generated.area - reference_raw.area) / reference_area * 100.0
            com_shift = float(np.linalg.norm(np.asarray(generated.center_mass) - np.asarray(reference_raw.center_mass)))
            face_error = abs(len(generated.faces) - REFERENCE_FACE_COUNT) / REFERENCE_FACE_COUNT
            rank_score = (
                face_error
                + volume_error / 100.0
                + area_error / 100.0
                + com_shift / reference_diagonal
            )
            row = {
                "linear_coefficient": linear,
                "angular_tolerance_rad": angular,
                "relative_deflection": True,
                "analytic_model_valid": bool(model.is_valid),
                "repair_audit": repair_audit,
                "generated_stats": stats,
                "volume_difference_percent": volume_error,
                "area_difference_percent": area_error,
                "com_shift_mm": com_shift,
                "com_shift_percent_bbox_diagonal": com_shift / reference_diagonal * 100.0,
                "face_count_delta": int(len(generated.faces) - REFERENCE_FACE_COUNT),
                "rank_score": rank_score,
                "repaired_mesh_path": str(repaired_path),
            }
        except Exception as exc:
            row = {
                "linear_coefficient": linear,
                "angular_tolerance_rad": angular,
                "relative_deflection": True,
                "exception": repr(exc),
            }
        scan_rows.append(row)
        print(json.dumps(row, indent=2), flush=True)

valid_scan = [row for row in scan_rows if "rank_score" in row]
valid_scan.sort(key=lambda row: row["rank_score"])
selected = valid_scan[:BOOLEAN_LIMIT]

# Ensure representation of distinct face-count plateaus near the reference.
by_faces = {}
for row in valid_scan:
    faces = row["generated_stats"]["faces"]
    by_faces.setdefault(faces, row)
for row in sorted(by_faces.values(), key=lambda item: abs(item["face_count_delta"]))[:8]:
    if row not in selected:
        selected.append(row)

boolean_rows = []
for row in selected:
    linear = row["linear_coefficient"]
    angular = row["angular_tolerance_rad"]
    tag = f"rel_{linear:.9f}_ang_{angular:.6f}".replace(".", "p")
    output = BOOLEAN_ROOT / tag
    output.mkdir(parents=True, exist_ok=True)
    print(f"=== relative Boolean linear={linear:.9f} angular={angular:.6f} ===", flush=True)
    try:
        generated = as_mesh(
            trimesh.load_mesh(row["repaired_mesh_path"], process=True),
            f"relative repaired {tag}",
        )
        gmr, gmr_stats = validator.directional_difference(
            generated, reference, "generated_minus_reference", output
        )
        rmg, rmg_stats = validator.directional_difference(
            reference, generated, "reference_minus_generated", output
        )
        symmetric = gmr + rmg
        result = dict(row)
        result.update(
            {
                "generated_minus_reference_mm3": gmr,
                "reference_minus_generated_mm3": rmg,
                "symmetric_difference_mm3": symmetric,
                "symmetric_difference_percent": symmetric / reference_volume * 100.0,
                "generated_minus_reference_stats": gmr_stats,
                "reference_minus_generated_stats": rmg_stats,
            }
        )
        result["checks"] = {
            "analytic_single_valid_solid": bool(result["analytic_model_valid"]),
            "generated_watertight": bool(generated.is_watertight),
            "generated_winding_consistent": bool(generated.is_winding_consistent),
            "generated_is_volume": bool(generated.is_volume),
            "symmetric_difference_below_0p01_percent": bool(result["symmetric_difference_percent"] < 0.01),
            "volume_difference_below_0p1_percent": bool(result["volume_difference_percent"] < 0.1),
            "area_difference_below_0p1_percent": bool(result["area_difference_percent"] < 0.1),
            "com_shift_below_0p1_percent_bbox_diagonal": bool(result["com_shift_percent_bbox_diagonal"] < 0.1),
        }
        result["strict_pass"] = all(result["checks"].values())
    except Exception as exc:
        result = dict(row)
        result.update({"strict_pass": False, "boolean_exception": repr(exc)})
    boolean_rows.append(result)
    print(json.dumps(result, indent=2), flush=True)

valid_boolean = [row for row in boolean_rows if "symmetric_difference_percent" in row]
valid_boolean.sort(key=lambda row: row["symmetric_difference_percent"])
report = {
    "reference_topology_audit": topology_audit,
    "reference_topology_checks": topology_checks,
    "scan_candidates": scan_rows,
    "boolean_candidates": boolean_rows,
    "best": valid_boolean[0] if valid_boolean else None,
    "overall_pass": bool(valid_boolean and valid_boolean[0]["strict_pass"]),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== RELATIVE FINAL-SOLID SWEEP RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
