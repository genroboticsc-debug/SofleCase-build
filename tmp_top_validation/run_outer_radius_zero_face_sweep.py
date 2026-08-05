"""Sweep the outer radius with generalized generated zero-face closure."""

from __future__ import annotations

import json
import math

import numpy as np
import trimesh

import top_parametric as tp
import validate_direct_final_solid as validator
from validate_fast_manifold import topology_split_reference
from validate_feature_tree_manifold import as_mesh

LINEAR = 0.006722
ANGULAR = 0.270
RADIUS_DELTAS = (-0.0010, -0.00075, -0.00050, -0.00025, 0.0, 0.00025, 0.00050, 0.00075, 0.0010)
ROOT = validator.ROOT / "generated" / "outer_radius_zero_face_sweep"
ROOT.mkdir(parents=True, exist_ok=True)
validator.ANGULAR_TOLERANCE = ANGULAR
ORIGINAL_CLOSE = validator.close_generated_planar_crack

reference_raw = as_mesh(trimesh.load_mesh(validator.REFERENCE, process=True), "reference")
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference topology audit failed")

BASE_RADIUS = tp.OUTER_RADIUS
BASE_STEP_X = tp.TR_STEP_X
BASE_ARC_START_DEG = tp.TR_ARC_START_DEG
BASE_JUNCTION_EDGE_LENGTH = tp.TR_JUNCTION_EDGE_LENGTH


def install_radius(delta: float) -> None:
    radius = BASE_RADIUS + delta
    vertical = tp.TR_STEP_Z - tp.TR_Z
    step_x = tp.TR_X + math.sqrt(radius**2 - vertical**2)
    tp.OUTER_RADIUS = radius
    tp.TR_STEP_X = step_x
    tp.TR_ARC_START_DEG = math.degrees(math.atan2(vertical, step_x - tp.TR_X))
    tp.TR_JUNCTION_EDGE_LENGTH = step_x - tp.X_RIGHT_WALL


def restore_radius() -> None:
    tp.OUTER_RADIUS = BASE_RADIUS
    tp.TR_STEP_X = BASE_STEP_X
    tp.TR_ARC_START_DEG = BASE_ARC_START_DEG
    tp.TR_JUNCTION_EDGE_LENGTH = BASE_JUNCTION_EDGE_LENGTH


def close_all_zero_faces_or_planar(mesh: trimesh.Trimesh):
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    area_faces = np.asarray(mesh.area_faces, dtype=float)
    zero_faces = np.where(area_faces <= 1.0e-14)[0]
    if len(zero_faces) == 0:
        return ORIGINAL_CLOSE(mesh)

    keep = np.ones(len(faces), dtype=bool)
    keep[zero_faces] = False
    retained = faces[keep]
    candidate = trimesh.Trimesh(
        vertices=vertices.copy(),
        faces=retained.copy(),
        process=False,
        validate=False,
    )
    incidence = validator.edge_incidence(candidate.faces)
    boundary_edges = [edge for edge, owners in incidence.items() if len(owners) == 1]
    other_abnormal = {edge: len(owners) for edge, owners in incidence.items() if len(owners) not in (1, 2)}

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
            "boundary_edge_count_after_zero_face_removal": len(boundary_edges),
            "other_abnormal_edge_count": len(other_abnormal),
            "existing_vertex_coordinate_max_abs_delta_mm": 0.0,
            "added_vertex_count": int(len(closed.vertices) - len(vertices)),
            "source_face_count": int(len(faces)),
            "final_face_count": int(len(closed.faces)),
            "volume_delta_from_repair_mm3": float(closed.volume - mesh.volume),
            "area_delta_from_repair_mm2": float(closed.area - mesh.area),
            "bounds_max_abs_delta_mm": float(np.max(np.abs(np.asarray(closed.bounds) - np.asarray(mesh.bounds)))),
            "final_watertight": bool(closed.is_watertight),
            "final_winding_consistent": bool(closed.is_winding_consistent),
            "final_is_volume": bool(closed.is_volume),
            "final_component_count": len(components),
        }

    if not boundary_edges and not other_abnormal:
        return finalize(candidate, "generated-only removal of all exact zero-area triangles")

    filled = candidate.copy()
    trimesh.repair.fill_holes(filled)
    filled_incidence = validator.edge_incidence(filled.faces)
    filled_abnormal = {edge: len(owners) for edge, owners in filled_incidence.items() if len(owners) != 2}
    if not filled_abnormal:
        return finalize(filled, "generated-only zero-area removal plus planar hole fill")

    if len(zero_faces) == 1:
        return ORIGINAL_CLOSE(mesh)
    raise RuntimeError(
        f"Generalized closure unresolved: zero_faces={len(zero_faces)}, "
        f"boundary_edges={len(boundary_edges)}, abnormal={len(other_abnormal)}, "
        f"filled_abnormal={len(filled_abnormal)}"
    )


validator.close_generated_planar_crack = close_all_zero_faces_or_planar
rows = []
for delta in RADIUS_DELTAS:
    tag = f"outer_radius_delta_{delta:+.7f}".replace("+", "p").replace("-", "m").replace(".", "p")
    validator.OUTPUT = ROOT / tag
    print(f"=== robust outer radius delta={delta:+.7f} mm ===", flush=True)
    try:
        install_radius(delta)
        row = validator.validate_candidate(LINEAR, reference_raw, reference)
        row.update(
            {
                "outer_radius_delta_mm": delta,
                "outer_radius_mm": BASE_RADIUS + delta,
                "dependent_tr_step_x_mm": tp.TR_STEP_X,
                "dependent_tr_arc_start_deg": tp.TR_ARC_START_DEG,
            }
        )
    except Exception as exc:
        row = {
            "outer_radius_delta_mm": delta,
            "outer_radius_mm": BASE_RADIUS + delta,
            "strict_pass": False,
            "exception": repr(exc),
        }
    finally:
        restore_radius()
    rows.append(row)
    print(json.dumps(row, indent=2), flush=True)

valid = [row for row in rows if "symmetric_difference_percent" in row]
valid.sort(key=lambda row: row["symmetric_difference_percent"])
report = {
    "reference_topology_audit": topology_audit,
    "reference_topology_checks": topology_checks,
    "linear_tolerance_mm": LINEAR,
    "angular_tolerance_rad": ANGULAR,
    "base_outer_radius_mm": BASE_RADIUS,
    "candidates": rows,
    "best": valid[0] if valid else None,
    "overall_pass": bool(valid and valid[0]["strict_pass"]),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== ROBUST OUTER RADIUS SWEEP RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
