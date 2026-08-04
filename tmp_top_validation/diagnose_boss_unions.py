"""Diagnose exact F003-F005 boss union topology and regularization options.

No reference data are used.  Every tested operand is generated from the same
identified analytic parameters as the production model.  The overlap variants
extend only into material already contained in the outer body; therefore their
set union is mathematically identical to the nominal up-to-face boss union.
"""

from __future__ import annotations

import inspect
import json
import traceback
from pathlib import Path
from typing import Any, Callable

from top_parametric import (
    BOSSES,
    Y_BODY_LOW,
    Y_COUNTERBORE_HIGH,
    Y_FILLET_LOW,
    _clipped_boss_solid,
    _main_rolling_body,
    _top_right_clipped_cap,
)

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "generated" / "boss_union_diagnostic.json"


def safe_value(shape: Any, name: str) -> Any:
    try:
        value = getattr(shape, name)
        return value() if callable(value) else value
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def summary(shape: Any) -> dict[str, Any]:
    box = safe_value(shape, "bounding_box")
    result: dict[str, Any] = {
        "python_type": type(shape).__name__,
        "shape_type": str(safe_value(shape, "shape_type")),
        "is_valid": safe_value(shape, "is_valid"),
        "volume": safe_value(shape, "volume"),
        "area": safe_value(shape, "area"),
    }
    for name in ("solids", "shells", "faces", "edges", "vertices"):
        try:
            result[f"{name}_count"] = len(getattr(shape, name)())
        except Exception as exc:
            result[f"{name}_count"] = f"{type(exc).__name__}: {exc}"
    try:
        result["bounds"] = {
            "x_min": box.min.X,
            "x_max": box.max.X,
            "y_min": box.min.Y,
            "y_max": box.max.Y,
            "z_min": box.min.Z,
            "z_max": box.max.Z,
        }
    except Exception as exc:
        result["bounds"] = f"{type(exc).__name__}: {exc}"
    return result


def attempt(label: str, fn: Callable[[], Any]) -> dict[str, Any]:
    record: dict[str, Any] = {"label": label, "success": False}
    try:
        shape = fn()
        record["success"] = True
        record["shape"] = summary(shape)
    except Exception as exc:
        record["exception"] = f"{type(exc).__name__}: {exc}"
        record["traceback"] = traceback.format_exc()
    return record


def run() -> dict[str, Any]:
    main = _main_rolling_body()
    cap = _top_right_clipped_cap()
    outer = main.fuse(cap)
    bosses = [
        _clipped_boss_solid(bx, bz, y0, y1)
        for _, bx, bz, y0, y1 in BOSSES
    ]

    after_bl = outer.fuse(bosses[0])
    after_br = after_bl.fuse(bosses[1])
    top_name, top_x, top_z, top_y0, top_y1 = BOSSES[2]
    top_nominal = bosses[2]
    top_overlap_counterbore = _clipped_boss_solid(
        top_x,
        top_z,
        top_y0,
        Y_COUNTERBORE_HIGH,
    )
    top_overlap_fillet = _clipped_boss_solid(
        top_x,
        top_z,
        top_y0,
        Y_FILLET_LOW,
    )

    expected_nominal_volume = (
        float(after_br.volume) + float(top_nominal.volume)
    )

    report: dict[str, Any] = {
        "fuse_signature": str(inspect.signature(type(after_br).fuse)),
        "clean_signature": str(inspect.signature(type(after_br).clean)),
        "outer": summary(outer),
        "bosses": {
            name: summary(boss)
            for (name, *_), boss in zip(BOSSES, bosses, strict=True)
        },
        "after_F003": summary(after_bl),
        "after_F004": summary(after_br),
        "expected_nominal_F005_union_volume": expected_nominal_volume,
        "top_overlap_counterbore": summary(top_overlap_counterbore),
        "top_overlap_fillet": summary(top_overlap_fillet),
        "attempts": [],
    }

    report["attempts"].append(
        attempt("nominal_sequential_fuse", lambda: after_br.fuse(top_nominal))
    )
    report["attempts"].append(
        attempt(
            "nominal_sequential_fuse_clean",
            lambda: after_br.fuse(top_nominal).clean(),
        )
    )
    report["attempts"].append(
        attempt(
            "all_three_bosses_simultaneous",
            lambda: outer.fuse(*bosses),
        )
    )
    report["attempts"].append(
        attempt(
            "all_three_bosses_simultaneous_clean",
            lambda: outer.fuse(*bosses).clean(),
        )
    )
    report["attempts"].append(
        attempt(
            "top_boss_overlap_to_counterbore_plane",
            lambda: after_br.fuse(top_overlap_counterbore),
        )
    )
    report["attempts"].append(
        attempt(
            "top_boss_overlap_to_counterbore_plane_clean",
            lambda: after_br.fuse(top_overlap_counterbore).clean(),
        )
    )
    report["attempts"].append(
        attempt(
            "top_boss_overlap_to_fillet_spring_plane",
            lambda: after_br.fuse(top_overlap_fillet),
        )
    )
    report["attempts"].append(
        attempt(
            "top_boss_overlap_to_fillet_spring_plane_clean",
            lambda: after_br.fuse(top_overlap_fillet).clean(),
        )
    )

    for tolerance in (1.0e-9, 1.0e-8, 1.0e-7, 1.0e-6):
        report["attempts"].append(
            attempt(
                f"nominal_fuse_tol_{tolerance:.0e}",
                lambda tolerance=tolerance: after_br.fuse(
                    top_nominal,
                    tol=tolerance,
                ),
            )
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
