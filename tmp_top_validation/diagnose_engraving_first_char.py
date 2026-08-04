"""Validate whether the recovered first engraving character is lowercase v.

With MAX/MAX text alignment, changing only the first glyph leaves the recovered
positions of the trailing "4_17" glyphs unchanged.  The reference first floor
component is 2.873 mm tall, while Arial uppercase V is 3.952 mm tall; this
diagnostic measures uppercase and lowercase candidates through the full F012
five-face cut.
"""

from __future__ import annotations

import json
from pathlib import Path

import top_parametric as tp
from diagnose_engraving import build_through_f011
from diagnose_engraving_all_faces import inspect

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated" / "engraving_first_char_diagnostic"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    pre_f012 = build_through_f011()
    original_text = tp.ENGRAVING_TEXT
    candidates = []
    try:
        for text in ("V4_17", "v4_17"):
            tp.ENGRAVING_TEXT = text
            sketch = tp._engraving_profile_sketch()
            entry = inspect(text, sketch, pre_f012)
            entry["engraving_text"] = text
            candidates.append(entry)
            print(json.dumps(entry, indent=2), flush=True)
    finally:
        tp.ENGRAVING_TEXT = original_text

    successful = [entry for entry in candidates if entry.get("success")]
    successful.sort(
        key=lambda entry: (
            entry["result"]["volume_difference_percent"]
            + entry["result"]["area_difference_percent"],
            entry["engraving_text"],
        )
    )
    report = {
        "fixed_parameters": {
            "font": tp.ENGRAVING_FONT,
            "font_size_mm": tp.ENGRAVING_FONT_SIZE,
            "rotation_degrees": tp.ENGRAVING_ROTATION_DEG,
            "u_max": tp.ENGRAVING_U_MAX,
            "v_max": tp.ENGRAVING_V_MAX,
            "depth_mm": tp.ENGRAVING_DEPTH,
        },
        "candidates": candidates,
        "best_metric_candidate": (
            successful[0]["engraving_text"] if successful else None
        ),
    }
    (OUT / "report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
