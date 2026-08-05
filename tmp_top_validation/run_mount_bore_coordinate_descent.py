"""Coordinate-descent sweep for the three independent mounting-bore radii.

All three bores benefit from a small radius increase. This sweep fixes two
bores at +0.00025 mm and resolves the third from 0 to +0.00060 mm in 0.00005 mm
increments, preserving every bore center and all unrelated analytic features.
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
FIXED_DELTA = 0.00025
AXIS_DELTAS = tuple(index * 0.00005 for index in range(0, 13))
NAMES = tuple(item[0] for item in tp.MOUNT_BORES)
ROOT = validator.ROOT / "generated" / "mount_bore_coordinate_descent"
ROOT.mkdir(parents=True, exist_ok=True)
validator.ANGULAR_TOLERANCE = ANGULAR

reference_raw = as_mesh(trimesh.load_mesh(validator.REFERENCE, process=True), "reference")
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference topology audit failed")

base_radius = tp.MOUNT_BORE_RADIUS
original_subtract = tp._subtract_cylindrical_bore
centers = {
    name: (x, z, y0, y1)
    for name, x, z, y0, y1 in tp.MOUNT_BORES
}


def install(delta_by_name: dict[str, float]) -> None:
    def selective_subtract(x: float, z: float, radius: float, y0: float, y1: float):
        if abs(radius - base_radius) <= 1.0e-12:
            for name, (cx, cz, cy0, cy1) in centers.items():
                if (
                    abs(x - cx) <= 1.0e-12
                    and abs(z - cz) <= 1.0e-12
                    and abs(y0 - cy0) <= 1.0e-12
                    and abs(y1 - cy1) <= 1.0e-12
                ):
                    return original_subtract(
                        x,
                        z,
                        base_radius + delta_by_name[name],
                        y0,
                        y1,
                    )
        return original_subtract(x, z, radius, y0, y1)

    tp._subtract_cylindrical_bore = selective_subtract


def restore() -> None:
    tp._subtract_cylindrical_bore = original_subtract


rows = []
all_fixed = {name: FIXED_DELTA for name in NAMES}
validator.OUTPUT = ROOT / "all_fixed"
try:
    install(all_fixed)
    baseline = validator.validate_candidate(LINEAR, reference_raw, reference)
    baseline.update(
        {
            "swept_axis": "all_fixed",
            "delta_by_bore_mm": all_fixed,
        }
    )
except Exception as exc:
    baseline = {
        "swept_axis": "all_fixed",
        "delta_by_bore_mm": all_fixed,
        "strict_pass": False,
        "exception": repr(exc),
    }
finally:
    restore()
rows.append(baseline)
print(json.dumps(baseline, indent=2), flush=True)

for axis in NAMES:
    for axis_delta in AXIS_DELTAS:
        delta_by_name = {name: FIXED_DELTA for name in NAMES}
        delta_by_name[axis] = axis_delta
        tag = (
            f"axis_{axis}_delta_{axis_delta:+.8f}"
            .replace("+", "p")
            .replace("-", "m")
            .replace(".", "p")
        )
        validator.OUTPUT = ROOT / tag
        print(
            f"=== axis={axis} delta={axis_delta:+.8f} mm; others={FIXED_DELTA:+.8f} ===",
            flush=True,
        )
        try:
            install(delta_by_name)
            row = validator.validate_candidate(LINEAR, reference_raw, reference)
            row.update(
                {
                    "swept_axis": axis,
                    "axis_delta_mm": axis_delta,
                    "delta_by_bore_mm": delta_by_name,
                    "radius_by_bore_mm": {
                        name: base_radius + delta
                        for name, delta in delta_by_name.items()
                    },
                }
            )
        except Exception as exc:
            row = {
                "swept_axis": axis,
                "axis_delta_mm": axis_delta,
                "delta_by_bore_mm": delta_by_name,
                "strict_pass": False,
                "exception": repr(exc),
            }
        finally:
            restore()
        rows.append(row)
        print(json.dumps(row, indent=2), flush=True)

valid = [row for row in rows if "symmetric_difference_percent" in row]
valid.sort(key=lambda row: row["symmetric_difference_percent"])
best_by_axis = {}
for axis in NAMES:
    axis_rows = [row for row in valid if row.get("swept_axis") == axis]
    best_by_axis[axis] = axis_rows[0] if axis_rows else None
report = {
    "reference_topology_audit": topology_audit,
    "reference_topology_checks": topology_checks,
    "linear_tolerance_mm": LINEAR,
    "angular_tolerance_rad": ANGULAR,
    "base_mount_bore_radius_mm": base_radius,
    "fixed_delta_mm": FIXED_DELTA,
    "candidates": rows,
    "ranking": valid,
    "best_by_axis": best_by_axis,
    "best": valid[0] if valid else None,
    "overall_pass": bool(valid and valid[0]["strict_pass"]),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== MOUNTING-BORE COORDINATE DESCENT RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
