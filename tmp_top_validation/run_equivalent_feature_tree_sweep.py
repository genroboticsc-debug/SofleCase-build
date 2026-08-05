"""Test geometry-equivalent explicit Boolean histories for final STL edge phases."""

from __future__ import annotations

import json

import trimesh

import top_parametric as tp
import validate_direct_final_solid as validator
from validate_fast_manifold import topology_split_reference
from validate_feature_tree_manifold import as_mesh

LINEAR = 0.006722
ANGULAR = 0.270
ROOT = validator.ROOT / "generated" / "equivalent_feature_tree_sweep"
ROOT.mkdir(parents=True, exist_ok=True)
validator.ANGULAR_TOLERANCE = ANGULAR
ORIGINAL_BUILD_TOP = tp.build_top

reference_raw = as_mesh(trimesh.load_mesh(validator.REFERENCE, process=True), "reference")
reference, topology_audit, topology_checks = topology_split_reference(reference_raw)
if not all(topology_checks.values()):
    raise RuntimeError("Reference topology audit failed")


def solids_and_cutters():
    outer = tp._main_rolling_body().fuse(tp._top_right_clipped_cap())
    if len(outer.solids()) != 1 or not outer.is_valid:
        raise RuntimeError("Equivalent outer-body union is invalid")
    bosses = {
        name: tp._clipped_boss_solid(x, z, y0, y1)
        for name, x, z, y0, y1 in tp.BOSSES
    }
    counterbore = tp._subtract_cylindrical_bore(
        tp.MAIN_X,
        tp.MAIN_Z,
        tp.COUNTERBORE_RADIUS,
        tp.Y_COUNTERBORE_LOW,
        tp.Y_COUNTERBORE_HIGH,
    )
    through = tp._subtract_cylindrical_bore(
        tp.MAIN_X,
        tp.MAIN_Z,
        tp.THROUGH_RADIUS,
        tp.Y_COUNTERBORE_HIGH,
        tp.Y_TOP,
    )
    mount_bores = [
        tp._subtract_cylindrical_bore(
            x,
            z,
            tp.MOUNT_BORE_RADIUS,
            y0,
            y1,
        )
        for _, x, z, y0, y1 in tp.MOUNT_BORES
    ]
    engraving = tp._solid_from_sketch(
        tp._engraving_profile_sketch(),
        tp.Y_BODY_LOW,
        tp.Y_ENGRAVE_HIGH,
    )
    key = tp._anti_rotation_key_solid()
    return outer, bosses, counterbore, key, through, mount_bores, engraving


def complete_after_bosses(result, counterbore, key, through, mount_bores, engraving):
    result = result.cut(counterbore)
    result = result.fuse(key)
    result = result.cut(through)
    for bore in mount_bores:
        result = result.cut(bore)
    result = result.cut(engraving)
    if len(result.solids()) != 1 or not result.is_valid:
        raise RuntimeError("Equivalent final feature tree is invalid")
    result.label = "top_parametric"
    return result


def build_variant(name: str):
    outer, bosses, counterbore, key, through, mount_bores, engraving = solids_and_cutters()
    baseline_order = [item[0] for item in tp.BOSSES]

    if name == "baseline":
        order = baseline_order
        result = outer
        for boss_name in order:
            result = result.fuse(bosses[boss_name])
        return complete_after_bosses(result, counterbore, key, through, mount_bores, engraving)

    if name == "bottom_left_last":
        order = [baseline_order[1], baseline_order[2], baseline_order[0]]
        result = outer
        for boss_name in order:
            result = result.fuse(bosses[boss_name])
        return complete_after_bosses(result, counterbore, key, through, mount_bores, engraving)

    if name == "top_right_first_bottom_left_last":
        order = [baseline_order[2], baseline_order[1], baseline_order[0]]
        result = outer
        for boss_name in order:
            result = result.fuse(bosses[boss_name])
        return complete_after_bosses(result, counterbore, key, through, mount_bores, engraving)

    if name == "bottom_right_first":
        order = [baseline_order[1], baseline_order[0], baseline_order[2]]
        result = outer
        for boss_name in order:
            result = result.fuse(bosses[boss_name])
        return complete_after_bosses(result, counterbore, key, through, mount_bores, engraving)

    if name == "grouped_boss_union":
        boss_group = bosses[baseline_order[0]].fuse(
            bosses[baseline_order[1]],
            bosses[baseline_order[2]],
        )
        result = outer.fuse(boss_group)
        return complete_after_bosses(result, counterbore, key, through, mount_bores, engraving)

    if name == "counterbore_pre_cut_and_recut":
        result = outer.cut(counterbore)
        for boss_name in baseline_order:
            result = result.fuse(bosses[boss_name])
        return complete_after_bosses(result, counterbore, key, through, mount_bores, engraving)

    if name == "counterbore_pre_cut_bottom_left_last":
        result = outer.cut(counterbore)
        for boss_name in [baseline_order[1], baseline_order[2], baseline_order[0]]:
            result = result.fuse(bosses[boss_name])
        return complete_after_bosses(result, counterbore, key, through, mount_bores, engraving)

    if name == "all_round_cuts_pre_and_post":
        result = outer.cut(counterbore).cut(through)
        for bore in mount_bores:
            result = result.cut(bore)
        for boss_name in baseline_order:
            result = result.fuse(bosses[boss_name])
        return complete_after_bosses(result, counterbore, key, through, mount_bores, engraving)

    if name == "key_before_bosses":
        result = outer.cut(counterbore).fuse(key)
        for boss_name in baseline_order:
            result = result.fuse(bosses[boss_name])
        result = result.cut(counterbore).fuse(key).cut(through)
        for bore in mount_bores:
            result = result.cut(bore)
        result = result.cut(engraving)
        if len(result.solids()) != 1 or not result.is_valid:
            raise RuntimeError("Equivalent key-before-bosses tree is invalid")
        result.label = "top_parametric"
        return result

    if name == "clean_after_each_boolean":
        result = outer.clean()
        for boss_name in baseline_order:
            result = result.fuse(bosses[boss_name]).clean()
        result = result.cut(counterbore).clean()
        result = result.fuse(key).clean()
        result = result.cut(through).clean()
        for bore in mount_bores:
            result = result.cut(bore).clean()
        result = result.cut(engraving).clean()
        if len(result.solids()) != 1 or not result.is_valid:
            raise RuntimeError("Equivalent cleaned feature tree is invalid")
        result.label = "top_parametric"
        return result

    raise ValueError(name)


VARIANTS = (
    "baseline",
    "bottom_left_last",
    "top_right_first_bottom_left_last",
    "bottom_right_first",
    "grouped_boss_union",
    "counterbore_pre_cut_and_recut",
    "counterbore_pre_cut_bottom_left_last",
    "all_round_cuts_pre_and_post",
    "key_before_bosses",
    "clean_after_each_boolean",
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
        row = {
            "feature_tree_variant": variant,
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
    "linear_tolerance_mm": LINEAR,
    "angular_tolerance_rad": ANGULAR,
    "candidates": rows,
    "best": valid[0] if valid else None,
    "overall_pass": bool(valid and valid[0]["strict_pass"]),
}
(ROOT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("=== EQUIVALENT FEATURE-TREE SWEEP RESULT ===", flush=True)
print(json.dumps(report, indent=2), flush=True)
raise SystemExit(0 if report["overall_pass"] else 1)
