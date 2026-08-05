from __future__ import annotations

import argparse
from pathlib import Path

from build123d import Compound, Face, ShapeList, Solid

import exact_domain_patch
import exact_feature_patch
import exact_floor_patch
import exact_mount_patch
import production


class EmptyBooleanResult:
    """Lossless representation of a valid empty Boolean result."""

    def solids(self):
        return []

    def faces(self):
        return []

    def __iter__(self):
        return iter(())


EMPTY_BOOLEAN_RESULT = EmptyBooleanResult()


def _install_none_result_adapter(shape_type, operation_name: str) -> None:
    original = getattr(shape_type, operation_name)

    def adapted(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        return EMPTY_BOOLEAN_RESULT if result is None else result

    setattr(shape_type, operation_name, adapted)


def install_boolean_compatibility_adapters() -> None:
    """Normalize API return containers without modifying any B-rep geometry."""
    for shape_type in (Solid, Face):
        _install_none_result_adapter(shape_type, "intersect")
        _install_none_result_adapter(shape_type, "cut")

    if hasattr(ShapeList, "cut"):
        return

    def cut(self, other):
        pieces = []
        for shape in self:
            result = shape.cut(other)
            if result is EMPTY_BOOLEAN_RESULT:
                continue
            if isinstance(result, (list, ShapeList)):
                pieces.extend(item for item in result if item is not None)
            else:
                pieces.append(result)
        return EMPTY_BOOLEAN_RESULT if not pieces else Compound(pieces)

    ShapeList.cut = cut


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("generated"))
    args = parser.parse_args()
    install_boolean_compatibility_adapters()
    exact_feature_patch.install()
    exact_floor_patch.install()
    exact_mount_patch.install()
    exact_domain_patch.install()
    production.export_both(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
