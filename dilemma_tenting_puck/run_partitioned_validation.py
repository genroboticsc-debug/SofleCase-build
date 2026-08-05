#!/usr/bin/env python3
from __future__ import annotations
from build123d import Compound
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
import validate_recovered_partitioned as validator

# Validation-only disjoint planes deliberately avoid every identified native
# face station. They do not alter either B-rep and their volume coverage is
# independently checked against the full solids.
validator.X = [-106.0, -72.4, -38.8, -5.2, 35.0]
validator.Y = [-78.0, -43.7, -9.4, 25.0]
validator.Z = {
    "opening": [-8.61, -7.583, -6.556, -5.529, -4.502, -3.475, -2.448, -1.421, -0.39],
    "integrated": [-9.14, -8.265, -7.39, -6.515, -5.64, -4.765, -3.89, -3.015, -2.14, -1.265, -0.39],
}
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
