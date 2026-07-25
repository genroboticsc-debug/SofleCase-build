from __future__ import annotations

import hashlib
import importlib.util
import math
import sys
import traceback
from pathlib import Path

from build123d import Edge, Face, Solid, Wire, extrude, export_step, import_step

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


def vec_tuple(v):
    return (v.X, v.Y, v.Z)


def add(a, b):
    return type(a)(a.X + b.X, a.Y + b.Y, a.Z + b.Z)


def mul(v, s):
    return type(v)(v.X * s, v.Y * s, v.Z * s)


def cross(a, b):
    return type(a)(a.Y * b.Z - a.Z * b.Y, a.Z * b.X - a.X * b.Z, a.X * b.Y - a.Y * b.X)


def unit(v):
    length = math.sqrt(v.X * v.X + v.Y * v.Y + v.Z * v.Z)
    return type(v)(v.X / length, v.Y / length, v.Z / length)


def summary(name, shape):
    bb = shape.bounding_box(optimal=True)
    print(name, "valid=", shape.is_valid(), "solids=", len(shape.solids()), "faces=", len(shape.faces()), "edges=", len(shape.edges()), "volume=", shape.volume, "area=", shape.area)
    print(" bbox", bb.min.to_tuple(), bb.max.to_tuple(), "center", shape.center().to_tuple())


def exact_pad():
    z = mod.SOLDER_TOP_Z_MM
    points = [
        (4.54488778941404, 3.76578476453536, z),
        (7.210189558447279, 3.7479184533604792, z),
        (7.21019340060459, 6.41087029507891, z),
        (4.54488778941404, 6.41087029507891, z),
    ]
    edges = [Edge.make_line(points[index], points[(index + 1) % 4]) for index in range(4)]
    wires = Wire.combine(edges, tol=1.0e-8)
    if len(wires) != 1:
        raise RuntimeError("pad wire failed")
    return extrude(Face(wires[0]), mod.SOLDER_PAD_Z_MAX_MM - z, dir=(0, 0, 1))


def profile_edges(x):
    return [Edge.make_bezier(*[(x, y, z) for y, z in span]) for span in mod.SOLDER_PROFILE_BEZIER_SPANS_YZ]


def quarter_sector(path):
    source = path.position_at(0.0)
    tangent = unit(path.tangent_at(0.0))
    x_axis = type(source)(1.0, 0.0, 0.0)
    inward = unit(cross(x_axis, tangent))
    center = add(source, mul(inward, R))
    terminal = add(center, mul(x_axis, R))
    mid = add(center, mul(add(x_axis, mul(inward, -1.0)), R / math.sqrt(2.0)))
    edges = [
        Edge.make_line(source, center),
        Edge.make_line(center, terminal),
        Edge.make_three_point_arc(terminal, mid, source),
    ]
    wires = Wire.combine(edges, tol=1.0e-8)
    if len(wires) != 1:
        raise RuntimeError("sector wire failed")
    face = Face(wires[0])
    print("SECTOR", "source", source.to_tuple(), "tangent", tangent.to_tuple(), "inward", inward.to_tuple(), "area", face.area)
    return face


def build_candidate():
    x0 = mod.SOLDER_X_START_MM
    xt = mod.SOLDER_TAPER_START_X_MM
    base = extrude(Face(mod._solder_profile_wire(x0)), xt - x0, dir=(1, 0, 0))
    summary("BASE", base)
    paths = profile_edges(xt)
    rolls = []
    for index, path in enumerate(paths):
        sector = quarter_sector(path)
        try:
            roll = Solid.sweep(sector.outer_wire(), path)
        except Exception:
            roll = Solid.sweep(sector, path)
        summary(f"ROLL_{index}", roll)
        export_step(roll, OUT / f"roll_{index}.step")
        rolls.append(roll)
    roll_union = rolls[0]
    for index, roll in enumerate(rolls[1:], 1):
        try:
            roll_union = roll_union.fuse(roll).clean()
            summary(f"ROLL_UNION_{index}", roll_union)
        except Exception as exc:
            print("ROLL_FUSE_FAIL", index, repr(exc))
    export_step(roll_union, OUT / "roll_union.step")
    pad = exact_pad()
    summary("PAD", pad)
    result = base.fuse(roll_union, pad).clean()
    summary("CANDIDATE", result)
    export_step(result, OUT / "candidate_right_solder.step")
    return result


def reference_solder():
    digest = hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
    print("REFERENCE_SHA256", digest)
    if digest != EXPECTED_SHA256:
        raise RuntimeError("reference checksum mismatch")
    model = import_step(REFERENCE)
    solids = list(model.solids())
    print("REFERENCE_SOLIDS", [(index, solid.volume, solid.bounding_box(optimal=True).min.to_tuple(), solid.bounding_box(optimal=True).max.to_tuple()) for index, solid in enumerate(solids)])
    matching = [solid for solid in solids if 1.7 < solid.volume < 1.9 and solid.bounding_box(optimal=True).min.X > 0]
    if len(matching) != 1:
        raise RuntimeError(f"right solder selection failed: {len(matching)}")
    reference = matching[0]
    summary("REFERENCE_RIGHT", reference)
    export_step(reference, OUT / "reference_right_solder.step")
    return reference


def compare(reference, candidate):
    print("VOLUME_ERROR_PERCENT", abs(candidate.volume - reference.volume) / reference.volume * 100.0)
    print("AREA_ERROR_PERCENT", abs(candidate.area - reference.area) / reference.area * 100.0)
    rbb = reference.bounding_box(optimal=True)
    cbb = candidate.bounding_box(optimal=True)
    print("BBOX_DIFF", abs(cbb.size.X-rbb.size.X), abs(cbb.size.Y-rbb.size.Y), abs(cbb.size.Z-rbb.size.Z))
    try:
        a = reference - candidate
        b = candidate - reference
        av = a.volume if a is not None else 0.0
        bv = b.volume if b is not None else 0.0
        xor = av + bv
        print("BOOLEAN", "A_MINUS_B", av, "B_MINUS_A", bv, "XOR", xor, "XOR_PERCENT", xor/reference.volume*100.0)
        if a is not None: export_step(a, OUT / "reference_minus_candidate.step")
        if b is not None: export_step(b, OUT / "candidate_minus_reference.step")
    except Exception as exc:
        print("BOOLEAN_FAIL", repr(exc))


def main():
    reference = reference_solder()
    candidate = build_candidate()
    compare(reference, candidate)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
