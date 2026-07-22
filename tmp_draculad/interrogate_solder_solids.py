from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run_validation as v


def point_tuple(point):
    return [float(point.X()), float(point.Y()), float(point.Z())]


def direction_tuple(direction):
    return [float(direction.X()), float(direction.Y()), float(direction.Z())]


def edge_detail(edge):
    o = v.load_occ()
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    names = {
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
    adaptor = o["BRepAdaptor_Curve"](e)
    first = float(adaptor.FirstParameter())
    last = float(adaptor.LastParameter())
    props = GProp_GProps()
    BRepGProp.LinearProperties_s(e, props)
    kind = names.get(str(adaptor.GetType()), str(adaptor.GetType()))
    item = {
        "type": kind,
        "length": float(props.Mass()),
        "parameter_range": [first, last],
        "start": point_tuple(adaptor.Value(first)),
        "mid": point_tuple(adaptor.Value((first + last) / 2.0)),
        "end": point_tuple(adaptor.Value(last)),
        "bbox": v.bbox(e),
    }
    try:
        if kind == "line":
            line = adaptor.Line()
            item["location"] = point_tuple(line.Location())
            item["direction"] = direction_tuple(line.Direction())
        elif kind == "circle":
            circle = adaptor.Circle()
            item["radius"] = float(circle.Radius())
            item["center"] = point_tuple(circle.Location())
            item["axis"] = direction_tuple(circle.Axis().Direction())
        elif kind == "ellipse":
            ellipse = adaptor.Ellipse()
            item["major_radius"] = float(ellipse.MajorRadius())
            item["minor_radius"] = float(ellipse.MinorRadius())
            item["center"] = point_tuple(ellipse.Location())
            item["axis"] = direction_tuple(ellipse.Axis().Direction())
        elif kind == "bezier":
            curve = adaptor.Bezier()
            item["degree"] = int(curve.Degree())
            item["pole_count"] = int(curve.NbPoles())
            item["rational"] = bool(curve.IsRational())
        elif kind == "bspline":
            curve = adaptor.BSpline()
            item["degree"] = int(curve.Degree())
            item["pole_count"] = int(curve.NbPoles())
            item["knot_count"] = int(curve.NbKnots())
            item["periodic"] = bool(curve.IsPeriodic())
            item["rational"] = bool(curve.IsRational())
    except Exception as exc:
        item["detail_error"] = str(exc)
    return item


def face_detail(face, index):
    o = v.load_occ()
    names = {
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
    f = o["TopoDS"].Face_s(face)
    adaptor = o["BRepAdaptor_Surface"](f, True)
    kind = names.get(str(adaptor.GetType()), str(adaptor.GetType()))
    item = {
        "index": index,
        "type": kind,
        "area": v.area(f),
        "bbox": v.bbox(f),
        "uv_bounds": [
            float(adaptor.FirstUParameter()),
            float(adaptor.LastUParameter()),
            float(adaptor.FirstVParameter()),
            float(adaptor.LastVParameter()),
        ],
        "edges": [edge_detail(edge) for edge in v.explore(f, o["TopAbs_EDGE"])],
    }
    try:
        if kind == "plane":
            plane = adaptor.Plane()
            item["origin"] = point_tuple(plane.Location())
            item["normal"] = direction_tuple(plane.Axis().Direction())
        elif kind == "cylinder":
            cylinder = adaptor.Cylinder()
            item["radius"] = float(cylinder.Radius())
            item["axis_location"] = point_tuple(cylinder.Location())
            item["axis_direction"] = direction_tuple(cylinder.Axis().Direction())
        elif kind == "cone":
            cone = adaptor.Cone()
            item["semi_angle"] = float(cone.SemiAngle())
            item["reference_radius"] = float(cone.RefRadius())
            item["axis_location"] = point_tuple(cone.Location())
            item["axis_direction"] = direction_tuple(cone.Axis().Direction())
        elif kind == "bspline_surface":
            surface = adaptor.BSpline()
            item["u_degree"] = int(surface.UDegree())
            item["v_degree"] = int(surface.VDegree())
            item["u_pole_count"] = int(surface.NbUPoles())
            item["v_pole_count"] = int(surface.NbVPoles())
            item["u_knot_count"] = int(surface.NbUKnots())
            item["v_knot_count"] = int(surface.NbVKnots())
            item["u_periodic"] = bool(surface.IsUPeriodic())
            item["v_periodic"] = bool(surface.IsVPeriodic())
            item["u_rational"] = bool(surface.IsURational())
            item["v_rational"] = bool(surface.IsVRational())
    except Exception as exc:
        item["surface_detail_error"] = str(exc)
    return item


def solid_detail(solid, index):
    o = v.load_occ()
    faces = v.explore(solid, o["TopAbs_FACE"])
    detailed_faces = [face_detail(face, i) for i, face in enumerate(faces)]
    return {
        "index": index,
        "volume": v.volume(solid),
        "area": v.area(solid),
        "bbox": v.bbox(solid),
        "center_of_mass": v.center_of_mass(solid),
        "valid": v.is_valid(solid),
        "face_count": len(faces),
        "surface_type_counts": dict(Counter(face["type"] for face in detailed_faces)),
        "faces": detailed_faces,
    }


def inspect_step(path: Path):
    o = v.load_occ()
    shape = v.read_step(path)
    solids = v.explore(shape, o["TopAbs_SOLID"])
    solids.sort(key=v.volume, reverse=True)
    return {
        "path": str(path),
        "sha256": v.sha256(path),
        "compound_volume": v.volume(shape),
        "compound_area": v.area(shape),
        "solid_count": len(solids),
        "solids": [solid_detail(solid, i) for i, solid in enumerate(solids)],
    }


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: interrogate_solder_solids.py REFERENCE_STEP GENERATED_STEP")
    reference = Path(sys.argv[1])
    generated = Path(sys.argv[2])
    payload = {
        "reference": inspect_step(reference),
        "generated": inspect_step(generated),
    }
    output = ROOT / "kailh_soldered_feature_interrogation.json"
    output.write_text(json.dumps(payload, indent=2))
    compact = {
        side: [
            {
                "index": solid["index"],
                "volume": solid["volume"],
                "area": solid["area"],
                "bbox": solid["bbox"],
                "center_of_mass": solid["center_of_mass"],
                "face_count": solid["face_count"],
                "surface_type_counts": solid["surface_type_counts"],
            }
            for solid in payload[side]["solids"]
        ]
        for side in ("reference", "generated")
    }
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
