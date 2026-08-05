"""Sweep OCCT angular deflection at the best absolute linear deflection."""

from __future__ import annotations

import json
from pathlib import Path

import trimesh

import validate_direct_final_solid as validator
from validate_fast_manifold import topology_split_reference
from validate_feature_tree_manifold import as_mesh

LINEAR = 0.006722
ANGLES = (
    0.070,
    0.080,
    0.090,
    0.095,
    0.100,
    0.105,
    0.110,
    0.115,
    0.120,
    0.130,
    0.150,
    0.200,
    0.300,
    0.600,
)
ROOT = validator.ROOT / "generated" / "direct_angular_sweep"
ROOT.mkdir(parents=True, exist_ok=True)

reference_raw = as_mesh(
    trimesh.load_mesh(validator.REFERENCE, process=True),
    "reference",
)
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference zero-coordinate topology audit failed")

rows = []
for angle in ANGLES:
    print(f"=== angular candidate {angle:.6f} rad ===", flush=True)
    validator.ANGULAR_TOLERANCE = angle
    validator.OUTPUT = ROOT / f"angular_{angle:.6f}".replace(".", "p")
    try:
        row = validator.validate_candidate(LINEAR, reference_raw, reference)
    except Exception as exc:
        row = {
            "linear_tolerance_mm": LINEAR,
            "angular_tolerance_rad": angle,
            "relative_deflection": False,
            "strict_pass": False,
            "exception": repr(exc),
        }
    rows.append(row)
    print(json.dumps(row, indent=2), flush=True)

valid = [row for row in rows if "symmetric_difference_percent" in row]
valid.sort(key=lambda row: row["symmetric_difference_percent"])
report = {
    "reference_topology_audit": topology_audit,
    "reference_topology_checks": topology_checks,
    "linear_tolerance_mm": LINEAR,
    "candidates": rows,
    "best": valid[0] if valid else None,
    "overall_pass": bool(valid and valid[0]["strict_pass"]),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== ANGULAR SWEEP RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
