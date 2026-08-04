"""Validate the scalar F012 Arial size recovered from reference glyph bounds.

Four unclipped reference glyphs have identical X/Z bounding-box scale ratios
relative to the 5 mm Build123d Arial outlines.  Their mean scale is
0.9778993842512901 about the unchanged transformed MAX/MAX anchor, identifying
an exact candidate size of 4.88949692125645 mm.  Nearby decimal-rounding
representations are tested to select a stable source parameter.
"""

from __future__ import annotations

import json
from pathlib import Path

import top_parametric as tp
from diagnose_engraving import REFERENCE_AREA, REFERENCE_COM, REFERENCE_VOLUME, build_through_f011
from diagnose_engraving_all_faces import inspect

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated" / "engraving_size_diagnostic"
OUT.mkdir(parents=True, exist_ok=True)

RECOVERED_SCALE = 0.9778993842512901
RECOVERED_SIZE = 5.0 * RECOVERED_SCALE


def main() -> int:
    pre_f012 = build_through_f011()
    original_size = tp.ENGRAVING_FONT_SIZE
    sizes = (
        4.88949000,
        4.88949692,
        RECOVERED_SIZE,
        4.88950000,
        4.88951000,
    )
    candidates = []
    try:
        for size in sizes:
            tp.ENGRAVING_FONT_SIZE = float(size)
            sketch = tp._engraving_profile_sketch()
            entry = inspect(f"font_size_{size:.11f}", sketch, pre_f012)
            entry["font_size_mm"] = float(size)
            candidates.append(entry)
            print(json.dumps(entry, indent=2), flush=True)
    finally:
        tp.ENGRAVING_FONT_SIZE = original_size

    successful = [entry for entry in candidates if entry.get("success")]
    successful.sort(
        key=lambda entry: (
            entry["result"]["volume_difference_percent"]
            + entry["result"]["area_difference_percent"],
            abs(entry["font_size_mm"] - RECOVERED_SIZE),
        )
    )
    report = {
        "derivation": {
            "source_size_mm": 5.0,
            "unclipped_glyph_bbox_scale_mean": RECOVERED_SCALE,
            "recovered_size_mm": RECOVERED_SIZE,
            "rotation_degrees": tp.ENGRAVING_ROTATION_DEG,
            "u_max": tp.ENGRAVING_U_MAX,
            "v_max": tp.ENGRAVING_V_MAX,
            "reference_volume_mm3": REFERENCE_VOLUME,
            "reference_area_mm2": REFERENCE_AREA,
            "reference_com_mm": list(REFERENCE_COM),
        },
        "candidates": candidates,
        "best_metric_candidate": successful[0]["name"] if successful else None,
        "best_font_size_mm": successful[0]["font_size_mm"] if successful else None,
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
