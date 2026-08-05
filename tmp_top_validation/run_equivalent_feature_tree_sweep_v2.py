"""Test exact-geometry Boolean histories with the recovered F005 tolerance."""

from __future__ import annotations

import json

import trimesh

import top_parametric as tp
import validate_direct_final_solid as validator
from validate_fast_manifold import topology_split_reference
from validate_feature_tree_manifold import as_mesh

LINEAR = 0.006722
ANGULAR = 0.270
F005_TOLERANCE = 1.0e-6
ROOT = validator.ROOT / "generated" / "equivalent_feature_tree_sweep_v2"
ROOT.mkdir(parents=True, exist_ok=True)
validator.ANGULAR_TOLERANCE = ANGULAR
ORIGINAL_BUILD_TOP = tp.build_top

reference_raw = as_mesh(trimesh.load_mesh(validator.REFERENCE, process=True), "reference")
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference topology audit failed")


def make_operands():
    outer = tp._main_rolling_body().fuse(tp._top_right_clipped_cap())
    bosses = [
        tp._clipped_boss_solid(x, z, y0, y1)
        for _, x, z, y0, y1 in tp.BOSSES
    ]
    counterbore = tp._subtract_cylindrical_bore(
        tp.MAIN_X, tp.MAIN_Z, tp.COUNTERBORE_RADIUS,
        tp.Y_COUNTERBORE_LOW, tp.Y_COUNTERBORE_HIGH,
    )
    key = tp._anti_rotation_key_solid()
    through = tp._subtract_cylindrical_bore(
        tp.MAIN_X, tp.MAIN_Z, tp.THROUGH_RADIUS,
        tp.Y_COUNTERBORE_HIGH, tp.Y_TOP,
    )
    mount_bores = [
        tp._subtract_cylindrical_bore(x, z, tp.MOUNT_BORE_RADIUS, y0, y1)
        for _, x, z, y0, y1 in tp.MOUNT_BORES
    ]
    engraving = tp._solid_from_sketch(
        tp._engraving_profile_sketch(), tp.Y_BODY_LOW, tp.Y_ENGRAVE_HIGH
    )
    return outer, bosses, counterbore, key, through, mount_bores, engraving


def fuse_boss(result, bosses, index):
    if index == 2:
        result = result.fuse(bosses[index], tol=F005_TOLERANCE)
    else:
        result = result.fuse(bosses[index])
    if len(result.solids()) != 1 or not result.is_valid:
        raise RuntimeError(f"Boss union {index} invalid")
    return result


def finish(result, counterbore, key, through, mount_bores, engraving):
    result = result.cut(counterbore)
    result = result.fuse(key)
    result = result.cut(through)
    for bore in mount_bores:
        result = result.cut(bore)
    result = result.cut(engraving)
    if len(result.solids()) != 1 or not result.is_valid:
        raise RuntimeError("Equivalent final tree invalid")
    result.label = "top_parametric"
    return result


def build_variant(name):
    outer, bosses, counterbore, key, through, mount_bores, engraving = make_operands()
    if name == "baseline":
        result = outer
        order = (0, 1, 2)
    elif name == "bottom_left_last":
        result = outer
        order = (1, 2, 0)
    elif name == "top_right_first":
        result = outer
        order = (2, 0, 1)
    elif name == "bottom_right_first":
        result = outer
        order = (1, 0, 2)
    elif name == "counterbore_pre_cut":
        result = outer.cut(counterbore)
        order = (0, 1, 2)
    elif name == "counterbore_pre_cut_bottom_left_last":
        result = outer.cut(counterbore)
        order = (1, 2, 0)
    elif name == "all_round_cuts_pre_and_post":
        result = outer.cut(counterbore).cut(through)
        for bore in mount_bores:
            result = result.cut(bore)
        order = (0, 1, 2)
    elif name == "clean_after_each":
        result = outer.clean()
        for index in (0, 1, 2):
            result = fuse_boss(result, bosses, index).clean()
        result = result.cut(counterbore).clean()
        result = result.fuse(key).clean()
        result = result.cut(through).clean()
        for bore in mount_bores:
            result = result.cut(bore).clean()
        result = result.cut(engraving).clean()
        if len(result.solids()) != 1 or not result.is_valid:
            raise RuntimeError("Cleaned final tree invalid")
        result.label = "top_parametric"
        return result
    else:
        raise ValueError(name)

    for index in order:
        result = fuse_boss(result, bosses, index)
    return finish(result, counterbore, key, through, mount_bores, engraving)


VARIANTS = (
    "baseline",
    "bottom_left_last",
    "top_right_first",
    "bottom_right_first",
    "counterbore_pre_cut",
    "counterbore_pre_cut_bottom_left_last",
    "all_round_cuts_pre_and_post",
    "clean_after_each",
)

rows = []
for variant in VARIANTS:
    print(f"=== equivalent feature-tree variant: {variant} ===", flush=True)
    validator.OUTPUT = ROOT / variant
    tp.build_top = lambda variant=variant: build_variant(variant)
    try:
        row = validator.validate_candidate(LINEAR, reference_raw, reference)
        row["feature_tree_variant"] = variant
    except Exception as exc:
        row = {"feature_tree_variant": variant, "strict_pass": False, "exception": repr(exc)}
    finally:
        tp.build_top = ORIGINAL_BUILD_TOP
    rows.append(row)
    print(json.dumps(row, indent=2), flush=True)

valid = [row for row in rows if "symmetric_difference_percent" in row]
valid.sort(key=lambda row: row["symmetric_difference_percent"])
report = {
    "reference_topology_audit": topology_audit,
    "reference_topology_checks": topology_checks,
    "linear_tolerance_mm": LINEAR,
    "angular_tolerance_rad": ANGULAR,
    "F005_boolean_tolerance_mm": F005_TOLERANCE,
    "candidates": rows,
    "best": valid[0] if valid else None,
    "overall_pass": bool(valid and valid[0]["strict_pass"]),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== EQUIVALENT FEATURE-TREE V2 RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
