"""Decompose the beneficial mounting-bore radius adjustment by bore subset.

The common +0.00025 mm radius improved the full Boolean result. This sweep
applies +0.00025 mm and +0.00030 mm to every non-empty subset of the three
mounting bores while preserving each center and all other analytic features.
"""

from __future__ import annotations

from itertools import combinations
import json

import trimesh

import top_parametric as tp
import validate_direct_final_solid as validator
from validate_fast_manifold import topology_split_reference
from validate_feature_tree_manifold import as_mesh

LINEAR = 0.006722
ANGULAR = 0.270
DELTAS = (0.00025, 0.00030)
NAMES = tuple(item[0] for item in tp.MOUNT_BORES)
SUBSETS = tuple(
    frozenset(combo)
    for length in range(1, len(NAMES) + 1)
    for combo in combinations(NAMES, length)
)
ROOT = validator.ROOT / "generated" / "individual_mount_bore_radius_subsets"
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


def install(selected: frozenset[str], delta: float) -> None:
    def selective_subtract(x: float, z: float, radius: float, y0: float, y1: float):
        if abs(radius - base_radius) <= 1.0e-12:
            for name, (cx, cz, cy0, cy1) in centers.items():
                if (
                    name in selected
                    and abs(x - cx) <= 1.0e-12
                    and abs(z - cz) <= 1.0e-12
                    and abs(y0 - cy0) <= 1.0e-12
                    and abs(y1 - cy1) <= 1.0e-12
                ):
                    return original_subtract(x, z, base_radius + delta, y0, y1)
        return original_subtract(x, z, radius, y0, y1)

    tp._subtract_cylindrical_bore = selective_subtract


def restore() -> None:
    tp._subtract_cylindrical_bore = original_subtract


rows = []
validator.OUTPUT = ROOT / "baseline"
try:
    baseline = validator.validate_candidate(LINEAR, reference_raw, reference)
    baseline.update({"selected_bores": [], "radius_delta_mm": 0.0})
except Exception as exc:
    baseline = {"selected_bores": [], "radius_delta_mm": 0.0, "strict_pass": False, "exception": repr(exc)}
rows.append(baseline)
print(json.dumps(baseline, indent=2), flush=True)

for delta in DELTAS:
    for selected in SUBSETS:
        selected_tag = "_".join(sorted(selected))
        tag = f"{selected_tag}_dr_{delta:+.7f}".replace("+", "p").replace("-", "m").replace(".", "p")
        validator.OUTPUT = ROOT / tag
        print(f"=== selected={sorted(selected)} delta={delta:+.7f} mm ===", flush=True)
        try:
            install(selected, delta)
            row = validator.validate_candidate(LINEAR, reference_raw, reference)
            row.update(
                {
                    "selected_bores": sorted(selected),
                    "radius_delta_mm": delta,
                    "selected_radius_mm": base_radius + delta,
                    "unselected_radius_mm": base_radius,
                }
            )
        except Exception as exc:
            row = {
                "selected_bores": sorted(selected),
                "radius_delta_mm": delta,
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
    "base_mount_bore_radius_mm": base_radius,
    "candidates": rows,
    "ranking": valid,
    "best": valid[0] if valid else None,
    "overall_pass": bool(valid and valid[0]["strict_pass"]),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== INDIVIDUAL MOUNT-BORE SUBSET RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
