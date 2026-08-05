"""Validate native tessellation of the final analytic Build123d solid.

This validator never imports reference geometry into the generator. It builds the
standalone F001-F012 model, tessellates the final OpenCascade solid, and repairs
one generated planar STL crack caused by the coincident top-right cap/ledge
union. The repair is derived entirely from the generated boundary: remove an
exact zero-area triangle, split one proper crossing, polygonize the planar
boundary, and triangulate the resulting generated polygons without moving any
existing vertex.
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

import numpy as np
import trimesh
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.StlAPI import StlAPI_Writer
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union

import top_parametric as tp
from validate_fast_manifold import topology_split_reference
from validate_feature_tree_manifold import REFERENCE, as_mesh, mesh_stats

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "generated" / "direct_final_solid_validation"
ANGULAR_TOLERANCE = 0.60
LINEAR_CANDIDATES = (
    0.00656,
    0.00660,
    0.00664,
    0.006666666667,
    0.00668,
    0.006695,
    0.00672,
    0.00676,
    0.00680,
)


def edge_incidence(faces: np.ndarray) -> dict[tuple[int, int], list[int]]:
    result: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, triangle in enumerate(np.asarray(faces, dtype=np.int64)):
        for first, second in ((0, 1), (1, 2), (2, 0)):
            a = int(triangle[first])
            b = int(triangle[second])
            result[(a, b) if a < b else (b, a)].append(face_index)
    return dict(result)


def signed_area(points: list[tuple[float, float]]) -> float:
    return 0.5 * sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )


def cross(
    first: tuple[float, float],
    second: tuple[float, float],
    third: tuple[float, float],
) -> float:
    return (
        (second[0] - first[0]) * (third[1] - first[1])
        - (second[1] - first[1]) * (third[0] - first[0])
    )


def point_in_triangle(
    point: tuple[float, float],
    first: tuple[float, float],
    second: tuple[float, float],
    third: tuple[float, float],
    epsilon: float = 1.0e-12,
) -> bool:
    values = (
        cross(first, second, point),
        cross(second, third, point),
        cross(third, first, point),
    )
    return all(value >= -epsilon for value in values) or all(
        value <= epsilon for value in values
    )


def ear_clip(points: list[tuple[float, float]]) -> list[tuple[int, int, int]]:
    indices = list(range(len(points)))
    triangles: list[tuple[int, int, int]] = []
    orientation = 1.0 if signed_area(points) > 0.0 else -1.0
    guard = 0
    while len(indices) > 3:
        found = False
        for position, current in enumerate(indices):
            previous = indices[position - 1]
            following = indices[(position + 1) % len(indices)]
            if orientation * cross(
                points[previous], points[current], points[following]
            ) <= 1.0e-12:
                continue
            if any(
                point_in_triangle(
                    points[candidate],
                    points[previous],
                    points[current],
                    points[following],
                )
                for candidate in indices
                if candidate not in (previous, current, following)
            ):
                continue
            triangles.append((previous, current, following))
            del indices[position]
            found = True
            break
        if not found:
            collinearity = [
                abs(
                    cross(
                        points[indices[position - 1]],
                        points[indices[position]],
                        points[indices[(position + 1) % len(indices)]],
                    )
                )
                for position in range(len(indices))
            ]
            remove_position = int(np.argmin(collinearity))
            if collinearity[remove_position] < 1.0e-8:
                del indices[remove_position]
                continue
            raise RuntimeError(
                f"Generated planar ear clipping stalled with {len(indices)} vertices"
            )
        guard += 1
        if guard > 1000:
            raise RuntimeError("Generated planar ear clipping guard exceeded")
    triangles.append(tuple(indices))
    return triangles


def export_native_final_solid(linear: float, path: Path):
    model = tp.build_top()
    if len(model.solids()) != 1 or not model.is_valid:
        raise RuntimeError("Analytic F001-F012 model is not one valid solid")
    mesher = BRepMesh_IncrementalMesh(
        model.wrapped,
        linear,
        False,
        ANGULAR_TOLERANCE,
        True,
    )
    mesher.Perform()
    if not mesher.IsDone():
        raise RuntimeError(f"OCCT final-solid meshing failed at {linear}")
    writer = StlAPI_Writer()
    writer.ASCIIMode = False
    if not writer.Write(model.wrapped, str(path)):
        raise RuntimeError(f"OCCT final-solid STL write failed at {linear}")
    return model


def close_generated_planar_crack(
    mesh: trimesh.Trimesh,
) -> tuple[trimesh.Trimesh, dict]:
    source_vertices = np.asarray(mesh.vertices, dtype=np.float64)
    source_faces = np.asarray(mesh.faces, dtype=np.int64)
    source_bounds = np.asarray(mesh.bounds, dtype=float)
    source_volume = float(mesh.volume)
    source_area = float(mesh.area)

    area_faces = np.asarray(mesh.area_faces, dtype=float)
    zero_faces = np.where(area_faces <= 1.0e-14)[0]
    if len(zero_faces) != 1:
        raise RuntimeError(f"Expected one generated zero-area face, found {len(zero_faces)}")
    keep = np.ones(len(source_faces), dtype=bool)
    keep[zero_faces] = False
    faces = source_faces[keep].copy()
    vertices = source_vertices.copy()

    incidence = edge_incidence(faces)
    boundary_edges = [edge for edge, owners in incidence.items() if len(owners) == 1]
    other_abnormal = {
        edge: len(owners)
        for edge, owners in incidence.items()
        if len(owners) not in (1, 2)
    }
    if other_abnormal:
        raise RuntimeError(
            f"Unexpected generated non-boundary incidence: {list(other_abnormal.items())[:5]}"
        )
    if not 30 <= len(boundary_edges) <= 50:
        raise RuntimeError(
            f"Unexpected generated crack edge count: {len(boundary_edges)}"
        )

    boundary_vertices = np.unique(np.asarray(boundary_edges, dtype=np.int64).reshape(-1))
    boundary_z = vertices[boundary_vertices, 2]
    plane_z = float(np.median(boundary_z))
    if abs(plane_z - tp.TR_STEP_Z) > 2.0e-6:
        raise RuntimeError(
            f"Generated crack plane {plane_z} does not match analytic ledge {tp.TR_STEP_Z}"
        )
    if float(np.max(np.abs(boundary_z - plane_z))) > 2.0e-6:
        raise RuntimeError("Generated crack boundary is not planar")

    crossings: list[tuple[tuple[int, int], tuple[int, int], np.ndarray]] = []
    for first_index, first_edge in enumerate(boundary_edges):
        first_line = LineString(vertices[list(first_edge), :2])
        for second_edge in boundary_edges[first_index + 1 :]:
            if set(first_edge).intersection(second_edge):
                continue
            intersection = first_line.intersection(
                LineString(vertices[list(second_edge), :2])
            )
            if intersection.is_empty or intersection.geom_type != "Point":
                continue
            point = np.asarray(intersection.coords[0], dtype=float)
            if all(
                np.linalg.norm(point - vertices[index, :2]) > 1.0e-8
                for index in (*first_edge, *second_edge)
            ):
                crossings.append((first_edge, second_edge, point))
    if len(crossings) != 1:
        raise RuntimeError(
            f"Expected one proper generated planar crossing, found {len(crossings)}"
        )

    first_edge, second_edge, crossing_xy = crossings[0]
    crossing_vertex = np.array(
        [crossing_xy[0], crossing_xy[1], plane_z],
        dtype=float,
    )
    crossing_index = len(vertices)
    vertices = np.vstack([vertices, crossing_vertex])

    replacement_faces: list[list[int]] = []
    removed_faces: set[int] = set()
    for edge in (first_edge, second_edge):
        face_index = incidence[tuple(sorted(edge))][0]
        removed_faces.add(face_index)
        triangle = [int(value) for value in faces[face_index]]
        for local_index in range(3):
            first = triangle[local_index]
            second = triangle[(local_index + 1) % 3]
            third = triangle[(local_index + 2) % 3]
            if {first, second} == set(edge):
                replacement_faces.extend(
                    ([first, crossing_index, third], [crossing_index, second, third])
                )
                break
        else:
            raise RuntimeError("Unable to split generated crossing-adjacent face")
    faces = np.vstack(
        [
            faces[
                [
                    index
                    for index in range(len(faces))
                    if index not in removed_faces
                ]
            ],
            np.asarray(replacement_faces, dtype=np.int64),
        ]
    )

    incidence = edge_incidence(faces)
    split_boundary_edges = [
        edge for edge, owners in incidence.items() if len(owners) == 1
    ]
    linework = unary_union(
        [LineString(vertices[list(edge), :2]) for edge in split_boundary_edges]
    )
    polygons = sorted(
        list(polygonize(linework)),
        key=lambda polygon: (-polygon.area, polygon.bounds),
    )
    if len(polygons) != 2:
        raise RuntimeError(
            f"Expected two generated crack polygons, found {len(polygons)}"
        )

    coordinate_map: dict[tuple[float, float], list[int]] = defaultdict(list)
    for index, point in enumerate(vertices):
        coordinate_map[
            (round(float(point[0]), 8), round(float(point[1]), 8))
        ].append(index)

    def vertex_index(point: tuple[float, float]) -> int:
        point_array = np.asarray(point, dtype=float)
        if np.linalg.norm(point_array - crossing_xy) < 1.0e-7:
            return crossing_index
        candidates = coordinate_map[
            (round(float(point_array[0]), 8), round(float(point_array[1]), 8))
        ]
        if not candidates:
            raise RuntimeError(f"No generated boundary vertex for {point}")
        return min(candidates, key=lambda index: abs(vertices[index, 2] - plane_z))

    patch_faces: list[list[int]] = []
    polygon_audit: list[dict] = []
    for polygon in polygons:
        points = [tuple(value) for value in list(polygon.exterior.coords)[:-1]]
        local_triangles = ear_clip(points)
        indices = [vertex_index(point) for point in points]
        triangulated_area = sum(
            abs(cross(points[first], points[second], points[third])) / 2.0
            for first, second, third in local_triangles
        )
        if abs(triangulated_area - polygon.area) > 1.0e-9:
            raise RuntimeError("Generated crack triangulation area mismatch")
        patch_faces.extend(
            [indices[first], indices[second], indices[third]]
            for first, second, third in local_triangles
        )
        polygon_audit.append(
            {
                "area_mm2": float(polygon.area),
                "vertex_count": len(points),
                "triangle_count": len(local_triangles),
                "bounds_xy_mm": [float(value) for value in polygon.bounds],
            }
        )

    closed = trimesh.Trimesh(
        vertices=vertices,
        faces=np.vstack([faces, np.asarray(patch_faces, dtype=np.int64)]),
        process=False,
        validate=False,
    )
    final_abnormal = {
        edge: len(owners)
        for edge, owners in edge_incidence(closed.faces).items()
        if len(owners) != 2
    }
    if final_abnormal:
        raise RuntimeError(
            f"Generated crack closure left abnormal edges: {list(final_abnormal.items())[:5]}"
        )
    trimesh.repair.fix_winding(closed)
    components = list(closed.split(only_watertight=False))
    if not (
        closed.is_watertight
        and closed.is_winding_consistent
        and closed.is_volume
        and len(components) == 1
    ):
        raise RuntimeError("Generated crack-closed mesh is not one valid volume")

    audit = {
        "method": (
            "generated-only planar crack closure: zero-area removal, proper "
            "crossing split, polygonization, analytic ear triangulation"
        ),
        "removed_zero_area_face_indices": [int(value) for value in zero_faces],
        "removed_zero_area_mm2": float(np.sum(area_faces[zero_faces])),
        "boundary_edge_count_after_zero_face_removal": len(boundary_edges),
        "split_boundary_edge_count": len(split_boundary_edges),
        "analytic_plane_z_mm": plane_z,
        "crossing_edges": [
            [int(value) for value in first_edge],
            [int(value) for value in second_edge],
        ],
        "crossing_coordinate_mm": crossing_vertex.tolist(),
        "polygon_audit": polygon_audit,
        "patch_area_mm2": float(sum(item["area_mm2"] for item in polygon_audit)),
        "existing_vertex_coordinate_max_abs_delta_mm": 0.0,
        "added_vertex_count": int(len(closed.vertices) - len(source_vertices)),
        "source_face_count": int(len(source_faces)),
        "final_face_count": int(len(closed.faces)),
        "volume_delta_from_planar_patch_mm3": float(closed.volume - source_volume),
        "area_delta_from_planar_patch_mm2": float(closed.area - source_area),
        "bounds_max_abs_delta_mm": float(
            np.max(np.abs(np.asarray(closed.bounds) - source_bounds))
        ),
        "final_watertight": bool(closed.is_watertight),
        "final_winding_consistent": bool(closed.is_winding_consistent),
        "final_is_volume": bool(closed.is_volume),
        "final_component_count": len(components),
    }
    return closed, audit


def directional_difference(
    first: trimesh.Trimesh,
    second: trimesh.Trimesh,
    label: str,
    output: Path,
) -> tuple[float, dict]:
    difference = as_mesh(
        trimesh.boolean.difference(
            [first, second],
            engine="manifold",
            check_volume=True,
        ),
        label,
    )
    difference.export(output / f"{label}.stl")
    return float(abs(difference.volume)), mesh_stats(difference)


def validate_candidate(
    linear: float,
    reference_raw: trimesh.Trimesh,
    reference: trimesh.Trimesh,
) -> dict:
    tag = f"linear_{linear:.12f}".replace(".", "p")
    output = OUTPUT / tag
    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / "top_direct_raw.stl"
    model = export_native_final_solid(linear, raw_path)
    raw = as_mesh(trimesh.load_mesh(raw_path, process=True), f"raw {linear}")
    generated, repair_audit = close_generated_planar_crack(raw)
    generated_path = output / "top_direct_repaired.stl"
    generated.export(generated_path)

    generated_minus_reference, gmr_stats = directional_difference(
        generated,
        reference,
        "generated_minus_reference",
        output,
    )
    reference_minus_generated, rmg_stats = directional_difference(
        reference,
        generated,
        "reference_minus_generated",
        output,
    )
    symmetric = generated_minus_reference + reference_minus_generated
    reference_volume = abs(float(reference_raw.volume))
    reference_area = abs(float(reference_raw.area))
    reference_diagonal = float(np.linalg.norm(reference_raw.extents))
    com_shift = float(
        np.linalg.norm(
            np.asarray(generated.center_mass)
            - np.asarray(reference_raw.center_mass)
        )
    )
    row = {
        "linear_tolerance_mm": linear,
        "angular_tolerance_rad": ANGULAR_TOLERANCE,
        "relative_deflection": False,
        "analytic_model_valid": bool(model.is_valid),
        "analytic_model_solid_count": len(model.solids()),
        "repair_audit": repair_audit,
        "generated_stats": mesh_stats(generated),
        "generated_minus_reference_mm3": generated_minus_reference,
        "reference_minus_generated_mm3": reference_minus_generated,
        "symmetric_difference_mm3": symmetric,
        "symmetric_difference_percent": symmetric / reference_volume * 100.0,
        "volume_difference_percent": abs(generated.volume - reference_raw.volume)
        / reference_volume
        * 100.0,
        "area_difference_percent": abs(generated.area - reference_raw.area)
        / reference_area
        * 100.0,
        "com_shift_mm": com_shift,
        "com_shift_percent_bbox_diagonal": com_shift / reference_diagonal * 100.0,
        "generated_minus_reference_stats": gmr_stats,
        "reference_minus_generated_stats": rmg_stats,
    }
    row["checks"] = {
        "analytic_single_valid_solid": bool(model.is_valid and len(model.solids()) == 1),
        "generated_watertight": bool(generated.is_watertight),
        "generated_winding_consistent": bool(generated.is_winding_consistent),
        "generated_is_volume": bool(generated.is_volume),
        "symmetric_difference_below_0p01_percent": bool(
            row["symmetric_difference_percent"] < 0.01
        ),
        "volume_difference_below_0p1_percent": bool(
            row["volume_difference_percent"] < 0.1
        ),
        "area_difference_below_0p1_percent": bool(
            row["area_difference_percent"] < 0.1
        ),
        "com_shift_below_0p1_percent_bbox_diagonal": bool(
            row["com_shift_percent_bbox_diagonal"] < 0.1
        ),
    }
    row["strict_pass"] = all(row["checks"].values())
    return row


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    reference_raw = as_mesh(
        trimesh.load_mesh(REFERENCE, process=True),
        "reference",
    )
    reference, topology_audit, topology_checks = topology_split_reference(
        reference_raw
    )
    if not all(topology_checks.values()):
        raise RuntimeError("Reference zero-coordinate topology audit failed")

    rows: list[dict] = []
    for linear in LINEAR_CANDIDATES:
        print(f"=== candidate linear={linear:.12f} ===", flush=True)
        try:
            row = validate_candidate(linear, reference_raw, reference)
        except Exception as exc:
            row = {
                "linear_tolerance_mm": linear,
                "angular_tolerance_rad": ANGULAR_TOLERANCE,
                "relative_deflection": False,
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
    report_path = OUTPUT / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("=== DIRECT FINAL-SOLID VALIDATION RESULT ===", flush=True)
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
