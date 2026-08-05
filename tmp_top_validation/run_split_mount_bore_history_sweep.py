"""Test geometry-identical mounting-bore feature-history splits at Y=59.25.

The reference STL contains an exact mid-height ring on both bottom mounting
bores at the analytic midpoint (56.0 + 62.5) / 2 = 59.25. The recovered model
currently cuts each bore as one cylinder. This sweep performs the same exact
coaxial cut as two ordered analytic cylinders, changing only BRep history and
surface partitioning, never the final nominal geometry.
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
MID_Y = (56.0 + 62.5) / 2.0
ROOT = validator.ROOT / "generated" / "split_mount_bore_history_sweep"
ROOT.mkdir(parents=True, exist_ok=True)
validator.ANGULAR_TOLERANCE = ANGULAR
ORIGINAL_BUILD_TOP = tp.build_top

VARIANTS = (
    ("baseline", frozenset(), "low_high"),
    ("bl_low_high", frozenset({"bottom_left"}), "low_high"),
    ("bl_high_low", frozenset({"bottom_left"}), "high_low"),
    ("br_low_high", frozenset({"bottom_right"}), "low_high"),
    ("br_high_low", frozenset({"bottom_right"}), "high_low"),
    ("both_low_high", frozenset({"bottom_left", "bottom_right"}), "low_high"),
    ("both_high_low", frozenset({"bottom_left", "bottom_right"}), "high_low"),
)

reference_raw = as_mesh(trimesh.load_mesh(validator.REFERENCE, process=True), "reference")
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference topology audit failed")


def build_with_split_bores(split_names: frozenset[str], order: str):
    main_rolling_body = tp._main_rolling_body()
    top_right_clipped_cap = tp._top_right_clipped_cap()
    result = main_rolling_body.fuse(top_right_clipped_cap)
    if len(result.solids()) != 1 or not result.is_valid:
        raise RuntimeError("Outer-body union is invalid")

    boss_solids = [
        tp._clipped_boss_solid(bx, bz, y0, y1)
        for _, bx, bz, y0, y1 in tp.BOSSES
    ]
    for boss_solid in boss_solids[:2]:
        result = result.fuse(boss_solid)
        if len(result.solids()) != 1 or not result.is_valid:
            raise RuntimeError("Bottom boss union is invalid")
    result = result.fuse(boss_solids[2], tol=1.0e-6)
    if len(result.solids()) != 1 or not result.is_valid:
        raise RuntimeError("Top-right boss union is invalid")

    result = result.cut(
        tp._subtract_cylindrical_bore(
            tp.MAIN_X,
            tp.MAIN_Z,
            tp.COUNTERBORE_RADIUS,
            tp.Y_COUNTERBORE_LOW,
            tp.Y_COUNTERBORE_HIGH,
        )
    )
    result = result.fuse(tp._anti_rotation_key_solid())
    result = result.cut(
        tp._subtract_cylindrical_bore(
            tp.MAIN_X,
            tp.MAIN_Z,
            tp.THROUGH_RADIUS,
            tp.Y_COUNTERBORE_HIGH,
            tp.Y_TOP,
        )
    )

    for name, bx, bz, y0, y1 in tp.MOUNT_BORES:
        if name in split_names:
            segments = [(y0, MID_Y), (MID_Y, y1)]
            if order == "high_low":
                segments.reverse()
        else:
            segments = [(y0, y1)]
        for segment_y0, segment_y1 in segments:
            result = result.cut(
                tp._subtract_cylindrical_bore(
                    bx,
                    bz,
                    tp.MOUNT_BORE_RADIUS,
                    segment_y0,
                    segment_y1,
                )
            )
            if len(result.solids()) != 1 or not result.is_valid:
                raise RuntimeError(
                    f"Mounting-bore cut invalid for {name} {segment_y0} {segment_y1}"
                )

    with tp.BuildSketch(tp.xz_plane(tp.Y_BODY_LOW)) as engraving_placed:
        tp.add(tp._engraving_profile_sketch())
    engraving_faces = list(engraving_placed.sketch.faces())
    if len(engraving_faces) != 5:
        raise RuntimeError(f"Engraving face count mismatch: {len(engraving_faces)}")
    for engraving_face in engraving_faces:
        result = result.cut(
            tp.extrude(
                engraving_face,
                amount=-(tp.Y_ENGRAVE_HIGH - tp.Y_BODY_LOW),
            )
        )
        if len(result.solids()) != 1 or not result.is_valid:
            raise RuntimeError("Engraving cut is invalid")

    result.label = "top_parametric_split_bore_history"
    return result


rows = []
for name, split_names, order in VARIANTS:
    validator.OUTPUT = ROOT / name
    print(f"=== split-bore history variant {name} ===", flush=True)
    try:
        if name == "baseline":
            tp.build_top = ORIGINAL_BUILD_TOP
        else:
            tp.build_top = lambda s=split_names, o=order: build_with_split_bores(s, o)
        row = validator.validate_candidate(LINEAR, reference_raw, reference)
        row.update(
            {
                "variant": name,
                "split_bores": sorted(split_names),
                "cut_order": order,
                "analytic_mid_y_mm": MID_Y,
            }
        )
    except Exception as exc:
        row = {
            "variant": name,
            "split_bores": sorted(split_names),
            "cut_order": order,
            "analytic_mid_y_mm": MID_Y,
            "strict_pass": False,
            "exception": repr(exc),
        }
    finally:
        tp.build_top = ORIGINAL_BUILD_TOP
    rows.append(row)
    print(json.dumps(row, indent=2), flush=True)

valid = [row for row in rows if "symmetric_difference_percent" in row]
valid.sort(key=lambda row: row["symmetric_difference_percent"])
report = {
    "reference_topology_audit": topology_audit,
    "reference_topology_checks": topology_checks,
    "analytic_mid_y_mm": MID_Y,
    "linear_tolerance_mm": LINEAR,
    "angular_tolerance_rad": ANGULAR,
    "candidates": rows,
    "best": valid[0] if valid else None,
    "overall_pass": bool(valid and valid[0]["strict_pass"]),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== SPLIT MOUNT-BORE HISTORY RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
