"""Sweep only the bottom-left boss radius and common boss/bore Z center."""

from __future__ import annotations

import json

import trimesh

import top_parametric as tp
import validate_direct_final_solid as validator
from validate_fast_manifold import topology_split_reference
from validate_feature_tree_manifold import as_mesh

LINEAR = 0.006722
ANGULAR = 0.270
RADIUS_DELTAS = (-0.0025, -0.0020, -0.0015, -0.0010, -0.0005, 0.0)
Z_DELTAS = (-0.0030, -0.0025, -0.0020, -0.0015, -0.0010, -0.0005, 0.0)
ROOT = validator.ROOT / "generated" / "bottom_left_boss_sweep"
ROOT.mkdir(parents=True, exist_ok=True)
validator.ANGULAR_TOLERANCE = ANGULAR

reference_raw = as_mesh(trimesh.load_mesh(validator.REFERENCE, process=True), "reference")
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference topology audit failed")

original_bosses = tp.BOSSES
original_bores = tp.MOUNT_BORES
original_clipped_boss = tp._clipped_boss_solid
base_name, base_x, base_z, base_y0, base_y1 = original_bosses[0]


def install_candidate(radius_delta: float, z_delta: float) -> None:
    candidate_z = base_z + z_delta
    candidate_radius = tp.BOSS_RADIUS + radius_delta
    tp.BOSSES = (
        (base_name, base_x, candidate_z, base_y0, base_y1),
        *original_bosses[1:],
    )
    bore_name, bore_x, bore_z, bore_y0, bore_y1 = original_bores[0]
    tp.MOUNT_BORES = (
        (bore_name, bore_x, bore_z + z_delta, bore_y0, bore_y1),
        *original_bores[1:],
    )

    def isolated_clipped_boss(x: float, z: float, y0: float, y1: float):
        if x < 0.0 and abs(y0 - base_y0) <= 1.0e-12:
            saved_radius = tp.BOSS_RADIUS
            tp.BOSS_RADIUS = candidate_radius
            try:
                return original_clipped_boss(x, z, y0, y1)
            finally:
                tp.BOSS_RADIUS = saved_radius
        return original_clipped_boss(x, z, y0, y1)

    tp._clipped_boss_solid = isolated_clipped_boss


def restore_source() -> None:
    tp.BOSSES = original_bosses
    tp.MOUNT_BORES = original_bores
    tp._clipped_boss_solid = original_clipped_boss


rows = []
for radius_delta in RADIUS_DELTAS:
    for z_delta in Z_DELTAS:
        tag = (
            f"dr_{radius_delta:+.7f}_dz_{z_delta:+.7f}"
            .replace("+", "p")
            .replace("-", "m")
            .replace(".", "p")
        )
        validator.OUTPUT = ROOT / tag
        print(
            f"=== bottom-left candidate radius_delta={radius_delta:+.7f} "
            f"z_delta={z_delta:+.7f} ===",
            flush=True,
        )
        try:
            install_candidate(radius_delta, z_delta)
            row = validator.validate_candidate(LINEAR, reference_raw, reference)
            row.update(
                {
                    "bottom_left_boss_radius_delta_mm": radius_delta,
                    "bottom_left_boss_radius_mm": tp.BOSS_RADIUS + radius_delta,
                    "bottom_left_center_z_delta_mm": z_delta,
                    "bottom_left_center_z_mm": base_z + z_delta,
                    "bottom_left_bore_center_z_mm": original_bores[0][2] + z_delta,
                }
            )
        except Exception as exc:
            row = {
                "bottom_left_boss_radius_delta_mm": radius_delta,
                "bottom_left_center_z_delta_mm": z_delta,
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
print("=== BOTTOM-LEFT BOSS SWEEP RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
