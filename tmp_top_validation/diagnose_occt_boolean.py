"""Diagnose OpenCascade import and directional Boolean support for top.stl."""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

from build123d import Mesher

from top_parametric import build_top

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "reference" / "top.stl"
OUTPUT = ROOT / "generated" / "occt_boolean_diagnostic.json"


def value(obj: Any, name: str) -> Any:
    try:
        item = getattr(obj, name)
        return item() if callable(item) else item
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def shape_summary(shape: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "python_type": type(shape).__name__,
        "shape_type": str(value(shape, "shape_type")),
        "is_valid": value(shape, "is_valid"),
        "volume": value(shape, "volume"),
        "area": value(shape, "area"),
    }
    for name in ("solids", "shells", "faces", "edges", "vertices"):
        try:
            summary[f"{name}_count"] = len(getattr(shape, name)())
        except Exception as exc:
            summary[f"{name}_count"] = f"{type(exc).__name__}: {exc}"
    return summary


def total_volume(shape: Any) -> float:
    try:
        return float(abs(shape.volume))
    except Exception:
        return float(sum(abs(solid.volume) for solid in shape.solids()))


def run() -> dict[str, Any]:
    report: dict[str, Any] = {
        "reference": str(REFERENCE),
        "import_success": False,
        "boolean_success": False,
    }
    try:
        imported = Mesher().read(REFERENCE)
        report["import_count"] = len(imported)
        report["imported"] = [shape_summary(shape) for shape in imported]
        report["import_success"] = len(imported) > 0
        if not imported:
            raise RuntimeError("Mesher returned no shapes")

        reference_shape = imported[0]
        generated = build_top()
        report["generated"] = shape_summary(generated)

        generated_minus_reference = generated.cut(reference_shape)
        reference_minus_generated = reference_shape.cut(generated)
        report["generated_minus_reference"] = shape_summary(
            generated_minus_reference
        )
        report["reference_minus_generated"] = shape_summary(
            reference_minus_generated
        )
        report["generated_minus_reference_volume_mm3"] = total_volume(
            generated_minus_reference
        )
        report["reference_minus_generated_volume_mm3"] = total_volume(
            reference_minus_generated
        )
        report["symmetric_difference_volume_mm3"] = (
            report["generated_minus_reference_volume_mm3"]
            + report["reference_minus_generated_volume_mm3"]
        )
        report["boolean_success"] = True
    except Exception as exc:
        report["exception"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
