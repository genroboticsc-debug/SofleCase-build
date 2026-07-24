from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run_validation as v

REFERENCE_SOLDER_INDEX = 1
RAW_EXTRUSION_LENGTH_MM = 2.0
TERMINAL_ROLL_RADIUS_MM = 0.375
JUNCTION_ROUND_RADIUS_MM = 0.07
PAD_Z_MIN_MM = 1.75
PAD_Z_MAX_MM = 1.80
PAD_POINTS_XY = (
    (4.54488778941404, 3.76578476453536),
    (7.210189558447279, 3.7479184533604792),
    (7.21019340060459, 6.41087029507891),
    (4.54488778941404, 6.41087029507891),
)


def point_tuple(point):
    return [float(point.X()), float(point.Y()), float(point.Z())]


def load_production_module(generated_step: Path):
    script = (
        generated_step.parent.parent.parent
        / "scripts"
        / "components"
        / "kailh cherry socket soldered.py"
    )
    spec = importlib.util.spec_from_file_location("kailh_soldered_production", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load production module: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, script


def write_step_shape(shape, path: Path):
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

    path.parent.mkdir(parents=True, exist_ok=True)
    writer = STEPControl_Writer()
    transfer_status = writer.Transfer(shape, STEPControl_AsIs)
    if int(transfer_status) != int(IFSelect_RetDone):
        raise RuntimeError(f"STEP transfer failed: {transfer_status}")
    write_status = writer.Write(str(path))
    if int(write_status) != int(IFSelect_RetDone):
        raise RuntimeError(f"STEP write failed: {write_status}")


def shape_summary(shape):
    o = v.load_occ()
    faces = v.explore(shape, o["TopAbs_FACE"])
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
    types = []
    cylinders = []
    for raw_face in faces:
        face = o["TopoDS"].Face_s(raw_face)
        adaptor = o["BRepAdaptor_Surface"](face, True)
        kind = surface_names.get(str(adaptor.GetType()), str(adaptor.GetType()))
        types.append(kind)
        if kind == "cylinder":
            cylinder = adaptor.Cylinder()
            cylinders.append(
                {
                    "radius": float(cylinder.Radius()),
                    "axis_location": point_tuple(cylinder.Location()),
                    "axis_direction": point_tuple(cylinder.Axis().Direction()),
                    "area": v.area(face),
                    "bbox": v.bbox(face),
                }
            )
    return {
        "volume": v.volume(shape),
        "area": v.area(shape),
        "bbox": v.bbox(shape),
        "center_of_mass": v.center_of_mass(shape),
        "valid": v.is_valid(shape),
        "face_count": len(faces),
        "surface_type_counts": dict(Counter(types)),
        "cylinders": cylinders,
    }


def build_native_candidate(module):
    from build123d import Face, Wire, extrude, fillet

    raw_end_x = module.SOLDER_X_START_MM + RAW_EXTRUSION_LENGTH_MM
    profile_face = Face(module._solder_profile_wire(module.SOLDER_X_START_MM))
    raw_meniscus = extrude(profile_face, RAW_EXTRUSION_LENGTH_MM, dir=(1, 0, 0))

    terminal_edges = []
    terminal_edge_bounds = []
    for edge in raw_meniscus.edges():
        bounds = v.bbox(edge.wrapped)
        if abs(bounds[0] - raw_end_x) <= 2.0e-5 and abs(bounds[3] - raw_end_x) <= 2.0e-5:
            terminal_edges.append(edge)
            terminal_edge_bounds.append(bounds)
    if len(terminal_edges) != 2:
        raise RuntimeError(
            f"Expected two terminal perimeter edges at X={raw_end_x}, found {len(terminal_edges)}: {terminal_edge_bounds}"
        )

    rolled_shape = fillet(terminal_edges, TERMINAL_ROLL_RADIUS_MM).clean()
    rolled = rolled_shape.solids()[0]

    pad_wire = Wire.make_polygon(
        [(x, y, PAD_Z_MIN_MM) for x, y in PAD_POINTS_XY], close=True
    )
    pad = extrude(Face(pad_wire), PAD_Z_MAX_MM - PAD_Z_MIN_MM, dir=(0, 0, 1))
    fused = rolled.fuse(pad).clean()

    junction_edges = []
    junction_edge_bounds = []
    terminal_tangent_x = raw_end_x - TERMINAL_ROLL_RADIUS_MM
    for edge in fused.edges():
        bounds = v.bbox(edge.wrapped)
        lies_on_pad_plane = (
            abs(bounds[2] - PAD_Z_MIN_MM) <= 2.0e-5
            and abs(bounds[5] - PAD_Z_MIN_MM) <= 2.0e-5
        )
        is_terminal_junction = (
            bounds[0] >= terminal_tangent_x - 2.0e-5
            and bounds[3] <= raw_end_x + 2.0e-5
        )
        not_pad_outer_edge = (
            bounds[0] > min(x for x, _ in PAD_POINTS_XY) + 0.05
            and bounds[3] < max(x for x, _ in PAD_POINTS_XY) - 0.05
        )
        if lies_on_pad_plane and is_terminal_junction and not_pad_outer_edge:
            junction_edges.append(edge)
            junction_edge_bounds.append(bounds)
    if not junction_edges:
        raise RuntimeError("No terminal pad-junction edges identified")

    rounded_shape = fillet(junction_edges, JUNCTION_ROUND_RADIUS_MM).clean()
    candidate = rounded_shape.solids()[0]
    if not candidate.is_valid:
        raise RuntimeError("Native solder candidate is invalid")
    return candidate, {
        "raw_end_x": raw_end_x,
        "terminal_edge_count": len(terminal_edges),
        "terminal_edge_bounds": terminal_edge_bounds,
        "junction_edge_count": len(junction_edges),
        "junction_edge_bounds": junction_edge_bounds,
    }


def exact_pair(reference_path: Path, candidate_path: Path):
    validator = ROOT / "original_validate_geometry.py"
    attempts = []
    for operation, fuzzy in (("pairfiles", 0.0), ("pairdirect", 0.0), ("pairfiles", 1.0e-10)):
        command = [
            sys.executable,
            "-u",
            str(validator),
            "--worker",
            "--root",
            str(ROOT / "work"),
            operation,
            str(reference_path),
            str(candidate_path),
            str(fuzzy),
        ]
        try:
            process = subprocess.run(
                command, text=True, capture_output=True, timeout=180
            )
        except subprocess.TimeoutExpired:
            attempts.append({"operation": operation, "fuzzy": fuzzy, "error": "timeout"})
            continue
        lines = [
            line.strip()
            for line in process.stdout.splitlines()
            if line.strip().startswith("{")
        ]
        payload = json.loads(lines[-1]) if lines else {
            "success": False,
            "error": "no JSON result",
            "stdout": process.stdout[-2000:],
            "stderr": process.stderr[-2000:],
        }
        payload["operation"] = operation
        payload["fuzzy"] = fuzzy
        attempts.append(payload)
        if payload.get("success"):
            return {"success": True, "selected": payload, "attempts": attempts}
    return {"success": False, "attempts": attempts}


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: interrogate_solder_solids.py REFERENCE_STEP GENERATED_STEP")
    reference_path = Path(sys.argv[1])
    generated_path = Path(sys.argv[2])
    module, production_script = load_production_module(generated_path)

    o = v.load_occ()
    reference_shape = v.read_step(reference_path)
    reference_solids = v.explore(reference_shape, o["TopAbs_SOLID"])
    reference_solids.sort(key=v.volume, reverse=True)
    reference_solder = reference_solids[REFERENCE_SOLDER_INDEX]

    generated_shape = v.read_step(generated_path)
    generated_solids = v.explore(generated_shape, o["TopAbs_SOLID"])
    generated_solids.sort(key=v.volume, reverse=True)
    generated_solder = generated_solids[REFERENCE_SOLDER_INDEX]

    payload = {
        "reference_sha256": v.sha256(reference_path),
        "generated_sha256": v.sha256(generated_path),
        "production_script": str(production_script),
        "reference_solder": shape_summary(reference_solder),
        "current_generated_solder": shape_summary(generated_solder),
        "native_candidate_parameters": {
            "raw_extrusion_length_mm": RAW_EXTRUSION_LENGTH_MM,
            "terminal_roll_radius_mm": TERMINAL_ROLL_RADIUS_MM,
            "junction_round_radius_mm": JUNCTION_ROUND_RADIUS_MM,
            "pad_z_min_mm": PAD_Z_MIN_MM,
            "pad_z_max_mm": PAD_Z_MAX_MM,
            "pad_points_xy": PAD_POINTS_XY,
        },
    }

    try:
        candidate, selection = build_native_candidate(module)
        candidate_path = ROOT / "kailh_native_solder_candidate.step"
        reference_solder_path = ROOT / "kailh_reference_solder_right.step"
        from build123d import export_step

        export_step(candidate, candidate_path)
        write_step_shape(reference_solder, reference_solder_path)
        payload["native_candidate"] = shape_summary(candidate.wrapped)
        payload["native_candidate_selection"] = selection
        payload["native_candidate_exact_boolean"] = exact_pair(
            reference_solder_path, candidate_path
        )
        payload["candidate_step"] = str(candidate_path)
        payload["reference_solder_step"] = str(reference_solder_path)
    except Exception as exc:
        payload["native_candidate_error"] = f"{type(exc).__name__}: {exc}"

    output = ROOT / "kailh_soldered_feature_interrogation.json"
    output.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
