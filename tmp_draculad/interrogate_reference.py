from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run_validation as v


def pnt_tuple(p):
    return [float(p.X()), float(p.Y()), float(p.Z())]


def dir_tuple(d):
    return [float(d.X()), float(d.Y()), float(d.Z())]


def edge_inventory(edge):
    o = v.load_occ()
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    curve_names = {
        str(o["GeomAbs_CurveType"].GeomAbs_Line): "line",
        str(o["GeomAbs_CurveType"].GeomAbs_Circle): "circle",
        str(o["GeomAbs_CurveType"].GeomAbs_Ellipse): "ellipse",
        str(o["GeomAbs_CurveType"].GeomAbs_Hyperbola): "hyperbola",
        str(o["GeomAbs_CurveType"].GeomAbs_Parabola): "parabola",
        str(o["GeomAbs_CurveType"].GeomAbs_BezierCurve): "bezier",
        str(o["GeomAbs_CurveType"].GeomAbs_BSplineCurve): "bspline",
        str(o["GeomAbs_CurveType"].GeomAbs_OtherCurve): "other",
    }
    e = o["TopoDS"].Edge_s(edge)
    ad = o["BRepAdaptor_Curve"](e)
    first = float(ad.FirstParameter())
    last = float(ad.LastParameter())
    props = GProp_GProps()
    BRepGProp.LinearProperties_s(e, props)
    kind = curve_names.get(str(ad.GetType()), str(ad.GetType()))
    item = {
        "type": kind,
        "bbox": v.bbox(e),
        "length": float(props.Mass()),
        "parameter_range": [first, last],
        "start": pnt_tuple(ad.Value(first)),
        "mid": pnt_tuple(ad.Value((first + last) / 2)),
        "end": pnt_tuple(ad.Value(last)),
    }
    try:
        if kind == "line":
            line = ad.Line()
            item["line_location"] = pnt_tuple(line.Location())
            item["line_direction"] = dir_tuple(line.Direction())
        elif kind == "circle":
            c = ad.Circle()
            item["radius"] = float(c.Radius())
            item["center"] = pnt_tuple(c.Location())
            item["axis"] = dir_tuple(c.Axis().Direction())
            item["x_direction"] = dir_tuple(c.XAxis().Direction())
            item["y_direction"] = dir_tuple(c.YAxis().Direction())
        elif kind == "ellipse":
            e2 = ad.Ellipse()
            item["major_radius"] = float(e2.MajorRadius())
            item["minor_radius"] = float(e2.MinorRadius())
            item["center"] = pnt_tuple(e2.Location())
            item["axis"] = dir_tuple(e2.Axis().Direction())
            item["x_direction"] = dir_tuple(e2.XAxis().Direction())
            item["y_direction"] = dir_tuple(e2.YAxis().Direction())
        elif kind == "bezier":
            bz = ad.Bezier()
            item["degree"] = int(bz.Degree())
            item["rational"] = bool(bz.IsRational())
            item["poles"] = [pnt_tuple(bz.Pole(i)) for i in range(1, bz.NbPoles() + 1)]
            item["weights"] = [float(bz.Weight(i)) for i in range(1, bz.NbPoles() + 1)]
        elif kind == "bspline":
            bs = ad.BSpline()
            item["degree"] = int(bs.Degree())
            item["periodic"] = bool(bs.IsPeriodic())
            item["rational"] = bool(bs.IsRational())
            item["poles"] = [pnt_tuple(bs.Pole(i)) for i in range(1, bs.NbPoles() + 1)]
            item["weights"] = [float(bs.Weight(i)) for i in range(1, bs.NbPoles() + 1)]
            item["knots"] = [float(bs.Knot(i)) for i in range(1, bs.NbKnots() + 1)]
            item["multiplicities"] = [int(bs.Multiplicity(i)) for i in range(1, bs.NbKnots() + 1)]
    except Exception as exc:
        item["detail_error"] = str(exc)
    return item


def face_inventory(face, index):
    o = v.load_occ()
    f = o["TopoDS"].Face_s(face)
    ad = o["BRepAdaptor_Surface"](f, True)
    surface_names = {
        str(o["GeomAbs_SurfaceType"].GeomAbs_Plane): "plane",
        str(o["GeomAbs_SurfaceType"].GeomAbs_Cylinder): "cylinder",
        str(o["GeomAbs_SurfaceType"].GeomAbs_Cone): "cone",
        str(o["GeomAbs_SurfaceType"].GeomAbs_Sphere): "sphere",
        str(o["GeomAbs_SurfaceType"].GeomAbs_Torus): "torus",
        str(o["GeomAbs_SurfaceType"].GeomAbs_BezierSurface): "bezier_surface",
        str(o["GeomAbs_SurfaceType"].GeomAbs_BSplineSurface): "bspline_surface",
        str(o["GeomAbs_SurfaceType"].GeomAbs_SurfaceOfRevolution): "surface_of_revolution",
        str(o["GeomAbs_SurfaceType"].GeomAbs_SurfaceOfExtrusion): "surface_of_extrusion",
        str(o["GeomAbs_SurfaceType"].GeomAbs_OffsetSurface): "offset_surface",
        str(o["GeomAbs_SurfaceType"].GeomAbs_OtherSurface): "other_surface",
    }
    kind = surface_names.get(str(ad.GetType()), str(ad.GetType()))
    item = {
        "index": index,
        "type": kind,
        "area": v.area(f),
        "bbox": v.bbox(f),
        "uv_bounds": [float(ad.FirstUParameter()), float(ad.LastUParameter()),
                      float(ad.FirstVParameter()), float(ad.LastVParameter())],
        "edges": [edge_inventory(e) for e in v.explore(f, o["TopAbs_EDGE"])],
    }
    try:
        if kind == "cylinder":
            c = ad.Cylinder()
            item["radius"] = float(c.Radius())
            item["axis_location"] = pnt_tuple(c.Location())
            item["axis_direction"] = dir_tuple(c.Axis().Direction())
        elif kind == "bspline_surface":
            bs = ad.BSpline()
            item["u_degree"] = int(bs.UDegree())
            item["v_degree"] = int(bs.VDegree())
            item["u_periodic"] = bool(bs.IsUPeriodic())
            item["v_periodic"] = bool(bs.IsVPeriodic())
            item["u_rational"] = bool(bs.IsURational())
            item["v_rational"] = bool(bs.IsVRational())
            item["u_knots"] = [float(bs.UKnot(i)) for i in range(1, bs.NbUKnots() + 1)]
            item["v_knots"] = [float(bs.VKnot(i)) for i in range(1, bs.NbVKnots() + 1)]
            item["u_multiplicities"] = [int(bs.UMultiplicity(i)) for i in range(1, bs.NbUKnots() + 1)]
            item["v_multiplicities"] = [int(bs.VMultiplicity(i)) for i in range(1, bs.NbVKnots() + 1)]
            item["pole_grid"] = [
                [pnt_tuple(bs.Pole(i, j)) for j in range(1, bs.NbVPoles() + 1)]
                for i in range(1, bs.NbUPoles() + 1)
            ]
            item["weight_grid"] = [
                [float(bs.Weight(i, j)) for j in range(1, bs.NbVPoles() + 1)]
                for i in range(1, bs.NbUPoles() + 1)
            ]
    except Exception as exc:
        item["surface_detail_error"] = str(exc)
    return item


def main():
    v.WORK.mkdir(parents=True, exist_ok=True)
    v.decode_chunks("ref_xz_", v.REFERENCE)
    if v.sha256(v.REFERENCE) != v.EXPECTED_REF_SHA256:
        raise RuntimeError("Reference SHA mismatch")
    o = v.load_occ()
    shape = v.read_step(v.REFERENCE)
    solids = v.explore(shape, o["TopAbs_SOLID"])
    solids.sort(key=v.volume, reverse=True)
    housing = solids[0]
    selected = []
    for idx, face in enumerate(v.explore(housing, o["TopAbs_FACE"])):
        b = v.bbox(face)
        kind = face_inventory(face, idx)["type"]
        mouth_region = b[2] >= 2.7498 and b[5] <= 3.0502
        tiny_pocket_blend = kind == "cylinder" and abs(v.area(face) - 0.0007853981633974483) < 1e-8
        outline_region = b[0] >= -0.901 and b[3] <= 1.152 and b[1] >= 4.859 and b[4] <= 6.464
        if mouth_region or tiny_pocket_blend or outline_region:
            selected.append(face_inventory(face, idx))
    out = {
        "reference_sha256": v.sha256(v.REFERENCE),
        "housing_volume": v.volume(housing),
        "selected_face_count": len(selected),
        "selected_faces": selected,
    }
    path = ROOT / "reference_feature_interrogation.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps({"selected_face_count": len(selected), "output": str(path)}, indent=2))


if __name__ == "__main__":
    main()
