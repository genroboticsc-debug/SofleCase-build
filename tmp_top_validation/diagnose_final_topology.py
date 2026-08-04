"""Diagnose exact F002 cap-union and final topology regularization variants."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import traceback

import numpy as np
import trimesh
from build123d import CenterOf, export_stl

import top_parametric as tp

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated" / "final_topology_diagnostic"
OUT.mkdir(parents=True, exist_ok=True)


def vector3(value):
    return [float(value.X), float(value.Y), float(value.Z)]


def topology(mesh: trimesh.Trimesh) -> dict:
    incidence = defaultdict(int)
    degenerate_edges = 0
    for triangle in np.asarray(mesh.faces, dtype=np.int64):
        for a, b in (
            (int(triangle[0]), int(triangle[1])),
            (int(triangle[1]), int(triangle[2])),
            (int(triangle[2]), int(triangle[0])),
        ):
            edge = (a, b) if a < b else (b, a)
            if a == b:
                degenerate_edges += 1
            incidence[edge] += 1
    counts = Counter(incidence.values())
    abnormal = {str(key): int(value) for key, value in sorted(counts.items()) if key != 2}
    boundary_vertices = set()
    boundary_bounds = None
    for edge, count in incidence.items():
        if count == 1:
            boundary_vertices.update(edge)
    if boundary_vertices:
        points = np.asarray(mesh.vertices)[sorted(boundary_vertices)]
        boundary_bounds = [points.min(axis=0).tolist(), points.max(axis=0).tolist()]
    return {
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "is_volume": bool(mesh.is_volume),
        "euler_number": int(mesh.euler_number),
        "edge_incidence_histogram": {str(key): int(value) for key, value in sorted(counts.items())},
        "abnormal_edge_incidence": abnormal,
        "degenerate_directed_edges": int(degenerate_edges),
        "boundary_vertex_count": int(len(boundary_vertices)),
        "boundary_bounds_mm": boundary_bounds,
        "mesh_volume_mm3": float(mesh.volume),
        "mesh_area_mm2": float(mesh.area),
        "mesh_bounds_mm": np.asarray(mesh.bounds, dtype=float).tolist(),
    }


def outer_union(mode: str):
    main = tp._main_rolling_body()
    cap = tp._top_right_clipped_cap()
    if mode == "nominal":
        return main.fuse(cap)
    if mode == "nominal_clean":
        return main.fuse(cap).clean()
    if mode.startswith("tol_"):
        tolerance = float(mode.split("_", 1)[1])
        return main.fuse(cap, tol=tolerance)
    if mode.startswith("tolclean_"):
        tolerance = float(mode.split("_", 1)[1])
        return main.fuse(cap, tol=tolerance).clean()
    raise ValueError(mode)


def build_variant(mode: str, final_clean: bool = False):
    result = outer_union(mode)
    if len(result.solids()) != 1 or not result.is_valid:
        raise RuntimeError(f"Invalid F001-F002 union for {mode}")

    boss_solids = [
        tp._clipped_boss_solid(bx, bz, y0, y1)
        for _, bx, bz, y0, y1 in tp.BOSSES
    ]
    for boss in boss_solids[:2]:
        result = result.fuse(boss)
    result = result.fuse(boss_solids[2], tol=1.0e-6)

    counterbore = tp._subtract_cylindrical_bore(
        tp.MAIN_X,
        tp.MAIN_Z,
        tp.COUNTERBORE_RADIUS,
        tp.Y_COUNTERBORE_LOW,
        tp.Y_COUNTERBORE_HIGH,
    )
    result = result.cut(counterbore)
    result = result.fuse(tp._anti_rotation_key_solid())
    through_bore = tp._subtract_cylindrical_bore(
        tp.MAIN_X,
        tp.MAIN_Z,
        tp.THROUGH_RADIUS,
        tp.Y_COUNTERBORE_HIGH,
        tp.Y_TOP,
    )
    result = result.cut(through_bore)
    for _, bx, bz, y0, y1 in tp.MOUNT_BORES:
        result = result.cut(
            tp._subtract_cylindrical_bore(
                bx,
                bz,
                tp.MOUNT_BORE_RADIUS,
                y0,
                y1,
            )
        )
    engraving = tp._solid_from_sketch(
        tp._engraving_profile_sketch(),
        tp.Y_BODY_LOW,
        tp.Y_ENGRAVE_HIGH,
    )
    result = result.cut(engraving)
    if final_clean:
        result = result.clean()
    if len(result.solids()) != 1 or not result.is_valid:
        raise RuntimeError(f"Invalid final solid for {mode}, final_clean={final_clean}")
    return result


def inspect_tessellation(model) -> dict:
    attempts = []
    for name, args, kwargs in (
        ("positional", (0.001, 0.1), {}),
        ("keywords", (), {"tolerance": 0.001, "angular_tolerance": 0.1}),
    ):
        try:
            vertices, faces = model.tessellate(*args, **kwargs)
            coords = np.asarray(
                [[float(v.X), float(v.Y), float(v.Z)] for v in vertices],
                dtype=float,
            )
            triangles = np.asarray(faces, dtype=np.int64)
            mesh = trimesh.Trimesh(
                vertices=coords,
                faces=triangles,
                process=True,
                validate=False,
            )
            return {
                "success": True,
                "call": name,
                "topology": topology(mesh),
            }
        except Exception as exc:
            attempts.append(f"{name}: {type(exc).__name__}: {exc}")
    return {"success": False, "attempts": attempts}


def main() -> int:
    variants = []
    for mode in (
        "nominal",
        "nominal_clean",
        "tol_1e-7",
        "tolclean_1e-7",
        "tol_1e-6",
        "tolclean_1e-6",
        "tol_1e-5",
        "tolclean_1e-5",
    ):
        for final_clean in (False, True):
            label = f"{mode}__finalclean_{int(final_clean)}"
            entry = {"label": label, "mode": mode, "final_clean": final_clean}
            try:
                model = build_variant(mode, final_clean=final_clean)
                bbox = model.bounding_box()
                entry["brep"] = {
                    "valid": bool(model.is_valid),
                    "solid_count": len(model.solids()),
                    "volume_mm3": float(model.volume),
                    "area_mm2": float(model.area),
                    "com_mm": vector3(model.center(CenterOf.MASS)),
                    "bounds_mm": [
                        [bbox.min.X, bbox.min.Y, bbox.min.Z],
                        [bbox.max.X, bbox.max.Y, bbox.max.Z],
                    ],
                    "face_count": len(model.faces()),
                    "edge_count": len(model.edges()),
                }
                path = OUT / f"{label}.stl"
                export_stl(
                    model,
                    path,
                    tolerance=0.001,
                    angular_tolerance=0.1,
                    ascii_format=False,
                )
                mesh = trimesh.load_mesh(path, process=True)
                entry["exported_stl"] = topology(mesh)
                entry["direct_tessellation"] = inspect_tessellation(model)
                entry["success"] = True
            except Exception as exc:
                entry["success"] = False
                entry["exception"] = f"{type(exc).__name__}: {exc}"
                entry["traceback"] = traceback.format_exc()
            variants.append(entry)
            print(json.dumps(entry, indent=2), flush=True)

    report = {"variants": variants}
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
