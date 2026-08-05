from __future__ import annotations

import hashlib
import importlib.util
import inspect
import math
import sys
import traceback
from pathlib import Path

from build123d import Compound, Edge, Shell, Transition, Vector, Wire, export_step, import_step

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "scripts" / "components" / "kailh cherry socket soldered.py"
REFERENCE = ROOT / "reference.step"
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)
R = 0.375
EXPECTED = "0b938e39f0fd84a6b424ef9c49f2c6aa8a232fa2a68f9105a0f9b821c987cc56"
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
    length = math.sqrt(a.X * a.X + a.Y * a.Y + a.Z * a.Z)
    return Vector(a.X / length, a.Y / length, a.Z / length)


def profile_wire(x):
    edges = [Edge.make_bezier(*[(x, y, z) for y, z in span]) for span in mod.SOLDER_PROFILE_BEZIER_SPANS_YZ]
    wires = Wire.combine(edges, tol=mod.WIRE_JOIN_TOLERANCE_MM)
    if len(wires) != 1:
        raise RuntimeError(f"profile wire count {len(wires)}")
    return wires[0]


def roll_arc(path):
    source = path.position_at(0.0)
    tangent = unit(path.tangent_at(0.0))
    x_axis = Vector(1, 0, 0)
    inward = unit(cross(tangent, x_axis))
    center = add(source, mul(inward, R))
    terminal = add(center, mul(x_axis, R))
    midpoint = add(center, mul(add(x_axis, mul(inward, -1.0)), R / math.sqrt(2.0)))
    return Edge.make_three_point_arc(source, midpoint, terminal)


def reference_data():
    if hashlib.sha256(REFERENCE.read_bytes()).hexdigest() != EXPECTED:
        raise RuntimeError("reference checksum mismatch")
    model = import_step(REFERENCE)
    solids = [solid for solid in model.solids() if 1.7 < solid.volume < 1.9 and solid.bounding_box(optimal=True).min.X > 0]
    if len(solids) != 1:
        raise RuntimeError(f"reference selection count {len(solids)}")
    reference = solids[0]
    remaining = list(reference.faces())
    faces = []
    for target_area in REFERENCE_FACE_AREAS:
        selected = min(remaining, key=lambda face: abs(face.area - target_area))
        faces.append(selected)
        remaining.remove(selected)
    compound = Compound(children=faces)
    return reference, faces, compound


def report(tag, shell, reference_compound):
    bbox = shell.bounding_box(optimal=True)
    rbox = reference_compound.bounding_box(optimal=True)
    print(
        "RESULT", tag,
        "type", type(shell).__name__,
        "valid", shell.is_valid(),
        "faces", len(shell.faces()),
        "edges", len(shell.edges()),
        "area", shell.area,
        "reference_area", reference_compound.area,
        "area_error_percent", abs(shell.area - reference_compound.area) / reference_compound.area * 100.0,
        "distance", shell.distance_to(reference_compound),
        "bbox", bbox.min.to_tuple(), bbox.max.to_tuple(),
        "reference_bbox", rbox.min.to_tuple(), rbox.max.to_tuple(),
    )
    for index, face in enumerate(shell.faces()):
        fbox = face.bounding_box(optimal=True)
        distances = [face.distance_to(reference_face) for reference_face in reference_compound.faces()]
        print(
            " FACE", index,
            "area", face.area,
            "edges", len(face.edges()),
            "bbox", fbox.min.to_tuple(), fbox.max.to_tuple(),
            "nearest_reference_face", min(range(len(distances)), key=distances.__getitem__),
            "distance", min(distances),
        )
    export_step(shell, OUT / f"full_pipe_{tag}.step")


def main():
    _, _, reference_compound = reference_data()
    export_step(reference_compound, OUT / "reference_canal_faces.step")
    path = profile_wire(mod.SOLDER_TAPER_START_X_MM)
    arc = roll_arc(path)
    print("SHELL_SWEEP_SIGNATURE", inspect.signature(Shell.sweep))
    print("TRANSITIONS", [(item.name, item.value) for item in Transition])
    attempts = [("default", {})]
    for transition in Transition:
        attempts.append((f"transition_{transition.name.lower()}", {"transition": transition}))
    attempts.extend([
        ("frenet_true", {"is_frenet": True}),
        ("frenet_false", {"is_frenet": False}),
    ])
    seen = set()
    for tag, kwargs in attempts:
        key = tuple(sorted((name, str(value)) for name, value in kwargs.items()))
        if key in seen:
            continue
        seen.add(key)
        try:
            shell = Shell.sweep(arc, path, **kwargs)
            report(tag, shell, reference_compound)
        except Exception as error:
            print("FAIL", tag, repr(error))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
