#!/usr/bin/env python3
from __future__ import annotations
from build123d import Compound
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
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


def direct_cut_volume(first, second):
    if first is None:
        return 0.0
    if second is None:
        return mass(first)
    operation = BRepAlgoAPI_Cut(first.wrapped, second.wrapped)
    operation.SetNonDestructive(True)
    operation.SetRunParallel(True)
    operation.Build()
    if not operation.IsDone():
        raise RuntimeError("OCCT directional cut failed")
    result = operation.Shape()
    if result.IsNull():
        return 0.0
    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(result, properties)
    return max(0.0, float(properties.Mass()))


validator.clipped = clipped
validator.mass = mass
validator.residual = direct_cut_volume
raise SystemExit(validator.main())
