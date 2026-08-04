"""Strict SROT + feature-tree Manifold validation for top.stl.

The STEP model is generated exclusively by the analytic Build123d F001-F012
feature tree.  For STL and Boolean validation, each Build123d feature operand is
tessellated independently and the same ordered feature tree is evaluated by
Manifold3D through Trimesh.  This avoids the OpenCascade STL writer's known
non-manifold tessellation at the exact top-right tangent/ledge while preserving
the analytic STEP model and every recovered parameter.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
import trimesh
from build123d import BuildSketch, CenterOf, add, export_step, export_stl, extrude

import top_parametric as tp
from strict_srot_check import run as run_srot
from validate_fast_manifold import topology_split_reference

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "reference" / "top.stl"
GENERATED = ROOT / "generated"
FEATURES = GENERATED / "feature_meshes"
EXPECTED_REFERENCE_SHA256 = "d9cd3e5cae398287140e92136a87a7aa1ed6ec4433434fca0cf0b661ca869cac"


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def vector3(value: Any) -> np.ndarray:
    if hasattr(value, "X"):
        return np.array([value.X, value.Y, value.Z], dtype=float)
    return np.asarray(value, dtype=float).reshape(3)


def pct(delta: float, reference: float) -> float:
    return abs(delta) / abs(reference) * 100.0


def as_mesh(value: Any, label: str) -> trimesh.Trimesh:
    if value is None:
        return trimesh.Trimesh(
            vertices=np.empty((0, 3), dtype=float),
            faces=np.empty((0, 3), dtype=np.int64),
            process=False,
        )
    if isinstance(value, trimesh.Scene):
        value = value.to_mesh()
    if not isinstance(value, trimesh.Trimesh):
        raise RuntimeError(f"{label} returned {type(value)!r}, not Trimesh")
    return value


def edge_incidence_histogram(mesh: trimesh.Trimesh) -> dict[str, int]:
    incidence: dict[tuple[int, int], int] = defaultdict(int)
    for triangle in np.asarray(mesh.faces, dtype=np.int64):
        a, b, c = (int(index) for index in triangle)
        for first, second in ((a, b), (b, c), (c, a)):
            edge = (
                (first, second)
                if first < second
                else (second, first)
            )
            incidence[edge] += 1
    counts = Counter(incidence.values())
    return {str(key): int(value) for key, value in sorted(counts.items())}


def mesh_stats(mesh: trimesh.Trimesh) -> dict[str, Any]:
    components = mesh.split(only_watertight=False) if len(mesh.faces) else []
    return {
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "is_volume": bool(mesh.is_volume),
        "component_count": int(len(components)),
        "volume_mm3": float(abs(mesh.volume)),
        "area_mm2": float(mesh.area),
        "center_mass_mm": np.asarray(mesh.center_mass, dtype=float).tolist(),
        "bounds_mm": np.asarray(mesh.bounds, dtype=float).tolist(),
        "edge_incidence": edge_incidence_histogram(mesh),
    }


def tessellate_shape(shape: Any, name: str) -> trimesh.Trimesh:
    FEATURES.mkdir(parents=True, exist_ok=True)
    path = FEATURES / f"{name}.stl"
    export_stl(
        shape,
        path,
        tolerance=0.001,
        angular_tolerance=0.1,
        ascii_format=False,
    )
    mesh = trimesh.load_mesh(path, process=True)
    return as_mesh(mesh, name)


def remove_zero_area_faces(
    mesh: trimesh.Trimesh,
    label: str,
) -> tuple[trimesh.Trimesh, dict[str, Any]]:
    vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    triangles = vertices[faces]
    doubled_area = np.linalg.norm(
        np.cross(
            triangles[:, 1] - triangles[:, 0],
            triangles[:, 2] - triangles[:, 0],
        ),
        axis=1,
    )
    repeated = np.array(
        [len({int(a), int(b), int(c)}) != 3 for a, b, c in faces],
        dtype=bool,
    )
    remove = repeated | (doubled_area <= 1.0e-14)
    repaired = trimesh.Trimesh(
        vertices=vertices.copy(),
        faces=faces[~remove].copy(),
        process=True,
        validate=False,
    )
    audit = {
        "label": label,
        "removed_face_count": int(np.count_nonzero(remove)),
        "removed_max_doubled_area_mm2": (
            float(np.max(doubled_area[remove])) if np.any(remove) else 0.0
        ),
        "volume_delta_mm3": float(abs(repaired.volume) - abs(mesh.volume)),
        "area_delta_mm2": float(repaired.area - mesh.area),
        "bounds_max_abs_delta_mm": float(
            np.max(np.abs(np.asarray(repaired.bounds) - np.asarray(mesh.bounds)))
        ),
        "before": mesh_stats(mesh),
        "after": mesh_stats(repaired),
    }
    return repaired, audit


def assert_manifold(mesh: trimesh.Trimesh, label: str) -> None:
    if not mesh.is_watertight or not mesh.is_winding_consistent or not mesh.is_volume:
        raise RuntimeError(
            f"{label} is not a watertight positive volume: {mesh_stats(mesh)}"
        )


def boolean_union(base: trimesh.Trimesh, tool: trimesh.Trimesh, label: str) -> trimesh.Trimesh:
    assert_manifold(base, f"{label} base")
    assert_manifold(tool, f"{label} tool")
    result = as_mesh(
        trimesh.boolean.union(
            [base, tool],
            engine="manifold",
            check_volume=True,
        ),
        label,
    )
    assert_manifold(result, label)
    return result


def boolean_cut(base: trimesh.Trimesh, tool: trimesh.Trimesh, label: str) -> trimesh.Trimesh:
    assert_manifold(base, f"{label} base")
    assert_manifold(tool, f"{label} tool")
    result = as_mesh(
        trimesh.boolean.difference(
            [base, tool],
            engine="manifold",
            check_volume=True,
        ),
        label,
    )
    assert_manifold(result, label)
    return result


def engraving_cutters() -> list[Any]:
    with BuildSketch(tp.xz_plane(tp.Y_BODY_LOW)) as engraving_placed:
        add(tp._engraving_profile_sketch())
    faces = list(engraving_placed.sketch.faces())
    if len(faces) != 5:
        raise RuntimeError(f"Expected five F012 faces, got {len(faces)}")
    return [
        extrude(
            face,
            amount=-(tp.Y_ENGRAVE_HIGH - tp.Y_BODY_LOW),
        )
        for face in faces
    ]


def build_feature_mesh_tree() -> tuple[trimesh.Trimesh, dict[str, Any]]:
    audit: dict[str, Any] = {"operations": []}

    log("Tessellating F001 main rolling body")
    main_raw = tessellate_shape(tp._main_rolling_body(), "F001_main_raw")
    main, main_repair = remove_zero_area_faces(main_raw, "F001")
    audit["F001_zero_area_repair"] = main_repair
    if main_repair["removed_face_count"] != 1:
        raise RuntimeError(
            "F001 expected exactly one zero-area transition triangle, got "
            f"{main_repair['removed_face_count']}"
        )
    if (
        abs(main_repair["volume_delta_mm3"]) > 1.0e-9
        or abs(main_repair["area_delta_mm2"]) > 1.0e-9
        or main_repair["bounds_max_abs_delta_mm"] > 1.0e-9
    ):
        raise RuntimeError("F001 zero-area repair changed geometric invariants")
    assert_manifold(main, "F001 repaired main")

    log("Tessellating and uniting F002 clipped top-right cap")
    cap = tessellate_shape(tp._top_right_clipped_cap(), "F002_cap")
    result = boolean_union(main, cap, "F001_F002_union")
    audit["operations"].append({"feature": "F002", "stats": mesh_stats(result)})

    boss_solids = [
        tp._clipped_boss_solid(bx, bz, y0, y1)
        for _, bx, bz, y0, y1 in tp.BOSSES
    ]
    for feature_index, boss in enumerate(boss_solids, start=3):
        log(f"Applying F{feature_index:03d} boss union")
        boss_mesh = tessellate_shape(boss, f"F{feature_index:03d}_boss")
        result = boolean_union(
            result,
            boss_mesh,
            f"F{feature_index:03d}_union",
        )
        audit["operations"].append(
            {"feature": f"F{feature_index:03d}", "stats": mesh_stats(result)}
        )

    log("Applying F006 counterbore cut")
    counterbore = tessellate_shape(
        tp._subtract_cylindrical_bore(
            tp.MAIN_X,
            tp.MAIN_Z,
            tp.COUNTERBORE_RADIUS,
            tp.Y_COUNTERBORE_LOW,
            tp.Y_COUNTERBORE_HIGH,
        ),
        "F006_counterbore",
    )
    result = boolean_cut(result, counterbore, "F006_cut")
    audit["operations"].append({"feature": "F006", "stats": mesh_stats(result)})

    log("Applying F007 anti-rotation key union")
    key = tessellate_shape(tp._anti_rotation_key_solid(), "F007_key")
    result = boolean_union(result, key, "F007_union")
    audit["operations"].append({"feature": "F007", "stats": mesh_stats(result)})

    log("Applying F008 through-bore cut")
    through = tessellate_shape(
        tp._subtract_cylindrical_bore(
            tp.MAIN_X,
            tp.MAIN_Z,
            tp.THROUGH_RADIUS,
            tp.Y_COUNTERBORE_HIGH,
            tp.Y_TOP,
        ),
        "F008_through_bore",
    )
    result = boolean_cut(result, through, "F008_cut")
    audit["operations"].append({"feature": "F008", "stats": mesh_stats(result)})

    for feature_index, (_, bx, bz, y0, y1) in enumerate(tp.MOUNT_BORES, start=9):
        log(f"Applying F{feature_index:03d} mounting-bore cut")
        bore = tessellate_shape(
            tp._subtract_cylindrical_bore(
                bx,
                bz,
                tp.MOUNT_BORE_RADIUS,
                y0,
                y1,
            ),
            f"F{feature_index:03d}_mount_bore",
        )
        result = boolean_cut(result, bore, f"F{feature_index:03d}_cut")
        audit["operations"].append(
            {"feature": f"F{feature_index:03d}", "stats": mesh_stats(result)}
        )

    for glyph_index, cutter in enumerate(engraving_cutters()):
        log(f"Applying F012 engraving face {glyph_index + 1}/5")
        cutter_mesh = tessellate_shape(
            cutter,
            f"F012_engraving_{glyph_index}",
        )
        result = boolean_cut(
            result,
            cutter_mesh,
            f"F012_cut_{glyph_index}",
        )
    audit["operations"].append({"feature": "F012", "stats": mesh_stats(result)})

    return result, audit


def directional_difference_volume(
    first: trimesh.Trimesh,
    second: trimesh.Trimesh,
    label: str,
) -> tuple[float, dict[str, Any]]:
    result = as_mesh(
        trimesh.boolean.difference(
            [first, second],
            engine="manifold",
            check_volume=True,
        ),
        label,
    )
    volume = float(abs(result.volume)) if len(result.faces) else 0.0
    return volume, mesh_stats(result)


def main() -> int:
    GENERATED.mkdir(parents=True, exist_ok=True)
    FEATURES.mkdir(parents=True, exist_ok=True)
    report_path = GENERATED / "feature_tree_validation_report.json"
    report: dict[str, Any] = {"overall_pass": False}

    reference_sha = hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
    if reference_sha != EXPECTED_REFERENCE_SHA256:
        raise RuntimeError(
            f"Reference checksum mismatch: {reference_sha}"
        )
    report["reference_sha256"] = reference_sha

    log("Running Strict SROT source audit")
    srot = run_srot(GENERATED / "strict_srot_report.json")
    report["strict_srot"] = srot
    if not srot["pass"]:
        raise RuntimeError("Strict SROT audit failed")

    log("Loading and topology-splitting immutable reference")
    reference_raw = as_mesh(
        trimesh.load_mesh(REFERENCE, process=True),
        "reference",
    )
    reference_mesh, reference_topology_audit, reference_topology_checks = (
        topology_split_reference(reference_raw)
    )
    if not all(reference_topology_checks.values()):
        raise RuntimeError("Reference topology split failed")
    assert_manifold(reference_mesh, "reference topology-split mesh")
    report["reference_topology_audit"] = reference_topology_audit
    report["reference_topology_checks"] = reference_topology_checks

    log("Building analytic F001-F012 OpenCascade solid")
    model = tp.build_top()
    if not model.is_valid or len(model.solids()) != 1:
        raise RuntimeError("Analytic Build123d result is not one valid solid")
    step_path = GENERATED / "top_parametric.step"
    export_step(model, step_path)

    log("Evaluating identical F001-F012 tree as manifold feature meshes")
    generated_mesh, feature_audit = build_feature_mesh_tree()
    assert_manifold(generated_mesh, "final feature-tree mesh")
    stl_path = GENERATED / "top_parametric.stl"
    generated_mesh.export(stl_path)
    generated_reload = as_mesh(
        trimesh.load_mesh(stl_path, process=True),
        "reloaded generated STL",
    )
    assert_manifold(generated_reload, "reloaded generated STL")

    ref_volume = float(abs(reference_raw.volume))
    ref_area = float(reference_raw.area)
    ref_com = np.asarray(reference_raw.center_mass, dtype=float)
    ref_bounds = np.asarray(reference_raw.bounds, dtype=float)
    bbox_diagonal = float(np.linalg.norm(ref_bounds[1] - ref_bounds[0]))

    gen_volume = float(model.volume)
    gen_area = float(model.area)
    gen_com = vector3(model.center(CenterOf.MASS))
    model_bbox = model.bounding_box()
    gen_bounds = np.array(
        [
            [model_bbox.min.X, model_bbox.min.Y, model_bbox.min.Z],
            [model_bbox.max.X, model_bbox.max.Y, model_bbox.max.Z],
        ],
        dtype=float,
    )
    com_shift = float(np.linalg.norm(gen_com - ref_com))

    log("Computing generated-minus-reference Manifold difference")
    generated_minus_reference, gmr_audit = directional_difference_volume(
        generated_mesh,
        reference_mesh,
        "generated_minus_reference",
    )
    log("Computing reference-minus-generated Manifold difference")
    reference_minus_generated, rmg_audit = directional_difference_volume(
        reference_mesh,
        generated_mesh,
        "reference_minus_generated",
    )
    symmetric_volume = generated_minus_reference + reference_minus_generated

    mesh_volume = float(abs(generated_reload.volume))
    mesh_area = float(generated_reload.area)
    mesh_com = np.asarray(generated_reload.center_mass, dtype=float)
    mesh_brep_com_shift = float(np.linalg.norm(mesh_com - gen_com))

    metrics = {
        "reference_volume_mm3": ref_volume,
        "generated_brep_volume_mm3": gen_volume,
        "volume_difference_mm3": gen_volume - ref_volume,
        "volume_difference_percent": pct(gen_volume - ref_volume, ref_volume),
        "reference_area_mm2": ref_area,
        "generated_brep_area_mm2": gen_area,
        "area_difference_mm2": gen_area - ref_area,
        "area_difference_percent": pct(gen_area - ref_area, ref_area),
        "reference_com_mm": ref_com.tolist(),
        "generated_brep_com_mm": gen_com.tolist(),
        "com_delta_mm": (gen_com - ref_com).tolist(),
        "com_shift_mm": com_shift,
        "com_shift_percent_of_bbox_diagonal": com_shift / bbox_diagonal * 100.0,
        "reference_bbox_mm": ref_bounds.tolist(),
        "generated_brep_bbox_mm": gen_bounds.tolist(),
        "bbox_absolute_delta_mm": np.abs(gen_bounds - ref_bounds).tolist(),
        "generated_stl_volume_mm3": mesh_volume,
        "stl_brep_volume_difference_percent": pct(mesh_volume - gen_volume, gen_volume),
        "generated_stl_area_mm2": mesh_area,
        "stl_brep_area_difference_percent": pct(mesh_area - gen_area, gen_area),
        "generated_stl_com_mm": mesh_com.tolist(),
        "stl_brep_com_shift_mm": mesh_brep_com_shift,
        "stl_brep_com_shift_percent_of_bbox_diagonal": (
            mesh_brep_com_shift / bbox_diagonal * 100.0
        ),
        "generated_minus_reference_volume_mm3": generated_minus_reference,
        "reference_minus_generated_volume_mm3": reference_minus_generated,
        "symmetric_difference_volume_mm3": symmetric_volume,
        "symmetric_difference_percent": symmetric_volume / ref_volume * 100.0,
    }
    checks = {
        "strict_srot": bool(srot["pass"]),
        "reference_checksum": reference_sha == EXPECTED_REFERENCE_SHA256,
        "reference_topology_preserved": all(reference_topology_checks.values()),
        "generated_brep_single_valid_solid": bool(
            model.is_valid and len(model.solids()) == 1
        ),
        "generated_stl_watertight": bool(generated_reload.is_watertight),
        "generated_stl_single_component": (
            len(generated_reload.split(only_watertight=False)) == 1
        ),
        "volume": metrics["volume_difference_percent"] < 0.1,
        "surface_area": metrics["area_difference_percent"] < 0.1,
        "center_of_mass": metrics["com_shift_percent_of_bbox_diagonal"] < 0.1,
        "stl_step_volume_congruence": (
            metrics["stl_brep_volume_difference_percent"] < 0.1
        ),
        "stl_step_area_congruence": (
            metrics["stl_brep_area_difference_percent"] < 0.1
        ),
        "stl_step_com_congruence": (
            metrics["stl_brep_com_shift_percent_of_bbox_diagonal"] < 0.1
        ),
        "symmetric_difference": metrics["symmetric_difference_percent"] < 0.01,
    }

    report.update(
        {
            "generator": str((ROOT / "top_parametric.py").resolve()),
            "generated_step": str(step_path.resolve()),
            "generated_stl": str(stl_path.resolve()),
            "boolean_engine": "Manifold3D through Trimesh, bidirectional differences",
            "mesh_generation": (
                "Independent tessellation of analytic Build123d F001-F012 "
                "operands followed by the identical ordered feature tree"
            ),
            "thresholds": {
                "volume_difference_percent_max": 0.1,
                "surface_area_difference_percent_max": 0.1,
                "com_shift_percent_of_bbox_diagonal_max": 0.1,
                "symmetric_difference_percent_max": 0.01,
                "stl_step_congruence_percent_max": 0.1,
            },
            "feature_mesh_audit": feature_audit,
            "generated_stl_stats": mesh_stats(generated_reload),
            "generated_minus_reference_audit": gmr_audit,
            "reference_minus_generated_audit": rmg_audit,
            "metrics": metrics,
            "checks": checks,
            "overall_pass": all(checks.values()),
        }
    )
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
