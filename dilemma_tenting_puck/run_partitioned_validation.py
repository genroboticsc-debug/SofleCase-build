#!/usr/bin/env python3
from __future__ import annotations
from build123d import Compound
import validate_recovered_partitioned as validator

_original_mass = validator.mass


def normalized(shape):
    if shape is None:
        return None
    if hasattr(shape, "wrapped"):
        return shape
    solids = list(shape.solids())
    if not solids:
        return None
    return solids[0] if len(solids) == 1 else Compound(solids)


def clipped(shape, cell):
    return normalized(shape.intersect(cell))


def mass(shape, kind="volume"):
    item = normalized(shape)
    return 0.0 if item is None else _original_mass(item, kind)


validator.clipped = clipped
validator.mass = mass
raise SystemExit(validator.main())
