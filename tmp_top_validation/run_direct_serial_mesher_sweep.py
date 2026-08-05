"""Sweep serial OCCT final-solid tessellation without changing CAD geometry."""

from __future__ import annotations

import json

import numpy as np
import trimesh
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.StlAPI import StlAPI_Writer

import top_parametric as tp
import validate_direct_final_solid as validator
from validate_fast_manifold import topology_split_reference
from validate_feature_tree_manifold import as_mesh

LINEAR_VALUES = (0.00668, 0.006722, 0.00676)
ANGULAR_VALUES = (0.18, 0.20, 0.21, 0.22, 0.225, 0.23, 0.24, 0.25, 0.27, 0.30, 0.60)
ROOT = validator.ROOT / "generated" / "direct_serial_mesher_sweep"
ROOT.mkdir(parents=True, exist_ok=True)
ORIGINAL_CLOSE = validator.close_generated_planar_crack


def export_serial_final_solid(linear: float, path):
    model = tp.build_top()
    if len(model.solids()) != 1 or not model.is_valid:
        raise RuntimeError("Analytic F001-F012 model is not one valid solid")
    mesher = BRepMesh_IncrementalMesh(
        model.wrapped,
        linear,
        False,
        validator.ANGULAR_TOLERANCE,
        False,
    )
    mesher.Perform()
    if not mesher.IsDone():
        raise RuntimeError("Serial OCCT final-solid meshing failed")
    writer = StlAPI_Writer()
    writer.ASCIIMode = False
    if not writer.Write(model.wrapped, str(path)):
        raise RuntimeError("Serial OCCT final-solid STL write failed")
    return model


def close_zero_face_or_planar_crack(mesh: trimesh.Trimesh):
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    area_faces = np.asarray(mesh.area_faces, dtype=float)
    zero_faces = np.where(area_faces <= 1.0e-14)[0]
    if len(zero_faces) != 1:
        return ORIGINAL_CLOSE(mesh)
    keep = np.ones(len(faces), dtype=bool)
    keep[zero_faces] = False
    retained_faces = faces[keep]
    incidence = validator.edge_incidence(retained_faces)
    boundary_edges = [edge for edge, owners in incidence.items() if len(owners) == 1]
    other_abnormal = {
        edge: len(owners)
        for edge, owners in incidence.items()
        if len(owners) not in (1, 2)
    }
    if boundary_edges or other_abnormal:
        return ORIGINAL_CLOSE(mesh)
    closed = trimesh.Trimesh(
        vertices=vertices.copy(),
        faces=retained_faces.copy(),
        process=False,
        validate=False,
    )
    trimesh.repair.fix_winding(closed)
    components = list(closed.split(only_watertight=False))
    if not (
        closed.is_watertight
        and closed.is_winding_consistent
        and closed.is_volume
        and len(components) == 1
    ):
        raise RuntimeError("Serial zero-face-removed mesh is not one valid volume")
    return closed, {
        "method": "serial generated-only removal of one exact zero-area triangle",
        "removed_zero_area_face_indices": [int(value) for value in zero_faces],
        "removed_zero_area_mm2": float(np.sum(area_faces[zero_faces])),
        "boundary_edge_count_after_zero_face_removal": 0,
        "existing_vertex_coordinate_max_abs_delta_mm": 0.0,
        "added_vertex_count": 0,
        "source_face_count": int(len(faces)),
        "final_face_count": int(len(closed.faces)),
        "volume_delta_from_repair_mm3": float(closed.volume - mesh.volume),
        "area_delta_from_repair_mm2": float(closed.area - mesh.area),
        "bounds_max_abs_delta_mm": float(
            np.max(np.abs(np.asarray(closed.bounds) - np.asarray(mesh.bounds)))
        ),
        "final_watertight": bool(closed.is_watertight),
        "final_winding_consistent": bool(closed.is_winding_consistent),
        "final_is_volume": bool(closed.is_volume),
        "final_component_count": len(components),
    }


validator.export_native_final_solid = export_serial_final_solid
validator.close_generated_planar_crack = close_zero_face_or_planar_crack
reference_raw = as_mesh(trimesh.load_mesh(validator.REFERENCE, process=True), "reference")
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference topology audit failed")

rows = []
for linear in LINEAR_VALUES:
    for angular in ANGULAR_VALUES:
        validator.ANGULAR_TOLERANCE = angular
        tag = f"linear_{linear:.9f}_angular_{angular:.6f}".replace(".", "p")
        validator.OUTPUT = ROOT / tag
        print(f"=== serial candidate linear={linear:.9f} angular={angular:.6f} ===", flush=True)
        try:
            row = validator.validate_candidate(linear, reference_raw, reference)
            row["occt_parallel"] = False
        except Exception as exc:
            row = {
                "linear_tolerance_mm": linear,
                "angular_tolerance_rad": angular,
                "occt_parallel": False,
                "strict_pass": False,
                "exception": repr(exc),
            }
        rows.append(row)
        print(json.dumps(row, indent=2), flush=True)

valid = [row for row in rows if "symmetric_difference_percent" in row]
valid.sort(key=lambda row: row["symmetric_difference_percent"])
report = {
    "reference_topology_audit": topology_audit,
    "reference_topology_checks": topology_checks,
    "candidates": rows,
    "best": valid[0] if valid else None,
    "overall_pass": bool(valid and valid[0]["strict_pass"]),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== SERIAL MESHER SWEEP RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
