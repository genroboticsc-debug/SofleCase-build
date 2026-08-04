"""Measure F012 using every disconnected face of the parametric text sketch."""

from __future__ import annotations

import json
from pathlib import Path
import traceback

from build123d import BuildSketch, CenterOf, add, extrude

import top_parametric as tp
from diagnose_engraving import (
    REFERENCE_AREA,
    REFERENCE_COM,
    REFERENCE_VOLUME,
    bbox_dict,
    build_through_f011,
    candidate_sketches,
    vector3,
)

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated" / "engraving_all_faces_diagnostic"
OUT.mkdir(parents=True, exist_ok=True)


def placed_face_cutters(sketch):
    with BuildSketch(tp.xz_plane(tp.Y_BODY_LOW)) as placed:
        add(sketch)
    faces = list(placed.sketch.faces())
    cutters = [
        extrude(face, amount=-(tp.Y_ENGRAVE_HIGH - tp.Y_BODY_LOW))
        for face in faces
    ]
    return placed.sketch, cutters


def inspect(name, sketch, pre_f012):
    entry = {"name": name}
    try:
        placed, cutters = placed_face_cutters(sketch)
        result = pre_f012
        glyphs = []
        total_common = 0.0
        for index, cutter in enumerate(cutters):
            common = result.intersect(cutter)
            if common is None:
                common_shapes = []
            elif hasattr(common, "volume"):
                common_shapes = [common]
            else:
                common_shapes = list(common)
            common_volume = sum(float(shape.volume) for shape in common_shapes)
            before = float(result.volume)
            result = result.cut(cutter)
            after = float(result.volume)
            removed = before - after
            total_common += common_volume
            glyphs.append(
                {
                    "index": index,
                    "cutter_volume_mm3": float(cutter.volume),
                    "cutter_area_mm2": float(cutter.area),
                    "cutter_bbox_global": bbox_dict(cutter),
                    "common_volume_mm3": common_volume,
                    "removed_volume_mm3": removed,
                }
            )

        if len(result.solids()) != 1 or not result.is_valid:
            raise RuntimeError("All-face F012 result is not one valid solid")

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
                "source_sketch_face_count": len(sketch.faces()),
                "placed_sketch_face_count": len(placed.faces()),
                "source_sketch_bbox_local": bbox_dict(sketch),
                "placed_sketch_bbox_global": bbox_dict(placed),
                "glyphs": glyphs,
                "total_cutter_volume_mm3": sum(
                    glyph["cutter_volume_mm3"] for glyph in glyphs
                ),
                "total_common_volume_mm3": total_common,
                "result": {
                    "valid": bool(result.is_valid),
                    "solid_count": len(result.solids()),
                    "volume_mm3": final_volume,
                    "area_mm2": final_area,
                    "com_mm": final_com,
                    "bbox_global": bbox_dict(result),
                    "removed_volume_mm3": removed_volume,
                    "area_change_mm2": area_change,
                    "target_removed_volume_mm3": pre_volume - REFERENCE_VOLUME,
                    "target_area_change_mm2": REFERENCE_AREA - pre_area,
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
    candidates = []
    for name, sketch in candidate_sketches().items():
        entry = inspect(name, sketch, pre_f012)
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
        "pre_f012": {
            "volume_mm3": float(pre_f012.volume),
            "area_mm2": float(pre_f012.area),
            "com_mm": vector3(pre_f012.center(CenterOf.MASS)),
        },
        "candidates": candidates,
        "best_metric_candidate": successful[0]["name"] if successful else None,
    }
    (OUT / "report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
