"""Finite-difference sensitivity sweep for remaining high-impact features.

All candidates remain genuine analytic Build123d models. Each candidate changes
one named scalar feature by a sub-micron or one-micron amount, then performs the
full native final-solid tessellation and bidirectional Boolean validation.
"""

from __future__ import annotations

import json

import trimesh

import top_parametric as tp
import validate_direct_final_solid as validator
from validate_fast_manifold import topology_split_reference
from validate_feature_tree_manifold import as_mesh

LINEAR = 0.006722
ANGULAR = 0.270
DELTAS = (-0.00100, -0.00025, 0.00025, 0.00100)
PARAMETERS = (
    "counterbore_radius",
    "through_radius",
    "main_x",
    "main_z",
    "mount_bore_radius",
    "key_width",
    "top_fillet_radius",
    "boss_radius_global",
)
ROOT = validator.ROOT / "generated" / "remaining_feature_sensitivity"
ROOT.mkdir(parents=True, exist_ok=True)
validator.ANGULAR_TOLERANCE = ANGULAR

reference_raw = as_mesh(trimesh.load_mesh(validator.REFERENCE, process=True), "reference")
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference topology audit failed")

BASE = {
    "COUNTERBORE_RADIUS": tp.COUNTERBORE_RADIUS,
    "THROUGH_RADIUS": tp.THROUGH_RADIUS,
    "MAIN_X": tp.MAIN_X,
    "MAIN_Z": tp.MAIN_Z,
    "MOUNT_BORE_RADIUS": tp.MOUNT_BORE_RADIUS,
    "KEY_WIDTH": tp.KEY_WIDTH,
    "TOP_FILLET_RADIUS": tp.TOP_FILLET_RADIUS,
    "Y_FILLET_LOW": tp.Y_FILLET_LOW,
    "BOSS_RADIUS": tp.BOSS_RADIUS,
}


def restore() -> None:
    for name, value in BASE.items():
        setattr(tp, name, value)


def install(parameter: str, delta: float) -> dict:
    restore()
    if parameter == "counterbore_radius":
        tp.COUNTERBORE_RADIUS = BASE["COUNTERBORE_RADIUS"] + delta
        return {"value_mm": tp.COUNTERBORE_RADIUS}
    if parameter == "through_radius":
        tp.THROUGH_RADIUS = BASE["THROUGH_RADIUS"] + delta
        return {"value_mm": tp.THROUGH_RADIUS}
    if parameter == "main_x":
        tp.MAIN_X = BASE["MAIN_X"] + delta
        return {"value_mm": tp.MAIN_X}
    if parameter == "main_z":
        tp.MAIN_Z = BASE["MAIN_Z"] + delta
        return {"value_mm": tp.MAIN_Z}
    if parameter == "mount_bore_radius":
        tp.MOUNT_BORE_RADIUS = BASE["MOUNT_BORE_RADIUS"] + delta
        return {"value_mm": tp.MOUNT_BORE_RADIUS}
    if parameter == "key_width":
        tp.KEY_WIDTH = BASE["KEY_WIDTH"] + delta
        return {"value_mm": tp.KEY_WIDTH}
    if parameter == "top_fillet_radius":
        tp.TOP_FILLET_RADIUS = BASE["TOP_FILLET_RADIUS"] + delta
        tp.Y_FILLET_LOW = tp.Y_TOP - tp.TOP_FILLET_RADIUS
        return {
            "value_mm": tp.TOP_FILLET_RADIUS,
            "dependent_y_fillet_low_mm": tp.Y_FILLET_LOW,
        }
    if parameter == "boss_radius_global":
        tp.BOSS_RADIUS = BASE["BOSS_RADIUS"] + delta
        return {"value_mm": tp.BOSS_RADIUS}
    raise ValueError(parameter)


rows = []
validator.OUTPUT = ROOT / "baseline"
try:
    baseline = validator.validate_candidate(LINEAR, reference_raw, reference)
    baseline.update({"parameter": "baseline", "delta_mm": 0.0})
except Exception as exc:
    baseline = {"parameter": "baseline", "delta_mm": 0.0, "strict_pass": False, "exception": repr(exc)}
rows.append(baseline)
print(json.dumps(baseline, indent=2), flush=True)

for parameter in PARAMETERS:
    for delta in DELTAS:
        tag = f"{parameter}_{delta:+.7f}".replace("+", "p").replace("-", "m").replace(".", "p")
        validator.OUTPUT = ROOT / tag
        print(f"=== sensitivity {parameter} delta={delta:+.7f} mm ===", flush=True)
        try:
            metadata = install(parameter, delta)
            row = validator.validate_candidate(LINEAR, reference_raw, reference)
            row.update({"parameter": parameter, "delta_mm": delta, **metadata})
        except Exception as exc:
            row = {
                "parameter": parameter,
                "delta_mm": delta,
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
    "base_values": BASE,
    "candidates": rows,
    "ranking": valid,
    "best": valid[0] if valid else None,
    "overall_pass": bool(valid and valid[0]["strict_pass"]),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== REMAINING FEATURE SENSITIVITY RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
