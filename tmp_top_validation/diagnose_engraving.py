"""Diagnose exact F012 engraving transform and pocket intersection."""

from __future__ import annotations

import json
from pathlib import Path
import traceback

from build123d import Align, BuildSketch, CenterOf, FontStyle, Pos, Rot, Text

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


def shape_sequence(value):
    """Normalize Build123d Shape, ShapeList, or None to a plain list."""
    if value is None:
        return []
    if hasattr(value, "volume") and hasattr(value, "bounding_box"):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def aggregate_stats(value):
    shapes = shape_sequence(value)
    if not shapes:
        return {
            "valid": True,
            "shape_count": 0,
            "solid_count": 0,
            "volume_mm3": 0.0,
            "area_mm2": 0.0,
            "bbox_global": None,
        }

    solids = []
    for shape in shapes:
        try:
            solids.extend(shape.solids())
        except Exception:
            pass

    boxes = [shape.bounding_box() for shape in shapes]
    minimum = [
        min(float(getattr(box.min, axis)) for box in boxes)
        for axis in ("X", "Y", "Z")
    ]
    maximum = [
        max(float(getattr(box.max, axis)) for box in boxes)
        for axis in ("X", "Y", "Z")
    ]
    return {
        "valid": all(bool(shape.is_valid) for shape in shapes),
        "shape_count": len(shapes),
        "solid_count": len(solids),
        "volume_mm3": sum(float(shape.volume) for shape in shapes),
        "area_mm2": sum(float(shape.area) for shape in shapes),
        "bbox_global": {
            "min": minimum,
            "max": maximum,
            "size": [maximum[i] - minimum[i] for i in range(3)],
        },
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

    max_anchor_delta = Pos(
        tp.ENGRAVING_U_MAX - rotated_box.max.X,
        tp.ENGRAVING_V_MAX - rotated_box.max.Y,
        0.0,
    )
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
    result = tp._main_rolling_body().fuse(tp._top_right_clipped_cap())
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
        final_com = vector3(result.center(CenterOf.MASS))
        removed_volume = pre_volume - final_volume
        area_change = final_area - pre_area

        entry.update(
            {
                "success": True,
                "sketch_face_count": len(sketch.faces()),
                "sketch_bbox_local": bbox_dict(sketch),
                "cutter": aggregate_stats(cutter),
                "common": aggregate_stats(common),
                "result": {
                    "valid": bool(result.is_valid),
                    "solid_count": len(result.solids()),
                    "volume_mm3": final_volume,
                    "area_mm2": final_area,
                    "com_mm": final_com,
                    "bbox_global": bbox_dict(result),
                    "removed_volume_mm3": removed_volume,
                    "area_change_mm2": area_change,
                    "removed_minus_target_mm3": (
                        removed_volume - (pre_volume - REFERENCE_VOLUME)
                    ),
                    "area_change_minus_target_mm2": (
                        area_change - (REFERENCE_AREA - pre_area)
                    ),
                    "volume_difference_mm3": final_volume - REFERENCE_VOLUME,
                    "volume_difference_percent": (
                        abs(final_volume - REFERENCE_VOLUME)
                        / REFERENCE_VOLUME
                        * 100.0
                    ),
                    "area_difference_mm2": final_area - REFERENCE_AREA,
                    "area_difference_percent": (
                        abs(final_area - REFERENCE_AREA)
                        / REFERENCE_AREA
                        * 100.0
                    ),
                    "com_delta_mm": [
                        final_com[i] - REFERENCE_COM[i] for i in range(3)
                    ],
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
    pre_volume = float(pre_f012.volume)
    pre_area = float(pre_f012.area)
    pre = {
        "valid": bool(pre_f012.is_valid),
        "solid_count": len(pre_f012.solids()),
        "volume_mm3": pre_volume,
        "area_mm2": pre_area,
        "com_mm": vector3(pre_f012.center(CenterOf.MASS)),
        "bbox_global": bbox_dict(pre_f012),
        "target_removed_volume_mm3": pre_volume - REFERENCE_VOLUME,
        "target_area_change_mm2": REFERENCE_AREA - pre_area,
    }
    print(json.dumps({"pre_f012": pre}, indent=2), flush=True)

    candidates = []
    for name, sketch in candidate_sketches().items():
        entry = inspect_candidate(name, sketch, pre_f012)
        candidates.append(entry)
        print(json.dumps(entry, indent=2), flush=True)

    successful = [entry for entry in candidates if entry.get("success")]
    successful.sort(
        key=lambda entry: (
            entry["result"]["volume_difference_percent"]
            + entry["result"]["area_difference_percent"],
            entry["name"],
        )
    )

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
        "best_metric_candidate": successful[0]["name"] if successful else None,
    }
    (OUT / "report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
