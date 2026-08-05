"""Sweep only the parametric seam orientation of the exact bottom-left boss."""

from __future__ import annotations

import json
import math

import trimesh

import top_parametric as tp
import validate_direct_final_solid as validator
from validate_fast_manifold import topology_split_reference
from validate_feature_tree_manifold import as_mesh

LINEAR = 0.006722
ANGULAR = 0.270
SEAM_DEGREES = (
    -5.0, -4.0, -3.0, -2.0, -1.5, -1.0, -0.75, -0.5, -0.25,
    0.0,
    0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0,
    15.0, 30.0, 45.0, 90.0, 180.0,
)
ROOT = validator.ROOT / "generated" / "bottom_left_boss_seam_sweep"
ROOT.mkdir(parents=True, exist_ok=True)
validator.ANGULAR_TOLERANCE = ANGULAR
ORIGINAL_CLIPPED_BOSS = tp._clipped_boss_solid

reference_raw = as_mesh(trimesh.load_mesh(validator.REFERENCE, process=True), "reference")
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference topology audit failed")


def install_seam(seam_degrees: float) -> None:
    angle = math.radians(seam_degrees)

    def seam_oriented_boss(x: float, z: float, y0: float, y1: float):
        if x < 0.0 and abs(y0 - tp.Y_BACK) <= 1.0e-12:
            plane = tp.Plane(
                origin=(x, y0, z),
                x_dir=(math.cos(angle), 0.0, math.sin(angle)),
                z_dir=(0.0, -1.0, 0.0),
            )
            with tp.BuildSketch(plane) as circle_profile:
                tp.Circle(tp.BOSS_RADIUS)
            cylinder = tp.extrude(
                circle_profile.sketch.face(),
                amount=-(y1 - y0),
            )
            envelope = tp._solid_from_sketch(tp.outer_profile_sketch(), y0, y1)
            clipped = cylinder & envelope
            if len(clipped.solids()) != 1 or not clipped.is_valid:
                raise RuntimeError("Seam-oriented bottom-left boss is invalid")
            return clipped
        return ORIGINAL_CLIPPED_BOSS(x, z, y0, y1)

    tp._clipped_boss_solid = seam_oriented_boss


rows = []
for seam_degrees in SEAM_DEGREES:
    tag = f"seam_{seam_degrees:+.6f}_deg".replace("+", "p").replace("-", "m").replace(".", "p")
    validator.OUTPUT = ROOT / tag
    print(f"=== bottom-left boss seam {seam_degrees:+.6f} deg ===", flush=True)
    try:
        install_seam(seam_degrees)
        row = validator.validate_candidate(LINEAR, reference_raw, reference)
        row["bottom_left_boss_seam_degrees"] = seam_degrees
    except Exception as exc:
        row = {
            "bottom_left_boss_seam_degrees": seam_degrees,
            "strict_pass": False,
            "exception": repr(exc),
        }
    finally:
        tp._clipped_boss_solid = ORIGINAL_CLIPPED_BOSS
    rows.append(row)
    print(json.dumps(row, indent=2), flush=True)

valid = [row for row in rows if "symmetric_difference_percent" in row]
valid.sort(key=lambda row: row["symmetric_difference_percent"])
report = {
    "reference_topology_audit": topology_audit,
    "reference_topology_checks": topology_checks,
    "linear_tolerance_mm": LINEAR,
    "angular_tolerance_rad": ANGULAR,
    "candidates": rows,
    "best": valid[0] if valid else None,
    "overall_pass": bool(valid and valid[0]["strict_pass"]),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== BOTTOM-LEFT BOSS SEAM SWEEP RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
