from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path("validation_run")
OUT = ROOT / "validation/historical_stl_comparison.json"
TARGET_PERCENT = 0.1


def load(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load(path, force="mesh", process=True)
    if not isinstance(mesh, trimesh.Trimesh):
        mesh = trimesh.util.concatenate(tuple(mesh.dump()))
    mesh.remove_unreferenced_vertices()
    return mesh


def pct(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1.0e-15) * 100.0


def properties(mesh: trimesh.Trimesh) -> dict:
    return {
        "watertight": bool(mesh.is_watertight),
        "volume_mm3": float(abs(mesh.volume)),
        "area_mm2": float(mesh.area),
        "center_of_mass_mm": np.asarray(mesh.center_mass, dtype=float).tolist(),
        "bounds_mm": np.asarray(mesh.bounds, dtype=float).tolist(),
        "bbox_diagonal_mm": float(np.linalg.norm(mesh.bounds[1] - mesh.bounds[0])),
        "thickness_y_mm": float(mesh.bounds[1, 1] - mesh.bounds[0, 1]),
    }


official = properties(load(ROOT / "source/midplate_official.stl"))
historical = properties(load(ROOT / "historical_reference/midplate_reference.stl"))
o_com = np.asarray(official["center_of_mass_mm"], dtype=float)
h_com = np.asarray(historical["center_of_mass_mm"], dtype=float)
o_bounds = np.asarray(official["bounds_mm"], dtype=float)
h_bounds = np.asarray(historical["bounds_mm"], dtype=float)
com_shift = float(np.linalg.norm(h_com - o_com))
bbox_max = float(np.max(np.abs(h_bounds - o_bounds)))
comparison = {
    "volume_difference_percent": pct(historical["volume_mm3"], official["volume_mm3"]),
    "area_difference_percent": pct(historical["area_mm2"], official["area_mm2"]),
    "com_shift_mm": com_shift,
    "com_difference_percent": com_shift / official["bbox_diagonal_mm"] * 100.0,
    "bbox_max_difference_mm": bbox_max,
    "bbox_difference_percent": bbox_max / official["bbox_diagonal_mm"] * 100.0,
}
checks = {
    "both_watertight": official["watertight"] and historical["watertight"],
    "official_exact_3mm_thickness": abs(official["thickness_y_mm"] - 3.0) < 1.0e-6,
    "historical_exact_3mm_thickness": abs(historical["thickness_y_mm"] - 3.0) < 1.0e-6,
    "volume": comparison["volume_difference_percent"] < TARGET_PERCENT,
    "area": comparison["area_difference_percent"] < TARGET_PERCENT,
    "com": comparison["com_difference_percent"] < TARGET_PERCENT,
    "bbox": comparison["bbox_difference_percent"] < TARGET_PERCENT,
}
checks = {name: bool(value) for name, value in checks.items()}
result = "PASS" if all(checks.values()) else "FAIL"
payload = {
    "result": result,
    "target_percent": TARGET_PERCENT,
    "historical_dxf_commit": "af0286154cd09af451bc475aabfbe1807123da26",
    "historical_dxf_git_blob_sha1": "ee1d16cfa34f71b3e2e434c5fba1ac9b40346945",
    "official_stl_git_blob_sha1": "d478c7ccd883702b420697c0646e41bba70d8733",
    "official": official,
    "historical_direct_dxf_reference": historical,
    "comparison": comparison,
    "checks": checks,
}
OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(f"HISTORICAL_OFFICIAL_STL_VALIDATION={result}")
for name, value in comparison.items():
    print(f"historical_vs_official_{name}={value:.15g}")
for name, value in checks.items():
    print(f"HISTORICAL_CHECK_{name}={'PASS' if value else 'FAIL'}")
raise SystemExit(0 if result == "PASS" else 1)
