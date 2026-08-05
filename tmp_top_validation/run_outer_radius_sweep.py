"""Refine the shared analytic outer-shell radius around 4.3 mm."""

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
RADIUS_DELTAS = (
    -0.0030, -0.0025, -0.0020, -0.0015, -0.0010, -0.00075,
    -0.0005, -0.00025, 0.0, 0.00025, 0.0005, 0.00075,
    0.0010, 0.0015, 0.0020, 0.0025, 0.0030,
)
ROOT = validator.ROOT / "generated" / "outer_radius_sweep"
ROOT.mkdir(parents=True, exist_ok=True)
validator.ANGULAR_TOLERANCE = ANGULAR

reference_raw = as_mesh(trimesh.load_mesh(validator.REFERENCE, process=True), "reference")
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference topology audit failed")

BASE_RADIUS = tp.OUTER_RADIUS
BASE_STEP_X = tp.TR_STEP_X
BASE_ARC_START_DEG = tp.TR_ARC_START_DEG
BASE_JUNCTION_EDGE_LENGTH = tp.TR_JUNCTION_EDGE_LENGTH


def install_radius(delta: float) -> None:
    radius = BASE_RADIUS + delta
    vertical = tp.TR_STEP_Z - tp.TR_Z
    if radius <= abs(vertical):
        raise RuntimeError("Outer radius cannot reach the recovered top-right step")
    step_x = tp.TR_X + math.sqrt(radius**2 - vertical**2)
    tp.OUTER_RADIUS = radius
    tp.TR_STEP_X = step_x
    tp.TR_ARC_START_DEG = math.degrees(math.atan2(vertical, step_x - tp.TR_X))
    tp.TR_JUNCTION_EDGE_LENGTH = step_x - tp.X_RIGHT_WALL


def restore() -> None:
    tp.OUTER_RADIUS = BASE_RADIUS
    tp.TR_STEP_X = BASE_STEP_X
    tp.TR_ARC_START_DEG = BASE_ARC_START_DEG
    tp.TR_JUNCTION_EDGE_LENGTH = BASE_JUNCTION_EDGE_LENGTH


rows = []
for delta in RADIUS_DELTAS:
    tag = f"outer_radius_delta_{delta:+.7f}".replace("+", "p").replace("-", "m").replace(".", "p")
    validator.OUTPUT = ROOT / tag
    print(f"=== outer radius delta={delta:+.7f} mm ===", flush=True)
    try:
        install_radius(delta)
        row = validator.validate_candidate(LINEAR, reference_raw, reference)
        row.update(
            {
                "outer_radius_delta_mm": delta,
                "outer_radius_mm": BASE_RADIUS + delta,
                "dependent_tr_step_x_mm": tp.TR_STEP_X,
                "dependent_tr_arc_start_deg": tp.TR_ARC_START_DEG,
            }
        )
    except Exception as exc:
        row = {
            "outer_radius_delta_mm": delta,
            "outer_radius_mm": BASE_RADIUS + delta,
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
    "base_outer_radius_mm": BASE_RADIUS,
    "candidates": rows,
    "best": valid[0] if valid else None,
    "overall_pass": bool(valid and valid[0]["strict_pass"]),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== OUTER RADIUS SWEEP RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
