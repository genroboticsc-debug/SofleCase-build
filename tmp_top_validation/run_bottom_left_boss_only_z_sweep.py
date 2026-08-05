"""Sweep only the bottom-left outer boss Z center, keeping its bore fixed.

Residual localization places the largest generated-only component above the
bottom-left boss center. This isolates the outer cylindrical boss Z position
from the independently recovered mounting-bore center.
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
Z_DELTAS = (
    -0.00500, -0.00400, -0.00300, -0.00250, -0.00200, -0.00150,
    -0.00125, -0.00100, -0.00075, -0.00050, -0.00025, 0.00000,
     0.00025, 0.00050, 0.00075, 0.00100, 0.00125, 0.00150,
     0.00200, 0.00300, 0.00400, 0.00500,
)
ROOT = validator.ROOT / "generated" / "bottom_left_boss_only_z_sweep"
ROOT.mkdir(parents=True, exist_ok=True)
validator.ANGULAR_TOLERANCE = ANGULAR

reference_raw = as_mesh(trimesh.load_mesh(validator.REFERENCE, process=True), "reference")
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference topology audit failed")

original_bosses = tp.BOSSES
base_name, base_x, base_z, base_y0, base_y1 = original_bosses[0]
fixed_bore = tuple(tp.MOUNT_BORES[0])


def install_candidate(z_delta: float) -> None:
    tp.BOSSES = (
        (base_name, base_x, base_z + z_delta, base_y0, base_y1),
        *original_bosses[1:],
    )


def restore_source() -> None:
    tp.BOSSES = original_bosses


rows = []
for z_delta in Z_DELTAS:
    tag = f"dz_{z_delta:+.7f}".replace("+", "p").replace("-", "m").replace(".", "p")
    validator.OUTPUT = ROOT / tag
    print(f"=== bottom-left outer boss-only Z delta {z_delta:+.7f} mm ===", flush=True)
    try:
        install_candidate(z_delta)
        row = validator.validate_candidate(LINEAR, reference_raw, reference)
        row.update(
            {
                "bottom_left_boss_center_z_delta_mm": z_delta,
                "bottom_left_boss_center_z_mm": base_z + z_delta,
                "bottom_left_bore_center_z_mm": fixed_bore[2],
                "bottom_left_boss_center_x_mm": base_x,
                "bottom_left_boss_radius_mm": tp.BOSS_RADIUS,
            }
        )
    except Exception as exc:
        row = {
            "bottom_left_boss_center_z_delta_mm": z_delta,
            "strict_pass": False,
            "exception": repr(exc),
        }
    finally:
        restore_source()
    rows.append(row)
    print(json.dumps(row, indent=2), flush=True)

valid = [row for row in rows if "symmetric_difference_percent" in row]
valid.sort(key=lambda row: row["symmetric_difference_percent"])
report = {
    "reference_topology_audit": topology_audit,
    "reference_topology_checks": topology_checks,
    "linear_tolerance_mm": LINEAR,
    "angular_tolerance_rad": ANGULAR,
    "base_bottom_left_boss": list(original_bosses[0]),
    "fixed_bottom_left_bore": list(fixed_bore),
    "candidates": rows,
    "best": valid[0] if valid else None,
    "overall_pass": bool(valid and valid[0]["strict_pass"]),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== BOTTOM-LEFT OUTER BOSS-ONLY Z SWEEP RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
