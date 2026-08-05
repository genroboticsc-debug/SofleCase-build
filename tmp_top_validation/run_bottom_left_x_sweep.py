"""Sweep the recovered bottom-left boss and bore X center only.

Residual localization shows generated-only volume on the left side of the
bottom-left boss and reference-only wedges on its right side. This test moves
the exact concentric boss/bore pair together along global X while preserving
radius, Z center, Y limits, outer envelope, and every other recovered feature.
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
X_DELTAS = (
    -0.00200, -0.00150, -0.00100, -0.00075, -0.00050, -0.00025,
     0.00000,  0.00025,  0.00050,  0.00075,  0.00100,  0.00125,
     0.00150,  0.00200,  0.00250,  0.00300,  0.00400,  0.00500,
     0.00750,  0.01000,
)
ROOT = validator.ROOT / "generated" / "bottom_left_x_sweep"
ROOT.mkdir(parents=True, exist_ok=True)
validator.ANGULAR_TOLERANCE = ANGULAR

reference_raw = as_mesh(
    trimesh.load_mesh(validator.REFERENCE, process=True),
    "reference",
)
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference topology audit failed")

original_bosses = tp.BOSSES
original_bores = tp.MOUNT_BORES
base_name, base_x, base_z, base_y0, base_y1 = original_bosses[0]
bore_name, bore_x, bore_z, bore_y0, bore_y1 = original_bores[0]


def install_candidate(x_delta: float) -> None:
    candidate_x = base_x + x_delta
    tp.BOSSES = (
        (base_name, candidate_x, base_z, base_y0, base_y1),
        *original_bosses[1:],
    )
    tp.MOUNT_BORES = (
        (bore_name, bore_x + x_delta, bore_z, bore_y0, bore_y1),
        *original_bores[1:],
    )


def restore_source() -> None:
    tp.BOSSES = original_bosses
    tp.MOUNT_BORES = original_bores


rows = []
for x_delta in X_DELTAS:
    tag = f"dx_{x_delta:+.7f}".replace("+", "p").replace("-", "m").replace(".", "p")
    validator.OUTPUT = ROOT / tag
    print(f"=== bottom-left shared X delta {x_delta:+.7f} mm ===", flush=True)
    try:
        install_candidate(x_delta)
        row = validator.validate_candidate(LINEAR, reference_raw, reference)
        row.update(
            {
                "bottom_left_center_x_delta_mm": x_delta,
                "bottom_left_boss_center_x_mm": base_x + x_delta,
                "bottom_left_bore_center_x_mm": bore_x + x_delta,
                "bottom_left_center_z_mm": base_z,
                "bottom_left_boss_radius_mm": tp.BOSS_RADIUS,
            }
        )
    except Exception as exc:
        row = {
            "bottom_left_center_x_delta_mm": x_delta,
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
    "base_bottom_left_bore": list(original_bores[0]),
    "candidates": rows,
    "best": valid[0] if valid else None,
    "overall_pass": bool(valid and valid[0]["strict_pass"]),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== BOTTOM-LEFT SHARED X SWEEP RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
