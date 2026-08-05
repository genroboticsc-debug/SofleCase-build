from __future__ import annotations

import argparse
from pathlib import Path

import exact_feature_patch
import production


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("generated"))
    args = parser.parse_args()
    exact_feature_patch.install()
    production.export_both(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
