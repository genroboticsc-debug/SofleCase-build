from __future__ import annotations

"""Kailh socket solder-joint feature test.

This is a standalone Build123d analysis builder. It reconstructs one solder joint
from compact design curves and native engineering features only. It does not
load the reference geometry.
"""

import json
from pathlib import Path

from build123d import Edge, Face, Solid, Wire, export_step, export_stl, extrude

JOIN_TOL = 1.0e-7
X_START = 5.010191487800
UNFILLETED_END_X = 7.010191487800
MAIN_ROLL_RADIUS = 0.375
TOP_BLEND_RADIUS = 0.070
TOP_Z = 1.750
PAD_Z_MAX = 1.800

PAD_XY = (
    (4.54488778941404, 3.76578476453536),
    (4.54488778941404, 6.41087029507891),
    (7.21019340060459, 6.41087029507891),
    (7.210189558447279, 3.7479184533604792),
)

PROFILE_SPANS_YZ = (
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


def closed_wire(edges: list[Edge]) -> Wire:
    wires = Wire.combine(edges, tol=JOIN_TOL)
    if len(wires) != 1:
        raise RuntimeError(f"expected one wire, got {len(wires)}")
    return wires[0]


def profile_wire(x: float) -> Wire:
    edges = [Edge.make_bezier(*((x, y, z) for y, z in span)) for span in PROFILE_SPANS_YZ]
    first = PROFILE_SPANS_YZ[0][0]
    last = PROFILE_SPANS_YZ[-1][-1]
    edges.append(Edge.make_line((x, last[0], last[1]), (x, first[0], first[1])))
    return closed_wire(edges)


def pad_face() -> Face:
    points = [(x, y, TOP_Z) for x, y in PAD_XY]
    edges = [Edge.make_line(points[i], points[(i + 1) % len(points)]) for i in range(len(points))]
    return Face(closed_wire(edges))


def _resolved(value):
    return value() if callable(value) else value


def geom_type_name(edge: Edge) -> str:
    return str(_resolved(edge.geom_type)).lower()


def edge_length(edge: Edge) -> float:
    return float(_resolved(edge.length))


def edge_record(edge: Edge) -> dict:
    bb = edge.bounding_box()
    return {
        "geom_type": geom_type_name(edge),
        "length": edge_length(edge),
        "bbox": [bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z],
    }


def build_joint() -> tuple[Solid, dict]:
    profile = Face(profile_wire(X_START))
    raw = extrude(profile, UNFILLETED_END_X - X_START, dir=(1, 0, 0))

    terminal_edges = []
    terminal_all = []
    for edge in raw.edges():
        bb = edge.bounding_box()
        if abs(bb.min.X - UNFILLETED_END_X) < 1.0e-6 and abs(bb.max.X - UNFILLETED_END_X) < 1.0e-6:
            terminal_all.append(edge)
            if "line" not in geom_type_name(edge):
                terminal_edges.append(edge)

    debug = {
        "raw_valid": raw.is_valid,
        "raw_volume": raw.volume,
        "terminal_edge_count": len(terminal_edges),
        "terminal_all_count": len(terminal_all),
        "terminal_edges": [edge_record(e) for e in terminal_all],
    }
    if not terminal_edges:
        raise RuntimeError("no curved terminal edges selected")

    rolled = raw.fillet(MAIN_ROLL_RADIUS, terminal_edges)
    debug.update({
        "main_fillet_valid": rolled.is_valid,
        "main_fillet_volume": rolled.volume,
        "main_fillet_faces": len(rolled.faces()),
    })

    pad = extrude(pad_face(), PAD_Z_MAX - TOP_Z, dir=(0, 0, 1))
    joint = rolled.fuse(pad).clean()
    debug.update({
        "pad_volume": pad.volume,
        "joint_valid": joint.is_valid,
        "joint_volume": joint.volume,
        "joint_area": joint.area,
        "joint_faces": len(joint.faces()),
        "joint_solids": len(joint.solids()),
    })
    if not joint.is_valid or len(joint.solids()) != 1:
        raise RuntimeError("invalid fused joint")
    return joint, debug


def main() -> None:
    out = Path("artifacts")
    out.mkdir(parents=True, exist_ok=True)
    joint, debug = build_joint()
    export_step(joint, out / "candidate_joint.step")
    export_stl(joint, out / "candidate_joint.stl", tolerance=0.01, angular_tolerance=0.05)
    (out / "candidate_build.json").write_text(json.dumps(debug, indent=2))
    print(json.dumps(debug, indent=2))


if __name__ == "__main__":
    main()
