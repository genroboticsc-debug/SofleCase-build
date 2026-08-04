"""Diagnose exact F012 engraving transform and pocket intersection.

The recovered engraving parameters are fixed: Arial Regular, 5 mm, text
"V4_17", +25 degrees, 1 mm depth, and recovered local U/V maximum values.
This diagnostic tests only mathematically distinct transform interpretations and
reports the actual intersected/cut volume and surface-area change.
"""

from __future__ import annotations

import json
from pathlib import Path
import traceback

from build123d import (
    Align,
    BuildSketch,
    CenterOf,
    FontStyle,
    Pos,
    Rot,
    Text,
)

import top_parametric as tp

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated" / "engraving_diagnostic"
OUT.mkdir(parents=True, exist_ok=True)

REFERENCE_VOLUME = 4622.072612271143
REFERENCE_AREA = 4058.7410863611594
REFERENCE_COM = (-2.7213288925039287, 64.09078103920702, -10.47228359068181)


def vector3(value):
    return [float(value.X), float(value.Y), float(value.Z)]


def bbox_dict(shape):
    box = shape.bounding_box()
    return {
        "min": [float(box.min.X), float(box.min.Y), float(box.min.Z)],
        "max": [float(box.max.X), float(box.max.Y), float(box.max.Z)],
        "size": [float(box.size.X), float(box.size.Y), float(box.size.Z)],
    }


def raw_text_sketch():
    with BuildSketch() as raw_text:
        Text(
            tp.ENGRAVING_TEXT,
            tp.ENGRAVING_FONT_SIZE,
            font=tp.ENGRAVING_FONT,
            font_style=FontStyle.REGULAR,
            align=(Align.MAX, Align.MAX),
        )
    return raw_text.sketch


def candidate_sketches():
    raw = raw_text_sketch()
    rotation = Rot(0.0, 0.0, tp.ENGRAVING_ROTATION_DEG)
    translation = Pos(tp.ENGRAVING_U_MAX, tp.ENGRAVING_V_MAX, 0.0)
    rotated = rotation * raw
    rotated_box = rotated.bounding_box()

    # The names U_MAX/V_MAX indicate the recovered maximum corner of the
    # rotated engraving.  Anchor it exactly by translating its current max.
    max_anchor_delta = Pos(
        tp.ENGRAVING_U_MAX - rotated_box.max.X,
        tp.ENGRAVING_V_MAX - rotated_box.max.Y,
        0.0,
    )

    # Included as a diagnostic contrast only: anchor the rotated minimum to the
    # same recovered coordinate. It should not match a MAX-labelled datum.
    min_anchor_delta = Pos(
        tp.ENGRAVING_U_MAX - rotated_box.min.X,
        tp.ENGRAVING_V_MAX - rotated_box.min.Y,
        0.0,
    )

    return {
        "current_rotate_after_translate": rotation * (translation * raw),
        "translate_after_rotate": translation * rotated,
        "rotated_bbox_max_anchor": max_anchor_delta * rotated,
        "rotated_bbox_min_anchor_contrast": min_anchor_delta * rotated,
    }


def build_through_f011():
    main_rolling_body = tp._main_rolling_body()
    top_right_clipped_cap = tp._top_right_clipped_cap()
    result = main_rolling_body.fuse(top_right_clipped_cap)
    if len(result.solids()) != 1 or not result.is_valid:
        raise RuntimeError("F001-F002 union invalid")

    bosses = [
        tp._clipped_boss_solid(bx, bz, y0, y1)
        for _, bx, bz, y0, y1 in tp.BOSSES
    ]
    result = result.fuse(bosses[0])
    result = result.fuse(bosses[1])
    result = result.fuse(bosses[2], tol=1.0e-6)

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
    for _, bx, bz, y0, y1 in tp.MOUNT_BORES:
        result = result.cut(
            tp._subtract_cylindrical_bore(
                bx,
                bz,
                tp.MOUNT_BORE_RADIUS,
                y0,
                y1,
            )
        )
    if len(result.solids()) != 1 or not result.is_valid:
        raise RuntimeError("F001-F011 result invalid")
    return result


def inspect_candidate(name, sketch, pre_f012):
    entry = {"name": name}
    try:
        cutter = tp._solid_from_sketch(
            sketch,
            tp.Y_BODY_LOW,
            tp.Y_ENGRAVE_HIGH,
        )
        common = pre_f012.intersect(cutter)
        result = pre_f012.cut(cutter)
        if len(result.solids()) != 1 or not result.is_valid:
            raise RuntimeError("F012 result is not one valid solid")

        pre_volume = float(pre_f012.volume)
        pre_area = float(pre_f012.area)
        final_volume = float(result.volume)
        final_area = float(result.area)
        removed_volume = pre_volume - final_volume
        area_change = final_area - pre_area
        final_com = vector3(result.center(CenterOf.MASS))

        entry.update(
            {
                "success": True,
                "sketch_face_count": len(sketch.faces()),
                "sketch_bbox_local": bbox_dict(sketch),
                "cutter": {
                    "valid": bool(cutter.is_valid),
                    "solid_count": len(cutter.solids()),
                    "volume_mm3": float(cutter.volume),
                    "area_mm2": float(cutter.area),
                    "bbox_global": bbox_dict(cutter),
                },
                "common": {
                    "valid": bool(common.is_valid),
                    "solid_count": len(common.solids()),
                    "volume_mm3": float(common.volume),
                    "area_mm2": float(common.area),
                    "bbox_global": bbox_dict(common) if common.solids() else None,
                },
                "result": {
                    "valid": bool(result.is_valid),
                    "solid_count": len(result.solids()),
                    "volume_mm3": final_volume,
                    "area_mm2": final_area,
                    "com_mm": final_com,
                    "bbox_global": bbox_dict(result),
                    "removed_volume_mm3": removed_volume,
                    "area_change_mm2": area_change,
                    "volume_difference_mm3": final_volume - REFERENCE_VOLUME,
                    "volume_difference_percent": abs(final_volume - REFERENCE_VOLUME) / REFERENCE_VOLUME * 100.0,
                    "area_difference_mm2": final_area - REFERENCE_AREA,
                    "area_difference_percent": abs(final_area - REFERENCE_AREA) / REFERENCE_AREA * 100.0,
                    "com_delta_mm": [final_com[i] - REFERENCE_COM[i] for i in range(3)],
                },
            }
        )
    except Exception as exc:
        entry.update(
            {
                "success": False,
                "exception": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        )
    return entry


def main() -> int:
    pre_f012 = build_through_f011()
    pre = {
        "valid": bool(pre_f012.is_valid),
        "solid_count": len(pre_f012.solids()),
        "volume_mm3": float(pre_f012.volume),
        "area_mm2": float(pre_f012.area),
        "com_mm": vector3(pre_f012.center(CenterOf.MASS)),
        "bbox_global": bbox_dict(pre_f012),
        "target_removed_volume_mm3": float(pre_f012.volume) - REFERENCE_VOLUME,
        "target_area_change_mm2": REFERENCE_AREA - float(pre_f012.area),
    }
    print(json.dumps({"pre_f012": pre}, indent=2), flush=True)

    candidates = []
    for name, sketch in candidate_sketches().items():
        entry = inspect_candidate(name, sketch, pre_f012)
        candidates.append(entry)
        print(json.dumps(entry, indent=2), flush=True)

    successful = [entry for entry in candidates if entry.get("success")]
    if successful:
        successful.sort(
            key=lambda entry: (
                entry["result"]["volume_difference_percent"]
                + entry["result"]["area_difference_percent"],
                entry["name"],
            )
        )
        best = successful[0]["name"]
    else:
        best = None

    report = {
        "reference": {
            "volume_mm3": REFERENCE_VOLUME,
            "area_mm2": REFERENCE_AREA,
            "com_mm": list(REFERENCE_COM),
        },
        "recovered_engraving": {
            "text": tp.ENGRAVING_TEXT,
            "font": tp.ENGRAVING_FONT,
            "font_size_mm": tp.ENGRAVING_FONT_SIZE,
            "rotation_degrees": tp.ENGRAVING_ROTATION_DEG,
            "u_max": tp.ENGRAVING_U_MAX,
            "v_max": tp.ENGRAVING_V_MAX,
            "depth_mm": tp.ENGRAVING_DEPTH,
        },
        "pre_f012": pre,
        "candidates": candidates,
        "best_metric_candidate": best,
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
