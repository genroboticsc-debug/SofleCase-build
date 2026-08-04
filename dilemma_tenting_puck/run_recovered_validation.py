#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
import validate_recovered_candidates as validator

def registered_load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

validator.load_module = registered_load_module
raise SystemExit(validator.main())
