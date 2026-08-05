from __future__ import annotations

import argparse
from pathlib import Path

from build123d import Compound, ShapeList

import exact_feature_patch
import production


def install_shapelist_boolean_adapter() -> None:
    if hasattr(ShapeList, "cut"):
        return

    def cut(self, other):
        pieces = []
        for shape in self:
            result = shape.cut(other)
            if isinstance(result, (list, ShapeList)):
                pieces.extend(result)
            else:
                pieces.append(result)
        return Compound(pieces)

    ShapeList.cut = cut


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("generated"))
    args = parser.parse_args()
    install_shapelist_boolean_adapter()
    exact_feature_patch.install()
    production.export_both(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
