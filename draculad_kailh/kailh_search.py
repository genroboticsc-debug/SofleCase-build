from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from pathlib import Path

from build123d import Edge, Face, Wire, export_step, export_stl, extrude, fillet, import_step

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "kailh_socket.py"
REFERENCE = ROOT / "kailh_reference.step"
OUT = ROOT / "results"
OUT.mkdir(exist_ok=True)

spec = importlib.util.spec_from_file_location("kailh_socket", TARGET)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def edge_record(index, edge):
    b = edge.bounding_box()
    try:
        geom = str(edge.geom_type)
    except Exception:
        geom = "unknown"
    return {
        "index": index,
        "geom_type": geom,
        "length": edge.length,
        "bbox": [b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z],
        "center": [edge.center().X, edge.center().Y, edge.center().Z],
        "start": list(edge.position_at(0)),
        "end": list(edge.position_at(1)),
    }


def metrics(shape):
    b = shape.bounding_box()
    c = shape.center_of_mass
    return {
        "valid": bool(shape.is_valid),
        "volume": float(shape.volume),
        "area": float(shape.area),
        "bbox": [b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z],
        "com": [c.X, c.Y, c.Z],
        "solids": len(shape.solids()),
        "faces": len(shape.faces()),
        "edges": len(shape.edges()),
    }


def shape_single(shape, label):
    solids = shape.solids()
    if len(solids) != 1:
        raise RuntimeError(f"{label}: expected one solid, got {len(solids)}")
    result = solids[0]
    if not result.is_valid:
        raise RuntimeError(f"{label}: invalid solid")
    return result


def exact_xor(a, b):
    am = a.cut(b)
    bm = b.cut(a)
    av = float(am.volume)
    bv = float(bm.volume)
    return {
        "a_minus_b": av,
        "b_minus_a": bv,
        "xor_volume": av + bv,
        "xor_pct": 100.0 * (av + bv) / float(a.volume),
    }


def pad():
    z0 = mod.SOLDER_TOP_Z_MM
    z1 = mod.SOLDER_PAD_Z_MAX_MM
    pts = [
        (4.54488778941404, 3.76578476453536, z0),
        (7.210189558447279, 3.7479184533604792, z0),
        (7.21019340060459, 6.41087029507891, z0),
        (4.54488778941404, 6.41087029507891, z0),
    ]
    edges = [Edge.make_line(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    wire = Wire.combine(edges, tol=1e-7)[0]
    return shape_single(extrude(Face(wire), z1 - z0, dir=(0, 0, 1)), "pad")


def select_terminal_edges(raw):
    x_end = mod.SOLDER_X_START_MM + 2.0
    records = [edge_record(i, e) for i, e in enumerate(raw.edges())]
    terminal = []
    terminal_top = []
    for i, e in enumerate(raw.edges()):
        b = e.bounding_box()
        on_end = abs(b.min.X - x_end) < 1e-5 and abs(b.max.X - x_end) < 1e-5
        if not on_end:
            continue
        if abs(e.length - 2.358727341038) < 1e-3:
            terminal_top.append((i, e))
        else:
            terminal.append((i, e))
    return records, terminal, terminal_top


def select_top_edges(rolled):
    selected = []
    records = []
    for i, e in enumerate(rolled.edges()):
        rec = edge_record(i, e)
        b = e.bounding_box()
        records.append(rec)
        if (
            abs(b.min.Z - mod.SOLDER_TOP_Z_MM) < 5e-5
            and abs(b.max.Z - mod.SOLDER_TOP_Z_MM) < 5e-5
            and b.max.X > mod.SOLDER_X_START_MM + 1.9
            and b.min.X > mod.SOLDER_TAPER_START_X_MM - 2e-4
        ):
            selected.append((i, e))
    return records, selected


def build_candidate(name, terminal_selector="all_profile", junction=True, fuse_pad=True):
    base_profile = Face(mod._solder_profile_wire(mod.SOLDER_X_START_MM))
    raw = shape_single(extrude(base_profile, 2.0, dir=(1, 0, 0)), "raw extrusion")
    raw_records, terminal, terminal_top = select_terminal_edges(raw)
    if terminal_selector == "all_profile":
        chosen = terminal
    elif terminal_selector == "lower_only":
        chosen = [(i, e) for i, e in terminal if e.bounding_box().min.Z < 1.749]
    elif terminal_selector == "single_longest":
        chosen = [max(terminal, key=lambda pair: pair[1].length)]
    else:
        raise ValueError(terminal_selector)
    rolled = shape_single(fillet([e for _, e in chosen], 0.375), "R0.375 terminal roll")
    rolled_records, top_edges = select_top_edges(rolled)
    formed = rolled
    if junction:
        formed = shape_single(fillet([e for _, e in top_edges], 0.07), "R0.07 junction round")
    final = formed.fuse(pad()).clean() if fuse_pad else formed
    final = shape_single(final, "final joint")
    return final, {
        "name": name,
        "raw": metrics(raw),
        "terminal_edge_indices": [i for i, _ in terminal],
        "terminal_top_indices": [i for i, _ in terminal_top],
        "chosen_terminal_indices": [i for i, _ in chosen],
        "raw_edges": raw_records,
        "rolled": metrics(rolled),
        "rolled_edges": rolled_records,
        "junction_edge_indices": [i for i, _ in top_edges],
        "formed": metrics(formed),
        "final": metrics(final),
    }


def main():
    reference_all = import_step(REFERENCE)
    reference_candidates = [s for s in reference_all.solids() if 1.0 < s.volume < 3.0 and s.center_of_mass.X > 0]
    if len(reference_candidates) != 1:
        raise RuntimeError(f"reference right solder selection found {len(reference_candidates)}")
    reference = reference_candidates[0]
    report = {"reference": metrics(reference), "candidates": []}
    variants = [
        ("all_profile_roll_and_junction", "all_profile", True),
        ("all_profile_roll_only", "all_profile", False),
        ("lower_profile_roll_and_junction", "lower_only", True),
        ("single_longest_roll_and_junction", "single_longest", True),
    ]
    for name, selector, junction in variants:
        entry = {"name": name}
        try:
            candidate, details = build_candidate(name, selector, junction, True)
            export_step(candidate, OUT / f"{name}.step")
            export_stl(candidate, OUT / f"{name}.stl", tolerance=0.01, angular_tolerance=0.05, ascii_format=True)
            entry.update(details)
            try:
                entry["exact_xor"] = exact_xor(reference, candidate)
            except Exception as exc:
                entry["exact_xor_error"] = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            entry["traceback"] = traceback.format_exc()
        report["candidates"].append(entry)
        (OUT / "search_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
