"""Strict SROT and exact-polyhedral validation for the reconstructed top.

The immutable reference STL contains one identified four-face tangency edge.
STL stores triangle coordinates but not topological edge identity, so the same
geometric edge is shared by two closed face fans.  This validator performs a
zero-coordinate topology split: one endpoint is duplicated at exactly the same
coordinate and one connected face fan is reassigned to that duplicate.  Every
triangle's geometric coordinates, volume, area, centre of mass, and bounds are
audited as unchanged before the repaired topology is used for two directional
Manifold3D Boolean differences.

The parametric generator remains completely independent of this validator and
is separately enforced by strict_srot_check.py.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import manifold3d
import numpy as np
import trimesh
from build123d import CenterOf, Mesher, export_step, export_stl

from strict_srot_check import run as run_srot
from top_parametric import build_top

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


def edge_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def edge_incidence(faces: np.ndarray) -> dict[tuple[int, int], list[int]]:
    result: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, triangle in enumerate(faces):
        a, b, c = (int(value) for value in triangle)
        result[edge_key(a, b)].append(face_index)
        result[edge_key(b, c)].append(face_index)
        result[edge_key(c, a)].append(face_index)
    return dict(result)


def endpoint_face_components(
    faces: np.ndarray,
    endpoint: int,
    singular_edge: tuple[int, int],
) -> list[list[int]]:
    """Return face-fan components around an endpoint, excluding one edge."""
    incident = [
        face_index
        for face_index, triangle in enumerate(faces)
        if endpoint in triangle
    ]
    neighbours: dict[int, set[int]] = {index: set() for index in incident}
    shared_endpoint_edges: dict[int, list[int]] = defaultdict(list)

    for face_index in incident:
        for other in (int(value) for value in faces[face_index]):
            if other == endpoint:
                continue
            if edge_key(endpoint, other) == singular_edge:
                continue
            shared_endpoint_edges[other].append(face_index)

    for edge_faces in shared_endpoint_edges.values():
        for first in edge_faces:
            for second in edge_faces:
                if first != second:
                    neighbours[first].add(second)

    unseen = set(incident)
    components: list[list[int]] = []
    while unseen:
        seed = min(unseen)
        stack = [seed]
        component: set[int] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            unseen.discard(current)
            stack.extend(neighbours[current] - component)
        components.append(sorted(component))
    return sorted(components, key=lambda component: (len(component), component))


def topology_split_reference(
    reference: trimesh.Trimesh,
) -> tuple[trimesh.Trimesh, dict[str, Any], dict[str, bool]]:
    """Split the sole four-face tangency edge without moving any coordinate."""
    original_vertices = np.asarray(reference.vertices, dtype=np.float64)
    original_faces = np.asarray(reference.faces, dtype=np.int64)
    incidence = edge_incidence(original_faces)
    abnormal = {
        edge: face_indices
        for edge, face_indices in incidence.items()
        if len(face_indices) != 2
    }
    four_face_edges = {
        edge: face_indices
        for edge, face_indices in abnormal.items()
        if len(face_indices) == 4
    }
    if len(abnormal) != 1 or len(four_face_edges) != 1:
        raise RuntimeError(
            "Expected exactly one four-face tangency edge, found "
            f"abnormal={len(abnormal)}, four_face={len(four_face_edges)}"
        )

    singular_edge, singular_faces = next(iter(four_face_edges.items()))
    endpoint_candidates: list[tuple[int, int, list[list[int]]]] = []
    for endpoint in singular_edge:
        components = endpoint_face_components(
            original_faces,
            endpoint,
            singular_edge,
        )
        if len(components) != 2:
            continue
        singular_counts = [
            len(set(component).intersection(singular_faces))
            for component in components
        ]
        if singular_counts != [2, 2]:
            continue
        incident_count = sum(len(component) for component in components)
        endpoint_candidates.append((incident_count, endpoint, components))

    if not endpoint_candidates:
        raise RuntimeError(
            "Unable to separate the singular edge into two closed face fans"
        )

    # Choose the endpoint with the smallest local face star, then the smallest
    # vertex index.  Choose the smallest fan deterministically.
    _, split_endpoint, components = min(
        endpoint_candidates,
        key=lambda item: (item[0], item[1]),
    )
    reassigned_faces = components[0]

    repaired_vertices = np.vstack(
        [original_vertices, original_vertices[split_endpoint]]
    )
    duplicate_vertex = len(original_vertices)
    repaired_faces = original_faces.copy()
    for face_index in reassigned_faces:
        mask = repaired_faces[face_index] == split_endpoint
        if int(np.count_nonzero(mask)) != 1:
            raise RuntimeError(
                f"Face {face_index} does not contain split endpoint exactly once"
            )
        repaired_faces[face_index, mask] = duplicate_vertex

    repaired = trimesh.Trimesh(
        vertices=repaired_vertices,
        faces=repaired_faces,
        process=False,
        validate=False,
    )

    original_triangle_coordinates = original_vertices[original_faces]
    repaired_triangle_coordinates = repaired_vertices[repaired_faces]
    triangle_coordinate_delta = float(
        np.max(
            np.abs(
                repaired_triangle_coordinates - original_triangle_coordinates
            )
        )
    )
    original_bounds = np.asarray(reference.bounds, dtype=float)
    repaired_bounds = np.asarray(repaired.bounds, dtype=float)
    original_com = np.asarray(reference.center_mass, dtype=float)
    repaired_com = np.asarray(repaired.center_mass, dtype=float)

    audit = {
        "method": "zero-coordinate singular-edge endpoint duplication",
        "raw_vertices": int(len(original_vertices)),
        "repaired_vertices": int(len(repaired_vertices)),
        "raw_faces": int(len(original_faces)),
        "repaired_faces": int(len(repaired_faces)),
        "abnormal_edge_count_before": int(len(abnormal)),
        "singular_edge_vertex_indices": [int(value) for value in singular_edge],
        "singular_edge_incident_faces": [int(value) for value in singular_faces],
        "split_endpoint_vertex_index": int(split_endpoint),
        "duplicate_vertex_index": int(duplicate_vertex),
        "reassigned_face_indices": [int(value) for value in reassigned_faces],
        "duplicated_coordinate_mm": original_vertices[split_endpoint].tolist(),
        "raw_watertight": bool(reference.is_watertight),
        "repaired_watertight": bool(repaired.is_watertight),
        "repaired_winding_consistent": bool(repaired.is_winding_consistent),
        "repaired_is_volume": bool(repaired.is_volume),
        "raw_euler_number": int(reference.euler_number),
        "repaired_euler_number": int(repaired.euler_number),
        "triangle_coordinate_max_abs_delta_mm": triangle_coordinate_delta,
        "original_vertices_max_abs_delta_mm": float(
            np.max(np.abs(repaired_vertices[:-1] - original_vertices))
        ),
        "duplicate_coordinate_max_abs_delta_mm": float(
            np.max(
                np.abs(
                    repaired_vertices[-1] - original_vertices[split_endpoint]
                )
            )
        ),
        "raw_volume_mm3": float(abs(reference.volume)),
        "repaired_volume_mm3": float(abs(repaired.volume)),
        "volume_delta_mm3": float(abs(repaired.volume) - abs(reference.volume)),
        "raw_area_mm2": float(reference.area),
        "repaired_area_mm2": float(repaired.area),
        "area_delta_mm2": float(repaired.area - reference.area),
        "com_shift_mm": float(np.linalg.norm(repaired_com - original_com)),
        "bbox_max_abs_delta_mm": float(
            np.max(np.abs(repaired_bounds - original_bounds))
        ),
    }
    checks = {
        "exactly_one_four_face_singularity": (
            len(abnormal) == 1 and len(four_face_edges) == 1
        ),
        "one_vertex_added": len(repaired_vertices) == len(original_vertices) + 1,
        "triangle_count_preserved": len(repaired_faces) == len(original_faces),
        "all_triangle_coordinates_identical": triangle_coordinate_delta == 0.0,
        "all_original_vertex_coordinates_identical": (
            audit["original_vertices_max_abs_delta_mm"] == 0.0
        ),
        "duplicate_coordinate_identical": (
            audit["duplicate_coordinate_max_abs_delta_mm"] == 0.0
        ),
        "volume_identical": audit["volume_delta_mm3"] == 0.0,
        "area_identical": audit["area_delta_mm2"] == 0.0,
        "center_of_mass_identical": audit["com_shift_mm"] == 0.0,
        "bounds_identical": audit["bbox_max_abs_delta_mm"] == 0.0,
        "repaired_watertight": bool(repaired.is_watertight),
        "repaired_winding_consistent": bool(repaired.is_winding_consistent),
        "repaired_is_volume": bool(repaired.is_volume),
    }
    return repaired, audit, checks


def manifold_status(value: manifold3d.Manifold) -> str:
    try:
        return str(value.status())
    except Exception as exc:
        return f"status-unavailable: {type(exc).__name__}: {exc}"


def to_manifold(
    mesh: trimesh.Trimesh,
    label: str,
) -> tuple[manifold3d.Manifold, dict[str, Any]]:
    vertices = np.asarray(mesh.vertices, dtype=np.float32)
    faces = np.asarray(mesh.faces, dtype=np.uint32)
    manifold_mesh = manifold3d.Mesh(
        vert_properties=vertices,
        tri_verts=faces,
    )
    try:
        solid = manifold3d.Manifold.from_mesh(manifold_mesh)
        constructor = "Manifold.from_mesh"
    except AttributeError:
        solid = manifold3d.Manifold(mesh=manifold_mesh)
        constructor = "Manifold(mesh=...)"

    status = manifold_status(solid)
    volume = float(solid.get_volume())
    empty = bool(solid.is_empty())
    audit = {
        "label": label,
        "constructor": constructor,
        "status": status,
        "is_empty": empty,
        "input_vertices": int(len(vertices)),
        "input_faces": int(len(faces)),
        "input_trimesh_volume_mm3": float(abs(mesh.volume)),
        "manifold_volume_mm3": volume,
        "volume_delta_mm3": volume - float(abs(mesh.volume)),
    }
    if empty or not np.isfinite(volume) or volume <= 0.0:
        raise RuntimeError(
            f"Manifold3D rejected {label}: status={status}, volume={volume}"
        )
    return solid, audit


def write_report(report_path: Path, report: dict[str, Any]) -> None:
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> int:
    GENERATED.mkdir(parents=True, exist_ok=True)
    report_path = GENERATED / "fast_validation_report.json"
    report: dict[str, Any] = {
        "overall_pass": False,
        "thresholds": {
            "volume_difference_percent_max": 0.1,
            "surface_area_difference_percent_max": 0.1,
            "com_shift_percent_of_bbox_diagonal_max": 0.1,
            "symmetric_difference_percent_max": 0.01,
        },
    }

    try:
        reference_sha = hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
        report["reference_sha256"] = reference_sha
        if reference_sha != EXPECTED_SHA256:
            raise RuntimeError(
                "Reference checksum mismatch: "
                f"expected {EXPECTED_SHA256}, got {reference_sha}"
            )

        log("Running machine-enforced Strict SROT audit")
        srot = run_srot(GENERATED / "strict_srot_report.json")
        report["strict_srot"] = srot
        if not srot["pass"]:
            raise RuntimeError("Strict SROT audit failed")

        log("Loading immutable reference metrics")
        reference_raw = trimesh.load_mesh(REFERENCE, process=True)
        if not isinstance(reference_raw, trimesh.Trimesh):
            raise RuntimeError("Reference did not load as one Trimesh")

        log("Verifying checksum reference imports as one OpenCascade solid")
        imported = Mesher().read(REFERENCE)
        if len(imported) != 1:
            raise RuntimeError(f"Expected one imported shape, got {len(imported)}")
        reference_shape = imported[0]
        reference_occt = {
            "import_count": len(imported),
            "is_valid": bool(reference_shape.is_valid),
            "solid_count": len(reference_shape.solids()),
            "volume_mm3": float(reference_shape.volume),
            "area_mm2": float(reference_shape.area),
        }
        report["reference_occt"] = reference_occt
        if not reference_shape.is_valid or len(reference_shape.solids()) != 1:
            raise RuntimeError("Reference is not one valid OpenCascade solid")

        log("Applying zero-coordinate topology split to reference tangency")
        reference_repaired, topology_audit, topology_checks = (
            topology_split_reference(reference_raw)
        )
        report["reference_topology_audit"] = topology_audit
        report["reference_topology_checks"] = topology_checks
        if not all(topology_checks.values()):
            raise RuntimeError("Reference topology split failed preservation audit")

        log("Building complete F001-F012 parametric solid")
        model = build_top()
        if not model.is_valid or len(model.solids()) != 1:
            raise RuntimeError("Generated CAD is not one valid solid")
        step_path = GENERATED / "top_parametric.step"
        stl_path = GENERATED / "top_parametric.stl"
        export_step(model, step_path)
        export_stl(
            model,
            stl_path,
            tolerance=0.001,
            angular_tolerance=0.1,
            ascii_format=False,
        )
        generated_mesh = trimesh.load_mesh(stl_path, process=True)
        if not isinstance(generated_mesh, trimesh.Trimesh):
            raise RuntimeError("Generated STL did not load as one Trimesh")
        if not generated_mesh.is_watertight or not generated_mesh.is_volume:
            raise RuntimeError("Generated STL is not a watertight positive volume")

        log("Constructing reference and generated Manifold3D solids")
        reference_manifold, reference_manifold_audit = to_manifold(
            reference_repaired,
            "zero-coordinate topology-split reference",
        )
        generated_manifold, generated_manifold_audit = to_manifold(
            generated_mesh,
            "generated parametric STL",
        )
        report["reference_manifold_audit"] = reference_manifold_audit
        report["generated_manifold_audit"] = generated_manifold_audit

        log("Computing generated-minus-reference Manifold3D difference")
        generated_minus_reference = generated_manifold - reference_manifold
        gen_minus_ref_status = manifold_status(generated_minus_reference)
        gen_minus_ref_volume = float(generated_minus_reference.get_volume())

        log("Computing reference-minus-generated Manifold3D difference")
        reference_minus_generated = reference_manifold - generated_manifold
        ref_minus_gen_status = manifold_status(reference_minus_generated)
        ref_minus_gen_volume = float(reference_minus_generated.get_volume())

        if not np.isfinite(gen_minus_ref_volume) or gen_minus_ref_volume < 0.0:
            raise RuntimeError(
                "Invalid generated-minus-reference volume: "
                f"{gen_minus_ref_volume} ({gen_minus_ref_status})"
            )
        if not np.isfinite(ref_minus_gen_volume) or ref_minus_gen_volume < 0.0:
            raise RuntimeError(
                "Invalid reference-minus-generated volume: "
                f"{ref_minus_gen_volume} ({ref_minus_gen_status})"
            )

        ref_volume = float(abs(reference_raw.volume))
        ref_area = float(reference_raw.area)
        ref_com = np.asarray(reference_raw.center_mass, dtype=float)
        ref_bounds = np.asarray(reference_raw.bounds, dtype=float)
        gen_volume = float(model.volume)
        gen_area = float(model.area)
        gen_com = vector3(model.center(CenterOf.MASS))
        gen_bounds = np.asarray(generated_mesh.bounds, dtype=float)
        bbox_diagonal = float(np.linalg.norm(ref_bounds[1] - ref_bounds[0]))
        com_shift_mm = float(np.linalg.norm(gen_com - ref_com))
        symmetric_volume = gen_minus_ref_volume + ref_minus_gen_volume

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
            "com_shift_percent_of_bbox_diagonal": (
                com_shift_mm / bbox_diagonal * 100.0
            ),
            "reference_bbox_mm": ref_bounds.tolist(),
            "generated_bbox_mm": gen_bounds.tolist(),
            "bbox_absolute_delta_mm": np.abs(gen_bounds - ref_bounds).tolist(),
            "generated_minus_reference_status": gen_minus_ref_status,
            "reference_minus_generated_status": ref_minus_gen_status,
            "generated_minus_reference_volume_mm3": gen_minus_ref_volume,
            "reference_minus_generated_volume_mm3": ref_minus_gen_volume,
            "symmetric_difference_volume_mm3": symmetric_volume,
            "symmetric_difference_percent": symmetric_volume / ref_volume * 100.0,
        }
        checks = {
            "strict_srot": bool(srot["pass"]),
            "reference_checksum": reference_sha == EXPECTED_SHA256,
            "reference_occt_single_valid_solid": bool(
                reference_shape.is_valid and len(reference_shape.solids()) == 1
            ),
            "reference_topology_preservation": all(topology_checks.values()),
            "reference_manifold_positive_volume": (
                reference_manifold_audit["manifold_volume_mm3"] > 0.0
            ),
            "generated_cad_single_valid_solid": bool(
                model.is_valid and len(model.solids()) == 1
            ),
            "generated_stl_watertight": bool(generated_mesh.is_watertight),
            "generated_manifold_positive_volume": (
                generated_manifold_audit["manifold_volume_mm3"] > 0.0
            ),
            "directional_booleans_finite": bool(
                np.isfinite(gen_minus_ref_volume)
                and np.isfinite(ref_minus_gen_volume)
            ),
            "volume": metrics["volume_difference_percent"] < 0.1,
            "surface_area": metrics["area_difference_percent"] < 0.1,
            "center_of_mass": (
                metrics["com_shift_percent_of_bbox_diagonal"] < 0.1
            ),
            "symmetric_difference": (
                metrics["symmetric_difference_percent"] < 0.01
            ),
        }
        report.update(
            {
                "generator": str((ROOT / "top_parametric.py").resolve()),
                "generated_step": str(step_path.resolve()),
                "generated_stl": str(stl_path.resolve()),
                "boolean_engine": (
                    "Manifold3D 3.5.2 direct indexed-mesh input; "
                    "two directional differences"
                ),
                "reference_regularization": (
                    "One topological endpoint duplicate at an identical XYZ "
                    "coordinate separates the two closed face fans of the "
                    "single four-face tangent edge. No triangle coordinate or "
                    "geometric invariant changes."
                ),
                "metrics": metrics,
                "checks": checks,
                "overall_pass": all(checks.values()),
            }
        )
        write_report(report_path, report)
        log(json.dumps(report, indent=2))
        return 0 if report["overall_pass"] else 1

    except Exception as exc:
        report["exception"] = f"{type(exc).__name__}: {exc}"
        write_report(report_path, report)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
