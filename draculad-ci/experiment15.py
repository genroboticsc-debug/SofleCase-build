from __future__ import annotations

import hashlib
import importlib.util
import math
import sys
import traceback
from pathlib import Path

from build123d import Compound, Edge, Face, Shell, Vector, Wire, export_step, import_step

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "scripts" / "components" / "kailh cherry socket soldered.py"
REFERENCE = ROOT / "reference.step"
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)
R = 0.375
EXPECTED = "0b938e39f0fd84a6b424ef9c49f2c6aa8a232fa2a68f9105a0f9b821c987cc56"
SPLITS = [
    (6.0556181584155, 1.52891560478045),
    (5.4686267080952, 1.38160563822046),
    (4.7023519634925, 1.43492679304685),
    (4.12087378923582, 1.57689067591221),
]
REFERENCE_FACE_AREAS = [
    0.09246547589811499,
    0.5622276448740541,
    0.40849986990533693,
    0.6122345330242496,
    0.06353283176612257,
]

spec = importlib.util.spec_from_file_location("kailh_mod", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def add(a, b):
    return Vector(a.X + b.X, a.Y + b.Y, a.Z + b.Z)


def mul(a, scale):
    return Vector(a.X * scale, a.Y * scale, a.Z * scale)


def cross(a, b):
    return Vector(a.Y * b.Z - a.Z * b.Y, a.Z * b.X - a.X * b.Z, a.X * b.Y - a.Y * b.X)


def unit(a):
    norm = math.sqrt(a.X * a.X + a.Y * a.Y + a.Z * a.Z)
    return Vector(a.X / norm, a.Y / norm, a.Z / norm)


def full_profile_wire(x):
    edges = [Edge.make_bezier(*[(x, y, z) for y, z in span]) for span in mod.SOLDER_PROFILE_BEZIER_SPANS_YZ]
    wires = Wire.combine(edges, tol=mod.WIRE_JOIN_TOLERANCE_MM)
    if len(wires) != 1:
        raise RuntimeError(f"profile wire count {len(wires)}")
    return wires[0]


def nearest_u(wire, target):
    target_y, target_z = target

    def error(u):
        point = wire.position_at(u)
        return (point.Y - target_y) ** 2 + (point.Z - target_z) ** 2

    samples = 5000
    best_index = min(range(samples + 1), key=lambda i: error(i / samples))
    lo = max(0.0, (best_index - 2) / samples)
    hi = min(1.0, (best_index + 2) / samples)
    phi = (math.sqrt(5.0) - 1.0) / 2.0
    c = hi - phi * (hi - lo)
    d = lo + phi * (hi - lo)
    fc, fd = error(c), error(d)
    for _ in range(90):
        if fc < fd:
            hi, d, fd = d, c, fc
            c = hi - phi * (hi - lo)
            fc = error(c)
        else:
            lo, c, fc = c, d, fd
            d = lo + phi * (hi - lo)
            fd = error(d)
    return (lo + hi) / 2.0


def roll_arc(path):
    source = path.position_at(0.0)
    tangent = unit(path.tangent_at(0.0))
    x_axis = Vector(1, 0, 0)
    inward = unit(cross(tangent, x_axis))
    center = add(source, mul(inward, R))
    terminal = add(center, mul(x_axis, R))
    midpoint = add(center, mul(add(x_axis, mul(inward, -1.0)), R / math.sqrt(2.0)))
    arc = Edge.make_three_point_arc(source, midpoint, terminal)
    print(
        "ARC",
        "source", source.to_tuple(),
        "center", center.to_tuple(),
        "terminal", terminal.to_tuple(),
        "length", arc.length,
        "expected", math.pi * R / 2.0,
    )
    return arc


def select_reference_solid():
    if hashlib.sha256(REFERENCE.read_bytes()).hexdigest() != EXPECTED:
        raise RuntimeError("reference checksum mismatch")
    model = import_step(REFERENCE)
    solids = [solid for solid in model.solids() if 1.7 < solid.volume < 1.9 and solid.bounding_box(optimal=True).min.X > 0]
    if len(solids) != 1:
        raise RuntimeError(f"reference solder selection count {len(solids)}")
    return solids[0]


def select_reference_faces(reference):
    selected = []
    remaining = list(reference.faces())
    for area in REFERENCE_FACE_AREAS:
        face = min(remaining, key=lambda candidate: abs(candidate.area - area))
        if abs(face.area - area) > 1.0e-8:
            raise RuntimeError(f"reference face area not found {area}")
        selected.append(face)
        remaining.remove(face)
    return selected


def face_metrics(index, generated, reference):
    gbb = generated.bounding_box(optimal=True)
    rbb = reference.bounding_box(optimal=True)
    print(
        "COMPARE_FACE", index,
        "g_area", generated.area,
        "r_area", reference.area,
        "area_error_percent", abs(generated.area - reference.area) / reference.area * 100.0,
        "distance", generated.distance_to(reference),
        "g_bbox", gbb.min.to_tuple(), gbb.max.to_tuple(),
        "r_bbox", rbb.min.to_tuple(), rbb.max.to_tuple(),
        "bbox_delta", (
            abs(gbb.min.X - rbb.min.X), abs(gbb.min.Y - rbb.min.Y), abs(gbb.min.Z - rbb.min.Z),
            abs(gbb.max.X - rbb.max.X), abs(gbb.max.Y - rbb.max.Y), abs(gbb.max.Z - rbb.max.Z),
        ),
        "g_faces", len(generated.faces()),
        "g_edges", len(generated.edges()),
        "valid", generated.is_valid(),
    )


def main():
    reference = select_reference_solid()
    reference_faces = select_reference_faces(reference)
    export_step(Compound(children=reference_faces), OUT / "reference_canal_faces.step")

    wire = full_profile_wire(mod.SOLDER_TAPER_START_X_MM)
    parameters = [0.0] + [nearest_u(wire, point) for point in SPLITS] + [1.0]
    parameters.sort()
    print("PARAMETERS", parameters)

    generated_faces = []
    for index, (start, end) in enumerate(zip(parameters, parameters[1:])):
        path = wire.trim(start, end)
        arc = roll_arc(path)
        try:
            swept = Shell.sweep(arc, path)
        except Exception as first_error:
            print("EDGE_SWEEP_FAIL", index, repr(first_error))
            swept = Shell.sweep(Wire(arc), path)
        print(
            "SWEEP", index,
            "type", type(swept).__name__,
            "faces", len(swept.faces()),
            "edges", len(swept.edges()),
            "valid", swept.is_valid(),
            "area", swept.area,
        )
        export_step(swept, OUT / f"generated_canal_{index}.step")
        if len(swept.faces()) == 1:
            generated = swept.faces()[0]
        else:
            generated = swept
        generated_faces.append(generated)
        face_metrics(index, generated, reference_faces[index])

    export_step(Compound(children=generated_faces), OUT / "generated_canal_faces.step")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
