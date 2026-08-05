"""Fine sweep of the common exact mounting-bore radius.

The remaining-feature sensitivity matrix improved the full symmetric difference
at +0.00025 mm. This sweep resolves the local optimum at 0.05 micrometre steps
without changing bore centers, boss geometry, or any other feature.
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
DELTAS = tuple(index * 0.00005 for index in range(0, 17))
ROOT = validator.ROOT / "generated" / "mount_bore_radius_fine_sweep"
ROOT.mkdir(parents=True, exist_ok=True)
validator.ANGULAR_TOLERANCE = ANGULAR

reference_raw = as_mesh(trimesh.load_mesh(validator.REFERENCE, process=True), "reference")
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference topology audit failed")

base_radius = tp.MOUNT_BORE_RADIUS
rows = []
for delta in DELTAS:
    tag = f"dr_{delta:+.8f}".replace("+", "p").replace("-", "m").replace(".", "p")
    validator.OUTPUT = ROOT / tag
    print(f"=== common mounting-bore radius delta {delta:+.8f} mm ===", flush=True)
    try:
        tp.MOUNT_BORE_RADIUS = base_radius + delta
        row = validator.validate_candidate(LINEAR, reference_raw, reference)
        row.update(
            {
                "mount_bore_radius_delta_mm": delta,
                "mount_bore_radius_mm": tp.MOUNT_BORE_RADIUS,
            }
        )
    except Exception as exc:
        row = {
            "mount_bore_radius_delta_mm": delta,
            "mount_bore_radius_mm": base_radius + delta,
            "strict_pass": False,
            "exception": repr(exc),
        }
    finally:
        tp.MOUNT_BORE_RADIUS = base_radius
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
    "best": valid[0] if valid else None,
    "overall_pass": bool(valid and valid[0]["strict_pass"]),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== MOUNTING-BORE RADIUS FINE SWEEP RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
