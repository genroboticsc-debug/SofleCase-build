from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path("validation_run")
OUT = ROOT / "validation/official_stl_comparison.json"
TARGET_PERCENT = 0.1


def load(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load(path, force="mesh", process=True)
    if not isinstance(mesh, trimesh.Trimesh):
        mesh = trimesh.util.concatenate(tuple(mesh.dump()))
    mesh.remove_unreferenced_vertices()
    return mesh


def pct(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1.0e-15) * 100.0


def metrics(mesh: trimesh.Trimesh) -> dict:
    return {
        "watertight": bool(mesh.is_watertight),
        "volume_mm3": float(abs(mesh.volume)),
        "area_mm2": float(mesh.area),
        "center_of_mass_mm": np.asarray(mesh.center_mass, dtype=float).tolist(),
        "bounds_mm": np.asarray(mesh.bounds, dtype=float).tolist(),
        "bbox_diagonal_mm": float(np.linalg.norm(mesh.bounds[1] - mesh.bounds[0])),
        "thickness_y_mm": float(mesh.bounds[1, 1] - mesh.bounds[0, 1]),
    }


def compare(candidate: dict, official: dict) -> dict:
    c_com = np.asarray(candidate["center_of_mass_mm"], dtype=float)
    o_com = np.asarray(official["center_of_mass_mm"], dtype=float)
    c_bounds = np.asarray(candidate["bounds_mm"], dtype=float)
    o_bounds = np.asarray(official["bounds_mm"], dtype=float)
    com_shift = float(np.linalg.norm(c_com - o_com))
    bbox_max = float(np.max(np.abs(c_bounds - o_bounds)))
    return {
        "volume_difference_percent": pct(candidate["volume_mm3"], official["volume_mm3"]),
        "area_difference_percent": pct(candidate["area_mm2"], official["area_mm2"]),
        "com_shift_mm": com_shift,
        "com_difference_percent": com_shift / official["bbox_diagonal_mm"] * 100.0,
        "bbox_max_difference_mm": bbox_max,
        "bbox_difference_percent": bbox_max / official["bbox_diagonal_mm"] * 100.0,
    }


official = metrics(load(ROOT / "source/midplate_official.stl"))
reference = metrics(load(ROOT / "reference/midplate_reference.stl"))
generated = metrics(load(ROOT / "generated/midplate_parametric.stl"))
reference_vs_official = compare(reference, official)
generated_vs_official = compare(generated, official)

checks = {
    "all_watertight": official["watertight"] and reference["watertight"] and generated["watertight"],
    "official_exact_3mm_thickness": abs(official["thickness_y_mm"] - 3.0) < 1.0e-6,
    "reference_volume": reference_vs_official["volume_difference_percent"] < TARGET_PERCENT,
    "reference_area": reference_vs_official["area_difference_percent"] < TARGET_PERCENT,
    "reference_com": reference_vs_official["com_difference_percent"] < TARGET_PERCENT,
    "reference_bbox": reference_vs_official["bbox_difference_percent"] < TARGET_PERCENT,
    "generated_volume": generated_vs_official["volume_difference_percent"] < TARGET_PERCENT,
    "generated_area": generated_vs_official["area_difference_percent"] < TARGET_PERCENT,
    "generated_com": generated_vs_official["com_difference_percent"] < TARGET_PERCENT,
    "generated_bbox": generated_vs_official["bbox_difference_percent"] < TARGET_PERCENT,
}
checks = {name: bool(value) for name, value in checks.items()}
result = "PASS" if all(checks.values()) else "FAIL"
payload = {
    "result": result,
    "target_percent": TARGET_PERCENT,
    "official": official,
    "reference": reference,
    "generated": generated,
    "reference_vs_official": reference_vs_official,
    "generated_vs_official": generated_vs_official,
    "checks": checks,
}
OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(f"OFFICIAL_STL_VALIDATION={result}")
for group_name in ("reference_vs_official", "generated_vs_official"):
    for name, value in payload[group_name].items():
        print(f"{group_name}_{name}={value:.15g}")
for name, value in checks.items():
    print(f"OFFICIAL_CHECK_{name}={'PASS' if value else 'FAIL'}")
raise SystemExit(0 if result == "PASS" else 1)
