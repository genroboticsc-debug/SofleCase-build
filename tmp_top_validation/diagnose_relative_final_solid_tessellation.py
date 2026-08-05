"""Diagnose OCCT relative-deflection topology on the final analytic solid.

The reference bottom mounting bores contain a mid-height Y=59.25 ring and a
lower-boundary phase not reproduced by the best absolute-deflection mesh. This
matrix records ring counts and angular phases before expensive Boolean tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.StlAPI import StlAPI_Writer

import top_parametric as tp

ROOT = Path(__file__).resolve().parent / "generated" / "relative_tessellation_diagnostic"
ROOT.mkdir(parents=True, exist_ok=True)
RELATIVE_LINEAR = (0.000040, 0.000050, 0.000060, 0.000067, 0.000075, 0.000090, 0.000120)
ANGULAR = (0.090, 0.100, 0.110, 0.120, 0.150)

TARGET = {
    "bottom_left_bore_y56_count": 59,
    "bottom_left_bore_y56_first_angle_deg": 5.77711204,
    "bottom_left_bore_y59p25_count": 58,
    "bottom_left_bore_y59p25_first_angle_deg": 6.20689919,
}


def ring(mesh: trimesh.Trimesh, cx: float, cz: float, radius: float, y: float) -> dict:
    vertices = np.asarray(mesh.vertices, dtype=float)
    radial = np.linalg.norm(vertices[:, [0, 2]] - np.array([cx, cz]), axis=1)
    mask = (np.abs(radial - radius) <= 0.010) & (np.abs(vertices[:, 1] - y) <= 0.001)
    points = vertices[mask]
    if len(points) == 0:
        return {"count": 0, "angles_deg": [], "first_angle_deg": None, "step_median_deg": None}
    angles = np.mod(
        np.degrees(np.arctan2(points[:, 2] - cz, points[:, 0] - cx)),
        360.0,
    )
    angles = np.sort(angles)
    steps = np.diff(np.r_[angles, angles[0] + 360.0])
    return {
        "count": int(len(angles)),
        "angles_deg": [float(value) for value in angles],
        "first_angle_deg": float(angles[0]),
        "step_median_deg": float(np.median(steps)),
        "step_min_deg": float(np.min(steps)),
        "step_max_deg": float(np.max(steps)),
    }


def score(item: dict) -> float:
    y56 = item["bottom_left_bore_y56"]
    ymid = item["bottom_left_bore_y59p25"]
    value = 10.0 * abs(y56["count"] - TARGET["bottom_left_bore_y56_count"])
    value += 10.0 * abs(ymid["count"] - TARGET["bottom_left_bore_y59p25_count"])
    if y56["first_angle_deg"] is not None:
        value += abs(y56["first_angle_deg"] - TARGET["bottom_left_bore_y56_first_angle_deg"])
    else:
        value += 1000.0
    if ymid["first_angle_deg"] is not None:
        value += abs(ymid["first_angle_deg"] - TARGET["bottom_left_bore_y59p25_first_angle_deg"])
    else:
        value += 1000.0
    return float(value)


rows = []
for linear in RELATIVE_LINEAR:
    for angular in ANGULAR:
        tag = f"rel_{linear:.9f}_ang_{angular:.6f}".replace(".", "p")
        path = ROOT / f"{tag}.stl"
        print(f"=== relative={linear:.9f} angular={angular:.6f} ===", flush=True)
        row = {"relative_linear": linear, "angular_tolerance_rad": angular}
        try:
            model = tp.build_top()
            mesher = BRepMesh_IncrementalMesh(
                model.wrapped,
                linear,
                True,
                angular,
                True,
            )
            mesher.Perform()
            if not mesher.IsDone():
                raise RuntimeError("OCCT relative meshing did not complete")
            writer = StlAPI_Writer()
            writer.ASCIIMode = False
            if not writer.Write(model.wrapped, str(path)):
                raise RuntimeError("OCCT relative STL write failed")
            mesh = trimesh.load_mesh(path, process=True)
            if isinstance(mesh, trimesh.Scene):
                mesh = mesh.to_mesh()
            _, cx, cz, _, _ = tp.BOSSES[0]
            row.update(
                {
                    "vertices": int(len(mesh.vertices)),
                    "faces": int(len(mesh.faces)),
                    "raw_watertight": bool(mesh.is_watertight),
                    "volume_mm3": float(mesh.volume),
                    "area_mm2": float(mesh.area),
                    "bottom_left_bore_y56": ring(mesh, cx, cz, tp.MOUNT_BORE_RADIUS, 56.0),
                    "bottom_left_bore_y59p25": ring(mesh, cx, cz, tp.MOUNT_BORE_RADIUS, 59.25),
                    "bottom_left_outer_y56": ring(mesh, cx, cz, tp.BOSS_RADIUS, 56.0),
                }
            )
            row["topology_score"] = score(row)
        except Exception as exc:
            row["exception"] = repr(exc)
            row["topology_score"] = 1.0e9
        rows.append(row)
        print(json.dumps(row, indent=2), flush=True)

rows.sort(key=lambda item: item["topology_score"])
report = {"target": TARGET, "candidates": rows, "best": rows[0] if rows else None}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== RELATIVE FINAL-SOLID TESSELLATION RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
