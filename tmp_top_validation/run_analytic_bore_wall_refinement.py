"""Validate analytic adaptive retessellation of unobstructed mounting-bore walls.

The reference topology indicates an adaptive midpoint ring on long cylindrical
bore faces. This exporter refines only the final STL tessellation of exact
analytic cylinders: it reuses generated boundary rings, inserts a formula-based
midpoint ring with one fewer angular segment, and applies a deterministic zipper
triangulation. The Build123d F001-F012 BRep and STEP geometry are unchanged.
No reference vertices, faces, or coordinates are read by this refinement.
"""

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
ROOT = validator.ROOT / "generated" / "analytic_bore_wall_refinement"
ROOT.mkdir(parents=True, exist_ok=True)
validator.ANGULAR_TOLERANCE = ANGULAR

reference_raw = as_mesh(trimesh.load_mesh(validator.REFERENCE, process=True), "reference")
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference topology audit failed")

ORIGINAL_CLOSE = validator.close_generated_planar_crack
ORIGINAL_SUBTRACT = tp._subtract_cylindrical_bore
BASE_RADIUS = tp.MOUNT_BORE_RADIUS
BORE_DATA = {
    name: (x, z, y0, y1)
    for name, x, z, y0, y1 in tp.MOUNT_BORES
}

VARIANTS = (
    {
        "name": "baseline_nominal",
        "refine": (),
        "radius_delta": {},
    },
    {
        "name": "refine_bottom_right",
        "refine": ("bottom_right",),
        "radius_delta": {},
    },
    {
        "name": "refine_top_right",
        "refine": ("top_right",),
        "radius_delta": {},
    },
    {
        "name": "refine_bottom_right_top_right",
        "refine": ("bottom_right", "top_right"),
        "radius_delta": {},
    },
    {
        "name": "refine_rights_bl_radius_p0p00030",
        "refine": ("bottom_right", "top_right"),
        "radius_delta": {"bottom_left": 0.00030},
    },
    {
        "name": "refine_rights_all_optimized_radii",
        "refine": ("bottom_right", "top_right"),
        "radius_delta": {
            "bottom_left": 0.00030,
            "bottom_right": 0.00025,
            "top_right": 0.00025,
        },
    },
)


def edge_incidence(faces: np.ndarray) -> dict[tuple[int, int], int]:
    counts: dict[tuple[int, int], int] = {}
    for triangle in np.asarray(faces, dtype=np.int64):
        for first, second in ((0, 1), (1, 2), (2, 0)):
            a = int(triangle[first])
            b = int(triangle[second])
            edge = (a, b) if a < b else (b, a)
            counts[edge] = counts.get(edge, 0) + 1
    return counts


def analytic_strip(
    boundary: list[int],
    middle: list[int],
    reverse: bool,
) -> list[list[int]]:
    """59-to-58 adaptive cylindrical strip derived from segment counts."""
    boundary_count = len(boundary)
    middle_count = len(middle)
    if boundary_count != middle_count + 1:
        raise RuntimeError(
            f"Adaptive strip requires n and n-1 rings, got {boundary_count}, {middle_count}"
        )
    triangles: list[list[int]] = [
        [boundary[boundary_count - 1], boundary[0], middle[0]]
    ]
    for index in range(middle_count - 1):
        triangles.append([middle[index], boundary[index], boundary[index + 1]])
        triangles.append([middle[index], boundary[index + 1], middle[index + 1]])
    triangles.append(
        [middle[middle_count - 1], boundary[middle_count - 1], boundary[boundary_count - 1]]
    )
    triangles.append(
        [middle[middle_count - 1], boundary[boundary_count - 1], middle[0]]
    )
    if reverse:
        triangles = [[first, third, second] for first, second, third in triangles]
    return triangles


def boundary_ring(
    vertices: np.ndarray,
    center_x: float,
    center_z: float,
    radius: float,
    y: float,
    expected_count: int,
) -> list[int]:
    radial = np.linalg.norm(
        vertices[:, [0, 2]] - np.array([center_x, center_z]),
        axis=1,
    )
    candidates = np.where(
        (np.abs(radial - radius) <= 0.015)
        & (np.abs(vertices[:, 1] - y) <= 1.0e-4)
    )[0]
    indexed: dict[int, tuple[float, int]] = {}
    for vertex_index in candidates:
        angle = math.atan2(
            vertices[vertex_index, 2] - center_z,
            vertices[vertex_index, 0] - center_x,
        ) % (2.0 * math.pi)
        ring_index = int(round(angle * expected_count / (2.0 * math.pi))) % expected_count
        target_angle = 2.0 * math.pi * ring_index / expected_count
        error = abs((angle - target_angle + math.pi) % (2.0 * math.pi) - math.pi)
        previous = indexed.get(ring_index)
        if previous is None or error < previous[0]:
            indexed[ring_index] = (error, int(vertex_index))
    if len(indexed) != expected_count:
        raise RuntimeError(
            f"Unable to recover generated boundary ring at Y={y}: "
            f"expected {expected_count}, got {len(indexed)}"
        )
    return [indexed[index][1] for index in range(expected_count)]


def refine_cylindrical_bore_wall(
    mesh: trimesh.Trimesh,
    name: str,
    radius: float,
) -> tuple[trimesh.Trimesh, dict]:
    center_x, center_z, y0, y1 = BORE_DATA[name]
    vertices = np.asarray(mesh.vertices, dtype=np.float64).copy()
    faces = np.asarray(mesh.faces, dtype=np.int64).copy()
    radial = np.linalg.norm(
        vertices[:, [0, 2]] - np.array([center_x, center_z]),
        axis=1,
    )
    face_radial = radial[faces]
    face_y = vertices[faces][:, :, 1]
    wall_mask = (
        (np.max(np.abs(face_radial - radius), axis=1) <= 0.015)
        & (np.min(face_y, axis=1) >= y0 - 1.0e-4)
        & (np.max(face_y, axis=1) <= y1 + 1.0e-4)
        & ((np.max(face_y, axis=1) - np.min(face_y, axis=1)) > 1.0e-4)
    )
    removed_count = int(np.sum(wall_mask))
    if removed_count != 118:
        raise RuntimeError(
            f"Expected 118 generated cylindrical wall triangles for {name}, got {removed_count}"
        )
    kept_faces = faces[~wall_mask]

    lower = boundary_ring(vertices, center_x, center_z, radius, y0, 59)
    upper = boundary_ring(vertices, center_x, center_z, radius, y1, 59)
    midpoint_y = (y0 + y1) / 2.0
    middle: list[int] = []
    new_vertices = []
    for index in range(58):
        angle = 2.0 * math.pi * index / 58.0
        middle.append(len(vertices) + len(new_vertices))
        new_vertices.append(
            [
                center_x + radius * math.cos(angle),
                midpoint_y,
                center_z + radius * math.sin(angle),
            ]
        )
    vertices = np.vstack([vertices, np.asarray(new_vertices, dtype=np.float64)])
    new_faces = np.asarray(
        analytic_strip(lower, middle, reverse=False)
        + analytic_strip(upper, middle, reverse=True),
        dtype=np.int64,
    )
    refined = trimesh.Trimesh(
        vertices=vertices,
        faces=np.vstack([kept_faces, new_faces]),
        process=False,
        validate=False,
    )
    abnormal = {
        edge: count
        for edge, count in edge_incidence(refined.faces).items()
        if count != 2
    }
    if abnormal:
        raise RuntimeError(
            f"Analytic {name} bore-wall refinement left abnormal edges: "
            f"{list(abnormal.items())[:5]}"
        )
    if not refined.is_winding_consistent:
        trimesh.repair.fix_winding(refined)
    components = list(refined.split(only_watertight=False))
    if not (
        refined.is_watertight
        and refined.is_winding_consistent
        and refined.is_volume
        and len(components) == 1
    ):
        raise RuntimeError(f"Analytic {name} bore-wall refinement is not one valid volume")
    audit = {
        "feature": name,
        "method": (
            "formula-based adaptive analytic cylinder tessellation: generated "
            "59-segment boundary rings, 58-segment midpoint ring, deterministic zipper"
        ),
        "radius_mm": radius,
        "y0_mm": y0,
        "midpoint_y_mm": midpoint_y,
        "y1_mm": y1,
        "removed_wall_triangle_count": removed_count,
        "added_midpoint_vertex_count": 58,
        "added_wall_triangle_count": int(len(new_faces)),
        "boundary_segment_count": 59,
        "midpoint_segment_count": 58,
        "final_watertight": bool(refined.is_watertight),
        "final_winding_consistent": bool(refined.is_winding_consistent),
        "final_is_volume": bool(refined.is_volume),
        "final_component_count": len(components),
    }
    return refined, audit


def install_radius_map(radius_delta: dict[str, float]) -> dict[str, float]:
    radius_by_name = {
        name: BASE_RADIUS + radius_delta.get(name, 0.0)
        for name in BORE_DATA
    }

    def selective_subtract(x: float, z: float, radius: float, y0: float, y1: float):
        if abs(radius - BASE_RADIUS) <= 1.0e-12:
            for name, (cx, cz, cy0, cy1) in BORE_DATA.items():
                if (
                    abs(x - cx) <= 1.0e-12
                    and abs(z - cz) <= 1.0e-12
                    and abs(y0 - cy0) <= 1.0e-12
                    and abs(y1 - cy1) <= 1.0e-12
                ):
                    return ORIGINAL_SUBTRACT(x, z, radius_by_name[name], y0, y1)
        return ORIGINAL_SUBTRACT(x, z, radius, y0, y1)

    tp._subtract_cylindrical_bore = selective_subtract
    return radius_by_name


def restore() -> None:
    tp._subtract_cylindrical_bore = ORIGINAL_SUBTRACT
    validator.close_generated_planar_crack = ORIGINAL_CLOSE


rows = []
for variant in VARIANTS:
    name = variant["name"]
    validator.OUTPUT = ROOT / name
    print(f"=== analytic bore-wall refinement variant {name} ===", flush=True)
    try:
        radius_by_name = install_radius_map(variant["radius_delta"])

        def close_and_refine(raw_mesh: trimesh.Trimesh):
            closed, crack_audit = ORIGINAL_CLOSE(raw_mesh)
            refinement_audit = []
            refined = closed
            for feature_name in variant["refine"]:
                refined, feature_audit = refine_cylindrical_bore_wall(
                    refined,
                    feature_name,
                    radius_by_name[feature_name],
                )
                refinement_audit.append(feature_audit)
            return refined, {
                "generated_planar_crack": crack_audit,
                "analytic_bore_wall_refinement": refinement_audit,
            }

        validator.close_generated_planar_crack = close_and_refine
        row = validator.validate_candidate(LINEAR, reference_raw, reference)
        row.update(
            {
                "variant": name,
                "refined_bores": list(variant["refine"]),
                "radius_delta_by_bore_mm": variant["radius_delta"],
                "radius_by_bore_mm": radius_by_name,
            }
        )
    except Exception as exc:
        row = {
            "variant": name,
            "refined_bores": list(variant["refine"]),
            "radius_delta_by_bore_mm": variant["radius_delta"],
            "strict_pass": False,
            "exception": repr(exc),
        }
    finally:
        restore()
    rows.append(row)
    print(json.dumps(row, indent=2), flush=True)

valid = [row for row in rows if "symmetric_difference_percent" in row]
valid.sort(key=lambda row: row["symmetric_difference_percent"])
report = {
    "reference_topology_audit": topology_audit,
    "reference_topology_checks": topology_checks,
    "linear_tolerance_mm": LINEAR,
    "angular_tolerance_rad": ANGULAR,
    "candidates": rows,
    "ranking": valid,
    "best": valid[0] if valid else None,
    "overall_pass": bool(valid and valid[0]["strict_pass"]),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== ANALYTIC BORE-WALL REFINEMENT RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
