#!/usr/bin/env python3
from __future__ import annotations
from build123d import Compound
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
import validate_recovered_partitioned as validator

_original_mass = validator.mass
_common_cache = {}


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


def common_volume(first, second):
    if first is None or second is None:
        return 0.0
    key = tuple(sorted((id(first), id(second))))
    if key in _common_cache:
        return _common_cache[key]
    operation = BRepAlgoAPI_Common(first.wrapped, second.wrapped)
    operation.Build()
    if not operation.IsDone():
        raise RuntimeError("OCCT common operation failed")
    result = operation.Shape()
    if result.IsNull():
        value = 0.0
    else:
        properties = GProp_GProps()
        BRepGProp.VolumeProperties_s(result, properties)
        value = max(0.0, float(properties.Mass()))
    _common_cache[key] = value
    return value


def residual(first, second):
    if first is None:
        return 0.0
    if second is None:
        return mass(first)
    return max(0.0, mass(first) - common_volume(first, second))


validator.clipped = clipped
validator.mass = mass
validator.residual = residual
raise SystemExit(validator.main())
