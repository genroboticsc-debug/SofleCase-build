from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

from build123d import Edge, Face, Wire, extrude, export_step, fillet
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.Geom import Geom_BezierCurve
from OCP.GeomAPI import GeomAPI_ProjectPointOnCurve
from OCP.GeomConvert import GeomConvert, GeomConvert_CompCurveToBSplineCurve
from OCP.TColgp import TColgp_Array1OfPnt
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


def make_bezier(span, x):
    poles = TColgp_Array1OfPnt(1, 4)
    for i, (y, z) in enumerate(span, 1):
        poles.SetValue(i, gp_Pnt(x, y, z))
    return Geom_BezierCurve(poles)


def make_composite(beziers, with_ratio):
    bsplines = [GeomConvert.CurveToBSplineCurve_s(c) for c in beziers]
    comp = GeomConvert_CompCurveToBSplineCurve(bsplines[0])
    for c in bsplines[1:]:
        ok = comp.Add(c, 1.0e-10, True, with_ratio)
        print("ADD", with_ratio, ok)
    return comp.BSplineCurve()


def edge_from_curve(curve):
    maker = BRepBuilderAPI_MakeEdge(curve)
    if not maker.IsDone():
        raise RuntimeError("edge maker failed")
    return Edge(maker.Edge())


def projection_deviation(curve, spans, x):
    worst = 0.0
    for span in spans:
        bez = make_bezier(span, x)
        for i in range(21):
            p = bez.Value(i / 20.0)
            proj = GeomAPI_ProjectPointOnCurve(p, curve)
            if proj.NbPoints() < 1:
                raise RuntimeError("projection failed")
            worst = max(worst, proj.LowerDistance())
    return worst


def build_raw(edge):
    closure = Edge.make_line(edge.end_point(), edge.start_point())
    wires = Wire.combine([edge, closure], tol=mod.WIRE_JOIN_TOLERANCE_MM)
    if len(wires) != 1:
        raise RuntimeError(f"wire count {len(wires)}")
    return extrude(Face(wires[0]), 2.0, dir=(1, 0, 0))


def terminal_curved(raw):
    xmax = raw.bounding_box(optimal=True).max.X
    terminal = [e for e in raw.edges() if all(abs(v.X - xmax) < 1e-6 for v in e.vertices())]
    print(" terminal", [(e.geom_type.name, e.length) for e in terminal])
    return [e for e in terminal if e.geom_type.name != "LINE"]


def largest_successful_radius(raw, edge, upper=0.375):
    lo, hi = 0.0, upper
    best = None
    for _ in range(16):
        mid = (lo + hi) / 2
        try:
            candidate = fillet([edge], mid)
            best = candidate
            lo = mid
        except Exception:
            hi = mid
    return lo, best


def main():
    x = mod.SOLDER_X_START_MM
    spans = mod.SOLDER_PROFILE_BEZIER_SPANS_YZ
    original_edges = [Edge.make_bezier(*[(x, y, z) for y, z in span]) for span in spans]
    original_length = sum(e.length for e in original_edges)
    original_raw = extrude(Face(mod._solder_profile_wire(x)), 2.0, dir=(1, 0, 0))
    print("ORIGINAL_LENGTH", original_length)
    summary("ORIGINAL_RAW", original_raw)

    beziers = [make_bezier(span, x) for span in spans]
    for with_ratio in (False, True):
        tag = "ratio_true" if with_ratio else "ratio_false"
        curve = make_composite(beziers, with_ratio)
        edge = edge_from_curve(curve)
        print(tag, "degree", curve.Degree(), "poles", curve.NbPoles(), "knots", curve.NbKnots(), "length", edge.length, "length_delta", edge.length-original_length, "deviation", projection_deviation(curve, spans, x))
        raw = build_raw(edge)
        summary("RAW_"+tag, raw)
        export_step(raw, OUT / f"raw_{tag}.step")
        curved = terminal_curved(raw)
        if len(curved) != 1:
            print("CURVED_COUNT_FAIL", tag, len(curved))
            continue
        try:
            rolled = fillet(curved, 0.375)
            summary("ROLLED_"+tag, rolled)
            export_step(rolled, OUT / f"rolled_{tag}.step")
        except Exception as exc:
            print("FILLET_0375_FAIL", tag, repr(exc))
            max_r, candidate = largest_successful_radius(raw, curved[0])
            print("MAX_RADIUS", tag, max_r)
            if candidate is not None:
                export_step(candidate, OUT / f"maxfillet_{tag}.step")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
