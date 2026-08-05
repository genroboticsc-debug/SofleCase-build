"""Diagnose OCCT IMeshTools interior tessellation parameters on final solid.

This uses only the analytic Build123d F001-F012 BRep. It tests native OCCT
interior-node controls to reproduce the reference's adaptive mid-height bore
ring without importing or replaying reference triangles into the generator.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.IMeshTools import IMeshTools_Parameters
from OCP.StlAPI import StlAPI_Writer

import top_parametric as tp

ROOT = Path(__file__).resolve().parent / "generated" / "imeshtools_diagnostic"
ROOT.mkdir(parents=True, exist_ok=True)
LINEAR = 0.006722
ANGULAR = 0.270
TARGET_MID_Y = 59.25

VARIANTS = (
    {"name": "default_fields"},
    {"name": "internal_false", "InternalVerticesMode": False},
    {"name": "internal_true", "InternalVerticesMode": True},
    {"name": "control_surface_false", "ControlSurfaceDeflection": False},
    {"name": "control_surface_true", "ControlSurfaceDeflection": True},
    {"name": "interior_defl_0p001", "DeflectionInterior": 0.001},
    {"name": "interior_defl_0p002", "DeflectionInterior": 0.002},
    {"name": "interior_defl_0p003", "DeflectionInterior": 0.003},
    {"name": "interior_defl_0p004", "DeflectionInterior": 0.004},
    {"name": "interior_defl_0p006722", "DeflectionInterior": 0.006722},
    {"name": "interior_defl_0p010", "DeflectionInterior": 0.010},
    {"name": "interior_angle_0p05", "AngleInterior": 0.05},
    {"name": "interior_angle_0p10", "AngleInterior": 0.10},
    {"name": "interior_angle_0p15", "AngleInterior": 0.15},
    {"name": "interior_angle_0p20", "AngleInterior": 0.20},
    {"name": "interior_angle_0p27", "AngleInterior": 0.27},
    {"name": "interior_combo", "DeflectionInterior": 0.003, "AngleInterior": 0.10, "InternalVerticesMode": True, "ControlSurfaceDeflection": True},
)


def ring_at(mesh: trimesh.Trimesh, y: float, radius: float) -> dict:
    _, cx, cz, _, _ = tp.BOSSES[0]
    vertices = np.asarray(mesh.vertices, dtype=float)
    radial = np.linalg.norm(vertices[:, [0, 2]] - np.array([cx, cz]), axis=1)
    mask = (np.abs(radial - radius) <= 0.010) & (np.abs(vertices[:, 1] - y) <= 0.001)
    points = vertices[mask]
    if len(points) == 0:
        return {"count": 0, "first_angle_deg": None, "step_median_deg": None}
    angles = np.sort(np.mod(np.degrees(np.arctan2(points[:, 2] - cz, points[:, 0] - cx)), 360.0))
    steps = np.diff(np.r_[angles, angles[0] + 360.0])
    return {
        "count": int(len(angles)),
        "first_angle_deg": float(angles[0]),
        "step_median_deg": float(np.median(steps)),
        "angles_deg": [float(value) for value in angles],
    }


def bore_y_levels(mesh: trimesh.Trimesh) -> list[dict]:
    _, cx, cz, _, _ = tp.BOSSES[0]
    vertices = np.asarray(mesh.vertices, dtype=float)
    radial = np.linalg.norm(vertices[:, [0, 2]] - np.array([cx, cz]), axis=1)
    mask = np.abs(radial - tp.MOUNT_BORE_RADIUS) <= 0.010
    levels = []
    rounded = np.round(vertices[mask, 1], 6)
    for y in np.unique(rounded):
        count = int(np.sum(rounded == y))
        if count >= 8:
            levels.append({"y_mm": float(y), "count": count})
    return levels


probe = IMeshTools_Parameters()
attributes = {}
for name in dir(probe):
    if name.startswith("_"):
        continue
    try:
        value = getattr(probe, name)
        if isinstance(value, (bool, int, float, str)):
            attributes[name] = value
    except Exception:
        pass
print("=== IMESHTOOLS DEFAULT ATTRIBUTES ===", flush=True)
print(json.dumps(attributes, indent=2, default=str), flush=True)

rows = []
for variant in VARIANTS:
    name = variant["name"]
    output = ROOT / f"{name}.stl"
    row = {"name": name, "requested": variant}
    print(f"=== IMeshTools variant {name} ===", flush=True)
    try:
        model = tp.build_top()
        params = IMeshTools_Parameters()
        params.Deflection = LINEAR
        params.Angle = ANGULAR
        params.Relative = False
        params.InParallel = True
        for key, value in variant.items():
            if key == "name":
                continue
            setattr(params, key, value)
        effective = {}
        for key in (
            "Deflection", "Angle", "DeflectionInterior", "AngleInterior",
            "MinSize", "Relative", "InParallel", "InternalVerticesMode",
            "ControlSurfaceDeflection", "ForceFaceDeflection", "AdjustMinSize",
            "AllowQualityDecrease", "CleanModel",
        ):
            if hasattr(params, key):
                try:
                    effective[key] = getattr(params, key)
                except Exception:
                    pass
        mesher = BRepMesh_IncrementalMesh(model.wrapped, params)
        mesher.Perform()
        if not mesher.IsDone():
            raise RuntimeError("IMeshTools mesher did not complete")
        writer = StlAPI_Writer()
        writer.ASCIIMode = False
        if not writer.Write(model.wrapped, str(output)):
            raise RuntimeError("STL writer failed")
        mesh = trimesh.load_mesh(output, process=True)
        if isinstance(mesh, trimesh.Scene):
            mesh = mesh.to_mesh()
        row.update(
            {
                "effective": effective,
                "vertices": int(len(mesh.vertices)),
                "faces": int(len(mesh.faces)),
                "raw_watertight": bool(mesh.is_watertight),
                "volume_mm3": float(mesh.volume),
                "area_mm2": float(mesh.area),
                "bore_y_levels": bore_y_levels(mesh),
                "bore_y56": ring_at(mesh, 56.0, tp.MOUNT_BORE_RADIUS),
                "bore_y59p25": ring_at(mesh, TARGET_MID_Y, tp.MOUNT_BORE_RADIUS),
                "boss_outer_y56": ring_at(mesh, 56.0, tp.BOSS_RADIUS),
            }
        )
        row["topology_score"] = (
            10.0 * abs(row["bore_y56"]["count"] - 59)
            + 10.0 * abs(row["bore_y59p25"]["count"] - 58)
            + abs((row["bore_y56"]["first_angle_deg"] or 1000.0) - 5.77711204)
            + abs((row["bore_y59p25"]["first_angle_deg"] or 1000.0) - 6.20689919)
        )
    except Exception as exc:
        row["exception"] = repr(exc)
        row["topology_score"] = 1.0e9
    rows.append(row)
    print(json.dumps(row, indent=2, default=str), flush=True)

rows.sort(key=lambda item: item["topology_score"])
report = {
    "default_attributes": attributes,
    "linear_deflection_mm": LINEAR,
    "angular_deflection_rad": ANGULAR,
    "target_mid_y_mm": TARGET_MID_Y,
    "candidates": rows,
    "best": rows[0] if rows else None,
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
print("=== IMESHTOOLS DIAGNOSTIC RESULT ===", flush=True)
print(json.dumps(report, indent=2, default=str), flush=True)
