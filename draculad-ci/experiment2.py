from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

from build123d import Edge, Face, Wire, extrude, export_step, fillet
from OCP.BRep import BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.Geom import Geom_TrimmedCurve
from OCP.GeomConvert import GeomConvert, GeomConvert_CompCurveToBSplineCurve

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


def curve_from_edge(edge: Edge):
    curve, first, last = BRep_Tool.Curve_s(edge.wrapped)
    trimmed = Geom_TrimmedCurve(curve, first, last)
    if not edge.is_forward:
        trimmed.Reverse()
    return trimmed


def to_bspline(curve):
    for name in ("CurveToBSplineCurve_s", "CurveToBSplineCurve"):
        fn = getattr(GeomConvert, name, None)
        if fn is not None:
            try:
                return fn(curve)
            except Exception as exc:
                print("CONVERT_VARIANT_FAIL", name, repr(exc))
    raise RuntimeError("No GeomConvert CurveToBSplineCurve overload succeeded")


def add_curve(comp, curve, after=True):
    attempts = [(curve, 1.0e-9, after, False), (curve, 1.0e-8, after, False), (curve, 1.0e-7, after, False), (curve, 1.0e-7, after), (curve, 1.0e-7), (curve,)]
    last_exc = None
    for args in attempts:
        try:
            result = comp.Add(*args)
            print("ADD_OK", len(args), args[1:] if len(args) > 1 else (), result)
            return result
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(f"All Add overloads failed: {last_exc!r}")


def exact_composite_edge(edges: list[Edge]) -> Edge:
    bsplines = [to_bspline(curve_from_edge(edge)) for edge in edges]
    print("BSPLINE_COUNT", len(bsplines))
    comp = None
    ctor_errors = []
    for args in ((bsplines[0],), (bsplines[0], 1.0e-9), ()):
        try:
            comp = GeomConvert_CompCurveToBSplineCurve(*args)
            print("COMP_CTOR_OK", len(args))
            if not args:
                add_curve(comp, bsplines[0], True)
            break
        except Exception as exc:
            ctor_errors.append((args, repr(exc)))
    if comp is None:
        raise RuntimeError(f"No composite constructor succeeded: {ctor_errors}")
    for curve in bsplines[1:]:
        add_curve(comp, curve, True)
    result_curve = comp.BSplineCurve()
    print("COMPOSITE_CURVE", "degree", result_curve.Degree(), "poles", result_curve.NbPoles(), "knots", result_curve.NbKnots(), "rational", result_curve.IsRational())
    maker = BRepBuilderAPI_MakeEdge(result_curve)
    if not maker.IsDone():
        raise RuntimeError("BRepBuilderAPI_MakeEdge did not complete")
    return Edge(maker.Edge())


def main():
    x = mod.SOLDER_X_START_MM
    spans = mod.SOLDER_PROFILE_BEZIER_SPANS_YZ
    span_edges = [Edge.make_bezier(*[(x, y, z) for y, z in span]) for span in spans]
    print("SPAN_LENGTH_SUM", sum(e.length for e in span_edges))
    print("SPAN_ENDPOINTS", span_edges[0].start_point().to_tuple(), span_edges[-1].end_point().to_tuple())
    composite = exact_composite_edge(span_edges)
    print("COMPOSITE_LENGTH", composite.length, "geom", composite.geom_type)
    print("COMPOSITE_ENDPOINTS", composite.start_point().to_tuple(), composite.end_point().to_tuple())
    print("LENGTH_DELTA", composite.length - sum(e.length for e in span_edges))

    closure = Edge.make_line(composite.end_point(), composite.start_point())
    wires = Wire.combine([composite, closure], tol=mod.WIRE_JOIN_TOLERANCE_MM)
    print("WIRE_COMBINE_COUNT", len(wires))
    if len(wires) != 1:
        raise RuntimeError("Composite profile did not make one wire")
    profile = Face(wires[0])
    raw = extrude(profile, 2.0, dir=(1, 0, 0))
    summary("RAW_COMPOSITE", raw)
    export_step(raw, OUT / "raw_composite.step")

    xmax = raw.bounding_box(optimal=True).max.X
    terminal = [edge for edge in raw.edges() if all(abs(v.X - xmax) < 1e-6 for v in edge.vertices())]
    print("TERMINAL_COUNT", len(terminal))
    for index, edge in enumerate(terminal):
        print("TERMINAL", index, "type", edge.geom_type, "length", edge.length, "start", edge.start_point().to_tuple(), "end", edge.end_point().to_tuple())

    curved = [e for e in terminal if e.geom_type.name != "LINE"]
    print("CURVED_TERMINAL_COUNT", len(curved))
    if len(curved) != 1:
        raise RuntimeError(f"Expected one curved terminal edge, got {len(curved)}")
    rolled = fillet(curved, 0.375)
    summary("ROLLED_R0375", rolled)
    export_step(rolled, OUT / "rolled_r0375.step")

    bb = rolled.bounding_box(optimal=True)
    for index, edge in enumerate(rolled.edges()):
        ebb = edge.bounding_box(optimal=True)
        if ebb.max.X > bb.max.X - 0.7:
            print("POST_EDGE", index, "type", edge.geom_type, "length", edge.length, "bbox", ebb.min.to_tuple(), ebb.max.to_tuple(), "vertices", [v.to_tuple() for v in edge.vertices()])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
