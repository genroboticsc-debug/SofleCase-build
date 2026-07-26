from __future__ import annotations

import json
import traceback
from pathlib import Path

from build123d import CenterOf, Edge, Face, Wire, export_step, export_stl, extrude, fillet, import_step

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "kailh_reference.step"
OUT = ROOT / "results"
OUT.mkdir(exist_ok=True)

X0 = 5.010191487800
X_RAW_END = X0 + 2.0
X_ROLL_START = X_RAW_END - 0.375
PROFILE_CENTER_Y = 5.085130767564
TOP_Z = 1.75
PAD_Z1 = 1.80
PROFILE_SPANS = (
    ((6.26449438808344, 1.75), (6.037652643286782, 1.7464977207059593), (5.948216212731957, 1.1627540082312793), (5.931167511145697, 0.9908398685910332)),
    ((5.931167511145697, 0.9908398685910332), (5.927754127720061, 0.9564203046194658), (5.922888677847069, 0.7445394664677538), (5.9056168509451865, 0.7353586477870302)),
    ((5.9056168509451865, 0.7353586477870302), (5.880620638817342, 0.7220719414904516), (5.853618519895407, 0.842675012490237), (5.847148297690575, 0.8600319632961385)),
    ((5.847148297690575, 0.8600319632961385), (5.816949601881485, 0.9410426706516545), (5.774807438674499, 1.0176881094435422), (5.727176591347377, 1.0896800429967701)),
    ((5.727176591347377, 1.0896800429967701), (5.581540119368333, 1.3098031733210076), (5.34929696093493, 1.5421574803805749), (5.070910946871318, 1.561888982007823)),
    ((5.070910946871318, 1.561888982007823), (4.750995222704022, 1.5845640350388521), (4.5310337517931325, 1.291336161578472), (4.409299950016339, 1.0327790431952582)),
    ((4.409299950016339, 1.0327790431952582), (4.390241682529478, 0.9923001404512655), (4.2790421668386305, 0.6963848252000207), (4.268512060541968, 0.6942119954420493)),
    ((4.268512060541968, 0.6942119954420493), (4.2637523122493635, 0.6932298474523463), (4.259899087895539, 0.6960508690099316), (4.256802438167436, 0.6992378869858319)),
    ((4.256802438167436, 0.6992378869858319), (4.235761897724996, 0.7208924448146236), (4.239333497876836, 0.9743776290012744), (4.234772130300953, 1.0251152351594182)),
    ((4.234772130300953, 1.0251152351594182), (4.216801197009745, 1.2250118934432974), (4.175010164179821, 1.7476386118392202), (3.90576714704497, 1.75)),
)


def closed_wire(edges):
    wires = Wire.combine(edges, tol=1e-7)
    if len(wires) != 1:
        raise RuntimeError(f"expected one wire, got {len(wires)}")
    return wires[0]


def profile_wire(x):
    def p(yz):
        return (x, yz[0], yz[1])
    edges = [Edge.make_bezier(*(p(point) for point in span)) for span in PROFILE_SPANS]
    edges.append(Edge.make_line(p(PROFILE_SPANS[-1][-1]), p(PROFILE_SPANS[0][0])))
    return closed_wire(edges)


def shape_single(shape, label):
    solids = shape.solids()
    if len(solids) != 1:
        raise RuntimeError(f"{label}: expected one solid, got {len(solids)}")
    solid = solids[0]
    if not solid.is_valid:
        raise RuntimeError(f"{label}: invalid solid")
    return solid


def metrics(shape):
    b = shape.bounding_box()
    c = shape.center(CenterOf.MASS)
    return {
        "valid": bool(shape.is_valid), "volume": float(shape.volume), "area": float(shape.area),
        "bbox": [b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z],
        "com": [c.X, c.Y, c.Z], "solids": len(shape.solids()),
        "faces": len(shape.faces()), "edges": len(shape.edges()),
    }


def edge_record(i, edge):
    b = edge.bounding_box()
    return {
        "index": i, "length": edge.length,
        "bbox": [b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z],
        "start": list(edge.position_at(0)), "end": list(edge.position_at(1)),
    }


def exact_xor(a, b):
    am = a.cut(b)
    bm = b.cut(a)
    av, bv = float(am.volume), float(bm.volume)
    return {"a_minus_b": av, "b_minus_a": bv, "xor_volume": av + bv,
            "xor_pct": 100.0 * (av + bv) / float(a.volume)}


def wetting_pad():
    pts = [
        (4.54488778941404, 3.76578476453536, TOP_Z),
        (7.210189558447279, 3.7479184533604792, TOP_Z),
        (7.21019340060459, 6.41087029507891, TOP_Z),
        (4.54488778941404, 6.41087029507891, TOP_Z),
    ]
    wire = closed_wire([Edge.make_line(pts[i], pts[(i + 1) % 4]) for i in range(4)])
    return shape_single(extrude(Face(wire), PAD_Z1 - TOP_Z, dir=(0, 0, 1)), "pad")


def terminal_edges(raw):
    result, top = [], []
    records = [edge_record(i, e) for i, e in enumerate(raw.edges())]
    for i, edge in enumerate(raw.edges()):
        b = edge.bounding_box()
        if abs(b.min.X - X_RAW_END) > 1e-5 or abs(b.max.X - X_RAW_END) > 1e-5:
            continue
        if abs(edge.length - 2.358727341038) < 1e-3:
            top.append((i, edge))
        else:
            result.append((i, edge))
    return records, result, top


def junction_edges(rolled):
    selected = []
    records = [edge_record(i, e) for i, e in enumerate(rolled.edges())]
    for i, edge in enumerate(rolled.edges()):
        b = edge.bounding_box()
        if (abs(b.min.Z - TOP_Z) < 5e-5 and abs(b.max.Z - TOP_Z) < 5e-5
                and b.min.X > X_ROLL_START - 2e-4 and b.max.X > X_RAW_END - 0.1):
            selected.append((i, edge))
    return records, selected


def candidate(selector, apply_junction):
    raw = shape_single(extrude(Face(profile_wire(X0)), 2.0, dir=(1, 0, 0)), "raw")
    raw_records, all_terminal, top_terminal = terminal_edges(raw)
    if selector == "all":
        selected = all_terminal
    elif selector == "lower":
        selected = [(i, e) for i, e in all_terminal if e.bounding_box().min.Z < TOP_Z - 1e-4]
    elif selector == "longest":
        selected = [max(all_terminal, key=lambda item: item[1].length)]
    else:
        raise ValueError(selector)
    rolled = shape_single(fillet([e for _, e in selected], 0.375), "terminal R0.375")
    rolled_records, top_edges = junction_edges(rolled)
    formed = shape_single(fillet([e for _, e in top_edges], 0.07), "junction R0.07") if apply_junction else rolled
    final = shape_single(formed.fuse(wetting_pad()).clean(), "final")
    return final, {
        "raw": metrics(raw), "raw_edges": raw_records,
        "terminal_all": [i for i, _ in all_terminal], "terminal_top": [i for i, _ in top_terminal],
        "terminal_selected": [i for i, _ in selected], "rolled": metrics(rolled),
        "rolled_edges": rolled_records, "junction_selected": [i for i, _ in top_edges],
        "formed": metrics(formed), "final": metrics(final),
    }


def main():
    ref_all = import_step(REFERENCE)
    refs = [s for s in ref_all.solids() if 1.0 < s.volume < 3.0 and s.center(CenterOf.MASS).X > 0]
    if len(refs) != 1:
        raise RuntimeError(f"right reference solder count={len(refs)}")
    ref = refs[0]
    report = {"reference": metrics(ref), "candidates": []}
    for name, selector, junction in [
        ("all_roll_junction", "all", True), ("all_roll_only", "all", False),
        ("lower_roll_junction", "lower", True), ("longest_roll_junction", "longest", True),
    ]:
        row = {"name": name}
        try:
            solid, details = candidate(selector, junction)
            row.update(details)
            row["exact_xor"] = exact_xor(ref, solid)
            export_step(solid, OUT / f"{name}.step")
            export_stl(solid, OUT / f"{name}.stl", tolerance=0.01, angular_tolerance=0.05, ascii_format=True)
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            row["traceback"] = traceback.format_exc()
        report["candidates"].append(row)
        (OUT / "search_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
