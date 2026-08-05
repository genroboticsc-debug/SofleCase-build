from __future__ import annotations

import importlib.util
import math
import sys
import traceback
from pathlib import Path

from build123d import Edge, Face, Wire, extrude, export_step, fillet
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.Geom import Geom_BSplineCurve
from OCP.TColgp import TColgp_Array1OfPnt
from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
from OCP.gp import gp_Pnt

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "scripts" / "components" / "kailh cherry socket soldered.py"
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)

spec = importlib.util.spec_from_file_location("kailh_mod", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def summary(name, shape):
    print(name, "valid=", shape.is_valid(), "solids=", len(shape.solids()), "faces=", len(shape.faces()), "edges=", len(shape.edges()), "volume=", shape.volume, "area=", shape.area)
    bb = shape.bounding_box(optimal=True)
    print(" bbox", bb.min.to_tuple(), bb.max.to_tuple())


def tangent_norm(a, b):
    return math.hypot(b[0]-a[0], b[1]-a[1])


def exact_piecewise_bspline(spans, x, reduce_to_c1):
    intervals = [1.0]
    for i in range(len(spans)-1):
        left = tangent_norm(spans[i][2], spans[i][3])
        right = tangent_norm(spans[i+1][0], spans[i+1][1])
        intervals.append(intervals[-1] * right / left)
    knots_values = [0.0]
    for h in intervals:
        knots_values.append(knots_values[-1] + h)
    print("INTERVALS", intervals)
    print("KNOT_VALUES", knots_values)

    pole_values = [spans[0][0], spans[0][1], spans[0][2], spans[0][3]]
    for span in spans[1:]:
        pole_values.extend([span[1], span[2], span[3]])
    poles = TColgp_Array1OfPnt(1, len(pole_values))
    for i, (y, z) in enumerate(pole_values, 1):
        poles.SetValue(i, gp_Pnt(x, y, z))

    knots = TColStd_Array1OfReal(1, len(knots_values))
    mults = TColStd_Array1OfInteger(1, len(knots_values))
    for i, value in enumerate(knots_values, 1):
        knots.SetValue(i, value)
        mults.SetValue(i, 4 if i in (1, len(knots_values)) else 3)

    curve = Geom_BSplineCurve(poles, knots, mults, 3, False)
    print("INITIAL", "poles", curve.NbPoles(), "knots", curve.NbKnots(), "continuity", curve.Continuity())
    if reduce_to_c1:
        for index in range(2, curve.NbKnots()):
            before = curve.Multiplicity(index)
            ok = curve.RemoveKnot(index, 2, 1.0e-9)
            print("REMOVE_KNOT", index, "before", before, "ok", ok, "after", curve.Multiplicity(index))
        print("REDUCED", "poles", curve.NbPoles(), "knots", curve.NbKnots(), "continuity", curve.Continuity())
    return curve


def edge_from_curve(curve):
    maker = BRepBuilderAPI_MakeEdge(curve)
    if not maker.IsDone():
        raise RuntimeError("edge maker failed")
    return Edge(maker.Edge())


def build_raw(edge):
    closure = Edge.make_line(edge.end_point(), edge.start_point())
    wires = Wire.combine([edge, closure], tol=mod.WIRE_JOIN_TOLERANCE_MM)
    if len(wires) != 1:
        raise RuntimeError(f"wire count {len(wires)}")
    return extrude(Face(wires[0]), 2.0, dir=(1, 0, 0))


def terminal_curved(raw):
    xmax = raw.bounding_box(optimal=True).max.X
    terminal = [e for e in raw.edges() if all(abs(v.X-xmax) < 1e-6 for v in e.vertices())]
    print("TERMINAL", [(e.geom_type.name, e.length) for e in terminal])
    return [e for e in terminal if e.geom_type.name != "LINE"]


def max_radius(raw, edge, upper=0.375):
    lo, hi = 0.0, upper
    best = None
    for _ in range(18):
        mid = (lo+hi)/2
        try:
            best = fillet([edge], mid)
            lo = mid
        except Exception:
            hi = mid
    return lo, best


def main():
    x = mod.SOLDER_X_START_MM
    spans = mod.SOLDER_PROFILE_BEZIER_SPANS_YZ
    original_raw = extrude(Face(mod._solder_profile_wire(x)), 2.0, dir=(1,0,0))
    summary("ORIGINAL_RAW", original_raw)

    for reduce_to_c1 in (False, True):
        tag = "c1" if reduce_to_c1 else "c0"
        curve = exact_piecewise_bspline(spans, x, reduce_to_c1)
        edge = edge_from_curve(curve)
        print(tag, "edge_length", edge.length, "start", edge.start_point().to_tuple(), "end", edge.end_point().to_tuple())
        raw = build_raw(edge)
        summary("RAW_"+tag, raw)
        export_step(raw, OUT / f"raw_exact_{tag}.step")
        curved = terminal_curved(raw)
        if len(curved) != 1:
            print("CURVED_COUNT_FAIL", len(curved)); continue
        try:
            rolled = fillet(curved, 0.375)
            summary("ROLLED_"+tag, rolled)
            export_step(rolled, OUT / f"rolled_exact_{tag}.step")
        except Exception as exc:
            print("FILLET_FAIL", tag, repr(exc))
            r, best = max_radius(raw, curved[0])
            print("MAX_RADIUS", tag, r)
            if best is not None and r > 0.01:
                export_step(best, OUT / f"maxfillet_exact_{tag}.step")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
