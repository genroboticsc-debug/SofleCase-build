#!/usr/bin/env python3
"""Exact OCCT B-rep interrogation for the two Dilemma tenting-puck references.

No tessellation is used for dimensions, topology, mass properties, surface
classification, or boolean comparison. All reported values come directly from
OpenCascade through Build123d/OCP.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from build123d import Shape, Vector, import_step
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.Bnd import Bnd_Box
from OCP.GProp import GProp_GProps
from OCP.GeomAbs import (
    GeomAbs_BSplineCurve,
    GeomAbs_BezierCurve,
    GeomAbs_Circle,
    GeomAbs_Cone,
    GeomAbs_Cylinder,
    GeomAbs_Ellipse,
    GeomAbs_Hyperbola,
    GeomAbs_Line,
    GeomAbs_OffsetCurve,
    GeomAbs_OffsetSurface,
    GeomAbs_OtherCurve,
    GeomAbs_OtherSurface,
    GeomAbs_Parabola,
    GeomAbs_Plane,
    GeomAbs_Sphere,
    GeomAbs_SurfaceOfExtrusion,
    GeomAbs_SurfaceOfRevolution,
    GeomAbs_Torus,
)
from OCP.TopAbs import TopAbs_REVERSED

ROOT = Path(__file__).resolve().parent
REF_DIR = ROOT / "reference"
OUT_DIR = ROOT / "analysis_output"
REF_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

RAW_BASE = (
    "https://raw.githubusercontent.com/Bastardkb/Dilemma/main/"
    "mechanical/cases/3x5_2/tenting_puck_hex/STEP/"
)

REFERENCES = {
    "integrated": {
        "filename": "Dilemma Case Integrated Tenting Puck.STEP",
        "git_blob_sha1": "c7d1e396d76daef9edb59edbba9a5fbe9d81696d",
        "sha256": "9a86c9e8179889fcdeb632e50cfb1b79c7c395290231f601494ba0046bc3178e",
    },
    "opening": {
        "filename": "Dilemma Case Tenting Puck Opening.STEP",
        "git_blob_sha1": "e1c89dd1d85e27850a9711011e2264750f4c3b01",
        "sha256": "adafdc2eea773a0b9fcd77e832fe459844d0d8de7617903eb9607822347eb14d",
    },
}

SURFACE_NAMES = {
    GeomAbs_Plane: "PLANE",
    GeomAbs_Cylinder: "CYLINDER",
    GeomAbs_Cone: "CONE",
    GeomAbs_Sphere: "SPHERE",
    GeomAbs_Torus: "TORUS",
    GeomAbs_SurfaceOfRevolution: "SURFACE_OF_REVOLUTION",
    GeomAbs_SurfaceOfExtrusion: "SURFACE_OF_EXTRUSION",
    GeomAbs_OffsetSurface: "OFFSET_SURFACE",
    GeomAbs_OtherSurface: "OTHER_SURFACE",
}
CURVE_NAMES = {
    GeomAbs_Line: "LINE",
    GeomAbs_Circle: "CIRCLE",
    GeomAbs_Ellipse: "ELLIPSE",
    GeomAbs_Hyperbola: "HYPERBOLA",
    GeomAbs_Parabola: "PARABOLA",
    GeomAbs_BezierCurve: "BEZIER",
    GeomAbs_BSplineCurve: "BSPLINE",
    GeomAbs_OffsetCurve: "OFFSET_CURVE",
    GeomAbs_OtherCurve: "OTHER_CURVE",
}


def r(x: float, digits: int = 12) -> float:
    """Stable serialization without reducing kernel precision in calculations."""
    x = float(x)
    return 0.0 if abs(x) < 5e-15 else round(x, digits)


def vec(v: Any) -> list[float]:
    return [r(v.X()), r(v.Y()), r(v.Z())]


def direction(v: Any) -> list[float]:
    return vec(v)


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def acquire_reference(meta: dict[str, str]) -> Path:
    path = REF_DIR / meta["filename"]
    url = RAW_BASE + urllib.parse.quote(meta["filename"])
    if not path.exists():
        print(f"Downloading exact reference: {meta['filename']}", flush=True)
        urllib.request.urlretrieve(url, path)
    data = path.read_bytes()
    actual_sha256 = hashlib.sha256(data).hexdigest()
    actual_blob = git_blob_sha1(data)
    if actual_sha256 != meta["sha256"] or actual_blob != meta["git_blob_sha1"]:
        raise RuntimeError(
            f"Reference hash mismatch for {path.name}: "
            f"sha256={actual_sha256}, blob={actual_blob}"
        )
    return path


def unwrap_single_solid(shape: Shape) -> Shape:
    solids = list(shape.solids())
    if len(solids) != 1:
        raise RuntimeError(f"Expected exactly one solid, found {len(solids)}")
    return solids[0]


def props(shape: Shape) -> dict[str, Any]:
    vp = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, vp)
    sp = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape.wrapped, sp)
    box = Bnd_Box()
    BRepBndLib.Add_s(shape.wrapped, box, True)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    c = vp.CentreOfMass()
    return {
        "volume_mm3": r(vp.Mass()),
        "area_mm2": r(sp.Mass()),
        "com_mm": vec(c),
        "bbox_min_mm": [r(xmin), r(ymin), r(zmin)],
        "bbox_max_mm": [r(xmax), r(ymax), r(zmax)],
        "bbox_size_mm": [r(xmax - xmin), r(ymax - ymin), r(zmax - zmin)],
    }


def face_area(face: Any) -> float:
    p = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face.wrapped, p)
    return float(p.Mass())


def edge_length(edge: Any) -> float:
    p = GProp_GProps()
    BRepGProp.LinearProperties_s(edge.wrapped, p)
    return float(p.Mass())


def shape_bbox(shape: Any) -> list[float]:
    box = Bnd_Box()
    BRepBndLib.Add_s(shape.wrapped, box, True)
    return [r(x) for x in box.Get()]


def face_descriptor(face: Any, index: int) -> dict[str, Any]:
    a = BRepAdaptor_Surface(face.wrapped, True)
    st = a.GetType()
    out: dict[str, Any] = {
        "index": index,
        "surface_type": SURFACE_NAMES.get(st, f"ENUM_{int(st)}"),
        "orientation": "REVERSED" if face.wrapped.Orientation() == TopAbs_REVERSED else "FORWARD",
        "area_mm2": r(face_area(face)),
        "bbox_mm": shape_bbox(face),
        "uv_bounds": [r(a.FirstUParameter()), r(a.LastUParameter()), r(a.FirstVParameter()), r(a.LastVParameter())],
        "wire_count": len(list(face.wires())),
        "edge_count": len(list(face.edges())),
    }
    if st == GeomAbs_Plane:
        g = a.Plane()
        ax = g.Position()
        out.update(origin_mm=vec(ax.Location()), normal=direction(ax.Direction()), x_direction=direction(ax.XDirection()))
    elif st == GeomAbs_Cylinder:
        g = a.Cylinder()
        ax = g.Position()
        out.update(
            origin_mm=vec(ax.Location()), axis=direction(ax.Direction()), x_direction=direction(ax.XDirection()), radius_mm=r(g.Radius())
        )
    elif st == GeomAbs_Cone:
        g = a.Cone()
        ax = g.Position()
        out.update(
            origin_mm=vec(ax.Location()), axis=direction(ax.Direction()), x_direction=direction(ax.XDirection()),
            semi_angle_rad=r(g.SemiAngle()), reference_radius_mm=r(g.RefRadius()), apex_mm=vec(g.Apex())
        )
    elif st == GeomAbs_Sphere:
        g = a.Sphere()
        ax = g.Position()
        out.update(center_mm=vec(ax.Location()), axis=direction(ax.Direction()), radius_mm=r(g.Radius()))
    elif st == GeomAbs_Torus:
        g = a.Torus()
        ax = g.Position()
        out.update(
            center_mm=vec(ax.Location()), axis=direction(ax.Direction()), major_radius_mm=r(g.MajorRadius()), minor_radius_mm=r(g.MinorRadius())
        )
    return out


def edge_descriptor(edge: Any, index: int) -> dict[str, Any]:
    a = BRepAdaptor_Curve(edge.wrapped)
    ct = a.GetType()
    out: dict[str, Any] = {
        "index": index,
        "curve_type": CURVE_NAMES.get(ct, f"ENUM_{int(ct)}"),
        "length_mm": r(edge_length(edge)),
        "parameter_range": [r(a.FirstParameter()), r(a.LastParameter())],
        "bbox_mm": shape_bbox(edge),
    }
    p0 = a.Value(a.FirstParameter())
    p1 = a.Value(a.LastParameter())
    out["start_mm"] = vec(p0)
    out["end_mm"] = vec(p1)
    if ct == GeomAbs_Line:
        g = a.Line()
        out.update(origin_mm=vec(g.Location()), direction=direction(g.Direction()))
    elif ct == GeomAbs_Circle:
        g = a.Circle()
        ax = g.Position()
        out.update(center_mm=vec(ax.Location()), normal=direction(ax.Direction()), x_direction=direction(ax.XDirection()), radius_mm=r(g.Radius()))
    elif ct == GeomAbs_Ellipse:
        g = a.Ellipse()
        ax = g.Position()
        out.update(center_mm=vec(ax.Location()), normal=direction(ax.Direction()), major_radius_mm=r(g.MajorRadius()), minor_radius_mm=r(g.MinorRadius()))
    elif ct == GeomAbs_BSplineCurve:
        c = a.BSpline()
        out.update(
            degree=int(c.Degree()), pole_count=int(c.NbPoles()), knot_count=int(c.NbKnots()),
            rational=bool(c.IsRational()), periodic=bool(c.IsPeriodic()), closed=bool(c.IsClosed()),
            poles_mm=[vec(c.Pole(i)) for i in range(1, c.NbPoles() + 1)],
            knots=[r(c.Knot(i)) for i in range(1, c.NbKnots() + 1)],
            multiplicities=[int(c.Multiplicity(i)) for i in range(1, c.NbKnots() + 1)],
            weights=[r(c.Weight(i)) for i in range(1, c.NbPoles() + 1)] if c.IsRational() else None,
        )
    return out


def exact_z_inventory(shape: Shape) -> dict[str, Any]:
    zs = sorted({r(v.Z, 10) for v in shape.vertices()})
    face_levels: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for i, face in enumerate(shape.faces()):
        a = BRepAdaptor_Surface(face.wrapped, True)
        if a.GetType() != GeomAbs_Plane:
            continue
        plane = a.Plane()
        n = plane.Axis().Direction()
        if abs(abs(n.Z()) - 1.0) < 1e-10:
            z = r(plane.Location().Z(), 10)
            face_levels[str(z)].append({"face_index": i, "area_mm2": r(face_area(face)), "normal_z": r(n.Z())})
    return {"vertex_z_levels_mm": zs, "horizontal_planar_faces_by_z": dict(face_levels)}


def analyze_shape(shape: Shape) -> dict[str, Any]:
    faces = list(shape.faces())
    edges = list(shape.edges())
    vertices = list(shape.vertices())
    face_data = [face_descriptor(f, i) for i, f in enumerate(faces)]
    edge_data = [edge_descriptor(e, i) for i, e in enumerate(edges)]
    return {
        "mass_properties": props(shape),
        "topology": {
            "solids": len(list(shape.solids())),
            "shells": len(list(shape.shells())),
            "faces": len(faces),
            "wires": len(list(shape.wires())),
            "edges": len(edges),
            "vertices": len(vertices),
        },
        "surface_type_counts": dict(Counter(d["surface_type"] for d in face_data)),
        "curve_type_counts": dict(Counter(d["curve_type"] for d in edge_data)),
        "z_inventory": exact_z_inventory(shape),
        "faces": face_data,
        "edges": edge_data,
    }


def pct(diff: float, ref: float) -> float:
    return abs(diff) / abs(ref) * 100.0 if ref else (0.0 if diff == 0 else math.inf)


def compare_mass(a: Shape, b: Shape) -> dict[str, Any]:
    pa, pb = props(a), props(b)
    dc = [pb["com_mm"][i] - pa["com_mm"][i] for i in range(3)]
    return {
        "volume_difference_mm3": r(pb["volume_mm3"] - pa["volume_mm3"]),
        "volume_difference_percent_of_a": r(pct(pb["volume_mm3"] - pa["volume_mm3"], pa["volume_mm3"])),
        "area_difference_mm2": r(pb["area_mm2"] - pa["area_mm2"]),
        "area_difference_percent_of_a": r(pct(pb["area_mm2"] - pa["area_mm2"], pa["area_mm2"])),
        "com_delta_mm": [r(x) for x in dc],
        "com_distance_mm": r(math.sqrt(sum(x * x for x in dc))),
    }


def boolean_delta(a: Shape, b: Shape) -> dict[str, Any]:
    print("Computing exact OCCT directional differences...", flush=True)
    a_minus_b = a.cut(b)
    b_minus_a = b.cut(a)
    pa = props(a_minus_b) if list(a_minus_b.solids()) else {"volume_mm3": 0.0, "area_mm2": 0.0, "com_mm": [0, 0, 0], "bbox_min_mm": None, "bbox_max_mm": None, "bbox_size_mm": None}
    pb = props(b_minus_a) if list(b_minus_a.solids()) else {"volume_mm3": 0.0, "area_mm2": 0.0, "com_mm": [0, 0, 0], "bbox_min_mm": None, "bbox_max_mm": None, "bbox_size_mm": None}
    sym_volume = float(pa["volume_mm3"]) + float(pb["volume_mm3"])
    denom = float(props(a)["volume_mm3"])
    return {
        "a_minus_b": {"mass_properties": pa, "solid_count": len(list(a_minus_b.solids())), "face_count": len(list(a_minus_b.faces()))},
        "b_minus_a": {"mass_properties": pb, "solid_count": len(list(b_minus_a.solids())), "face_count": len(list(b_minus_a.faces()))},
        "symmetric_difference_volume_mm3": r(sym_volume),
        "symmetric_difference_percent_of_a": r(sym_volume / denom * 100.0),
    }


def main() -> int:
    print(f"Python: {sys.version}")
    try:
        import build123d
        import OCP
        print(f"build123d: {build123d.__version__}")
        print(f"OCP: {getattr(OCP, '__version__', 'unknown')}")
    except Exception:
        pass

    shapes: dict[str, Shape] = {}
    report: dict[str, Any] = {"reference_hashes": {}, "models": {}}
    for key, meta in REFERENCES.items():
        path = acquire_reference(meta)
        data = path.read_bytes()
        report["reference_hashes"][key] = {
            "filename": path.name,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "git_blob_sha1": git_blob_sha1(data),
        }
        print(f"Importing exact STEP B-rep: {path.name}", flush=True)
        shape = unwrap_single_solid(import_step(path))
        shapes[key] = shape
        print(f"Analyzing exact topology and analytic geometry: {key}", flush=True)
        report["models"][key] = analyze_shape(shape)

    report["reference_to_reference_mass_delta"] = compare_mass(shapes["opening"], shapes["integrated"])
    report["reference_to_reference_boolean_delta"] = boolean_delta(shapes["opening"], shapes["integrated"])

    out = OUT_DIR / "reference_exact_geometry.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    summary = {
        key: {
            "mass_properties": report["models"][key]["mass_properties"],
            "topology": report["models"][key]["topology"],
            "surface_type_counts": report["models"][key]["surface_type_counts"],
            "curve_type_counts": report["models"][key]["curve_type_counts"],
            "vertex_z_levels_mm": report["models"][key]["z_inventory"]["vertex_z_levels_mm"],
        }
        for key in ("integrated", "opening")
    }
    summary["boolean_delta"] = report["reference_to_reference_boolean_delta"]
    (OUT_DIR / "reference_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
