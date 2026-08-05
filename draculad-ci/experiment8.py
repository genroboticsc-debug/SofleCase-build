from __future__ import annotations

import hashlib
import importlib.util
import math
import sys
import traceback
from pathlib import Path

from build123d import Compound, Edge, Face, Solid, Wire, extrude, export_step, import_step

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "scripts" / "components" / "kailh cherry socket soldered.py"
REFERENCE = ROOT / "reference.step"
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)
R = 0.375
EXPECTED_SHA256 = "0b938e39f0fd84a6b424ef9c49f2c6aa8a232fa2a68f9105a0f9b821c987cc56"

spec = importlib.util.spec_from_file_location("kailh_mod", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def v(x, y, z):
    from build123d import Vector
    return Vector(x, y, z)


def add(a, b): return v(a.X + b.X, a.Y + b.Y, a.Z + b.Z)
def mul(a, s): return v(a.X * s, a.Y * s, a.Z * s)
def cross(a, b): return v(a.Y*b.Z-a.Z*b.Y, a.Z*b.X-a.X*b.Z, a.X*b.Y-a.Y*b.X)
def unit(a):
    n = math.sqrt(a.X*a.X+a.Y*a.Y+a.Z*a.Z)
    return v(a.X/n, a.Y/n, a.Z/n)


def summary(name, shape):
    bb = shape.bounding_box(optimal=True)
    print(name, "type=", type(shape).__name__, "valid=", shape.is_valid(), "solids=", len(shape.solids()), "faces=", len(shape.faces()), "edges=", len(shape.edges()), "volume=", shape.volume, "area=", shape.area)
    print(" bbox", bb.min.to_tuple(), bb.max.to_tuple(), "center", shape.center().to_tuple())


def profile_edges(x):
    return [Edge.make_bezier(*[(x, y, z) for y, z in span]) for span in mod.SOLDER_PROFILE_BEZIER_SPANS_YZ]


def open_profile_wire(x):
    wires = Wire.combine(profile_edges(x), tol=mod.WIRE_JOIN_TOLERANCE_MM)
    if len(wires) != 1:
        raise RuntimeError(f"open profile wire count {len(wires)}")
    return wires[0]


def exact_pad():
    z = mod.SOLDER_TOP_Z_MM
    points = [
        (4.54488778941404, 3.76578476453536, z),
        (7.210189558447279, 3.7479184533604792, z),
        (7.21019340060459, 6.41087029507891, z),
        (4.54488778941404, 6.41087029507891, z),
    ]
    wire = Wire.make_polygon(points, close=True)
    return extrude(Face(wire), 0.05, dir=(0, 0, 1))


def quarter_sector(path):
    source = path.position_at(0.0)
    tangent = unit(path.tangent_at(0.0))
    x_axis = v(1, 0, 0)
    # Profile is authored from upper-right to upper-left.  The enclosed solder
    # region lies on the T×X side of this directed curve.
    inward = unit(cross(tangent, x_axis))
    center = add(source, mul(inward, R))
    terminal = add(center, mul(x_axis, R))
    mid = add(center, mul(add(x_axis, mul(inward, -1.0)), R/math.sqrt(2.0)))
    edges = [
        Edge.make_line(source, center),
        Edge.make_line(center, terminal),
        Edge.make_three_point_arc(terminal, mid, source),
    ]
    wires = Wire.combine(edges, tol=1e-8)
    if len(wires) != 1:
        raise RuntimeError("quarter sector wire failed")
    face = Face(wires[0])
    print("SECTOR", source.to_tuple(), tangent.to_tuple(), inward.to_tuple(), "area", face.area)
    return face


def normalize_single(shape, name):
    solids = list(shape.solids())
    if len(solids) == 1:
        return solids[0]
    print(name, "MULTI_SOLID", len(solids), [s.volume for s in solids])
    return Compound(children=solids)


def build_full_wire_roll(x_terminal):
    path = open_profile_wire(x_terminal)
    section = quarter_sector(path)
    roll = Solid.sweep(section.outer_wire(), path)
    summary("FULL_WIRE_ROLL", roll)
    export_step(roll, OUT / "full_wire_roll.step")
    return roll


def build_span_rolls(x_terminal):
    rolls = []
    for index, path in enumerate(profile_edges(x_terminal)):
        section = quarter_sector(path)
        roll = Solid.sweep(section.outer_wire(), path)
        summary(f"SPAN_ROLL_{index}", roll)
        export_step(roll, OUT / f"span_roll_{index}.step")
        rolls.append(roll)
    return rolls


def build_candidate():
    x_start = mod.SOLDER_X_START_MM
    x_terminal = mod.SOLDER_TAPER_START_X_MM
    base = extrude(Face(mod._solder_profile_wire(x_start)), x_terminal-x_start, dir=(1,0,0))
    pad = exact_pad()
    summary("BASE", base)
    summary("PAD", pad)

    full_roll = None
    try:
        full_roll = build_full_wire_roll(x_terminal)
    except Exception as exc:
        print("FULL_WIRE_SWEEP_FAIL", repr(exc))

    span_rolls = build_span_rolls(x_terminal)
    candidates = []
    if full_roll is not None:
        try:
            c = base.fuse(full_roll, pad)
            c = normalize_single(c, "FULL_CANDIDATE")
            summary("FULL_CANDIDATE", c)
            export_step(c, OUT / "candidate_full_wire.step")
            candidates.append(("full", c))
        except Exception as exc:
            print("FULL_CANDIDATE_FUSE_FAIL", repr(exc))

    # Fuse all span rolls together with the base in one Boolean call so OCCT can
    # partition their self-overlapping valley regions globally.
    try:
        c = base.fuse(*span_rolls, pad)
        c = normalize_single(c, "SPAN_CANDIDATE")
        summary("SPAN_CANDIDATE", c)
        export_step(c, OUT / "candidate_span_global.step")
        candidates.append(("span", c))
    except Exception as exc:
        print("SPAN_GLOBAL_FUSE_FAIL", repr(exc))

    if not candidates:
        raise RuntimeError("no candidate built")
    return candidates


def reference_solder():
    digest = hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
    print("REFERENCE_SHA256", digest)
    if digest != EXPECTED_SHA256:
        raise RuntimeError("reference checksum mismatch")
    model = import_step(REFERENCE)
    matching = [s for s in model.solids() if 1.7 < s.volume < 1.9 and s.bounding_box(optimal=True).min.X > 0]
    if len(matching) != 1:
        raise RuntimeError(f"right reference selection failed: {len(matching)}")
    ref = matching[0]
    summary("REFERENCE_RIGHT", ref)
    export_step(ref, OUT / "reference_right_solder.step")
    return ref


def compare(reference, name, candidate):
    print("COMPARE", name)
    print(" VOLUME_ERROR_PERCENT", abs(candidate.volume-reference.volume)/reference.volume*100)
    print(" AREA_ERROR_PERCENT", abs(candidate.area-reference.area)/reference.area*100)
    rbb=reference.bounding_box(optimal=True); cbb=candidate.bounding_box(optimal=True)
    print(" BBOX_SIZE_DIFF", abs(cbb.size.X-rbb.size.X), abs(cbb.size.Y-rbb.size.Y), abs(cbb.size.Z-rbb.size.Z))
    try:
        a = reference.cut(candidate)
        b = candidate.cut(reference)
        av = sum(s.volume for s in a.solids()) if a is not None else 0.0
        bv = sum(s.volume for s in b.solids()) if b is not None else 0.0
        print(" BOOLEAN", av, bv, av+bv, (av+bv)/reference.volume*100)
        if a is not None: export_step(a, OUT/f"reference_minus_{name}.step")
        if b is not None: export_step(b, OUT/f"{name}_minus_reference.step")
    except Exception as exc:
        print(" BOOLEAN_FAIL", repr(exc))


def main():
    reference = reference_solder()
    for name, candidate in build_candidate():
        compare(reference, name, candidate)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
