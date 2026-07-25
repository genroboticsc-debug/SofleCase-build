from __future__ import annotations

import importlib.util
import math
import sys
import traceback
from pathlib import Path

from build123d import Edge, Face, Plane, Solid, Wire, extrude, export_step
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.Geom import Geom_BSplineCurve
from OCP.TColgp import TColgp_Array1OfPnt
from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
from OCP.gp import gp_Pnt

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "scripts" / "components" / "kailh cherry socket soldered.py"
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)
R = 0.375

spec = importlib.util.spec_from_file_location("kailh_mod", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def summary(name, shape):
    print(name, "valid=", shape.is_valid(), "solids=", len(shape.solids()), "faces=", len(shape.faces()), "edges=", len(shape.edges()), "volume=", shape.volume, "area=", shape.area)
    bb = shape.bounding_box(optimal=True)
    print(" bbox", bb.min.to_tuple(), bb.max.to_tuple())


def norm(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def pair_edge(a, b, x):
    ratio = norm(b[0], b[1]) / norm(a[2], a[3])
    values = [a[0], a[1], a[2], a[3], b[1], b[2], b[3]]
    poles = TColgp_Array1OfPnt(1, 7)
    for index, (y, z) in enumerate(values, 1):
        poles.SetValue(index, gp_Pnt(x, y, z))
    knots = TColStd_Array1OfReal(1, 3)
    mults = TColStd_Array1OfInteger(1, 3)
    for index, value in enumerate((0.0, 1.0, 1.0 + ratio), 1):
        knots.SetValue(index, value)
    for index, value in enumerate((4, 3, 4), 1):
        mults.SetValue(index, value)
    curve = Geom_BSplineCurve(poles, knots, mults, 3, False)
    if not curve.RemoveKnot(2, 2, 1.0e-9):
        raise RuntimeError("C1 knot reduction failed")
    maker = BRepBuilderAPI_MakeEdge(curve)
    if not maker.IsDone():
        raise RuntimeError("edge construction failed")
    return Edge(maker.Edge())


def make_profile_edges(x):
    spans = mod.SOLDER_PROFILE_BEZIER_SPANS_YZ
    return [pair_edge(spans[index], spans[index + 1], x) for index in range(0, 10, 2)]


def build_raw(paths):
    closure = Edge.make_line(paths[-1].end_point(), paths[0].start_point())
    wires = Wire.combine([*paths, closure], tol=mod.WIRE_JOIN_TOLERANCE_MM)
    if len(wires) != 1:
        raise RuntimeError(f"raw profile wire count {len(wires)}")
    return extrude(Face(wires[0]), 2.0, dir=(1, 0, 0))


def cutter_section(path):
    origin = path.position_at(0)
    tangent = path.tangent_at(0)
    plane = Plane(origin=origin, x_dir=(1, 0, 0), z_dir=tangent)

    def point(u, v):
        return plane.from_local_coords((u, v, 0))

    start = point(0, 0)
    setback = point(-R, 0)
    arc_mid = point(-R + R / math.sqrt(2), R - R / math.sqrt(2))
    inward = point(0, R)
    edges = [Edge.make_line(start, setback), Edge.make_three_point_arc(setback, arc_mid, inward), Edge.make_line(inward, start)]
    wires = Wire.combine(edges, tol=1.0e-7)
    if len(wires) != 1:
        raise RuntimeError("cutter section wire failed")
    return Face(wires[0])


def main():
    x_start = mod.SOLDER_X_START_MM
    start_paths = make_profile_edges(x_start)
    raw = build_raw(start_paths)
    summary("RAW", raw)
    export_step(raw, OUT / "sweep_raw.step")

    terminal_paths = [edge.translate((2.0, 0, 0)) for edge in start_paths]
    result = raw
    cutters = []
    for index, path in enumerate(terminal_paths):
        section = cutter_section(path)
        print("SECTION", index, "area", section.area, "normal", section.normal_at().to_tuple(), "path_tangent", path.tangent_at(0).to_tuple())
        try:
            cutter = Solid.sweep(section.outer_wire(), path)
        except Exception as exc:
            print("SWEEP_WIRE_FAIL", index, repr(exc))
            cutter = Solid.sweep(section, path)
        summary(f"CUTTER_{index}", cutter)
        export_step(cutter, OUT / f"cutter_{index}.step")
        cutters.append(cutter)
        result = (result - cutter).clean()
        summary(f"AFTER_CUT_{index}", result)

    summary("ROLLED_SWEEP_RESULT", result)
    export_step(result, OUT / "rolled_sweep_result.step")
    print("CUTTER_VOLUME_SUM", sum(c.volume for c in cutters))
    print("REMOVED_VOLUME", raw.volume - result.volume)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
