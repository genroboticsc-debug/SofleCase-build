from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from build123d import Axis, Edge, Face, Wire, export_step, export_stl, extrude, import_dxf

EXPECTED_GIT_BLOB_SHA1 = "ee1d16cfa34f71b3e2e434c5fba1ac9b40346945"
Y_MIN_MM = -5.85


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def closed_wire_from_edge(edge: Edge) -> Wire:
    wire = Wire([edge])
    if not wire.is_closed:
        raise RuntimeError("Expected closed historical spline edge")
    return wire


def build(dxf_path: Path, thickness_mm: float):
    if abs(thickness_mm - 3.0) > 1.0e-12:
        raise ValueError("Historical official model thickness is exactly 3.000 mm")
    data = dxf_path.read_bytes()
    actual_blob = git_blob_sha1(data)
    if actual_blob != EXPECTED_GIT_BLOB_SHA1:
        raise RuntimeError(f"Historical DXF Git blob mismatch: {actual_blob}")

    imported = import_dxf(dxf_path)
    closed_wires: list[Wire] = []
    open_edges: list[Edge] = []
    for obj in imported:
        if isinstance(obj, Wire):
            if obj.is_closed:
                closed_wires.append(obj)
            else:
                open_edges.extend(obj.edges())
        elif isinstance(obj, Edge):
            if obj.is_closed:
                closed_wires.append(closed_wire_from_edge(obj))
            else:
                open_edges.append(obj)
        else:
            raise RuntimeError(f"Unexpected historical DXF object type: {type(obj).__name__}")

    if open_edges:
        combined = Wire.combine(open_edges)
        if not combined:
            raise RuntimeError("Historical open entities produced no connected wire chains")
        non_closed = [wire for wire in combined if not wire.is_closed]
        if non_closed:
            details = [(len(wire.edges()), float(wire.length)) for wire in non_closed]
            raise RuntimeError(f"Historical edge chains are not closed: {details}")
        closed_wires.extend(combined)

    if len(closed_wires) != 9:
        details = [(len(w.edges()), bool(w.is_closed), float(Face(w).area)) for w in closed_wires]
        raise RuntimeError(f"Expected 9 historical closed loops, got {len(closed_wires)}: {details}")

    loop_areas = [(float(Face(wire).area), wire) for wire in closed_wires]
    loop_areas.sort(key=lambda item: item[0], reverse=True)
    outer_area, outer_wire = loop_areas[0]
    inner_wires = [wire for _, wire in loop_areas[1:]]
    inner_areas = [area for area, _ in loop_areas[1:]]
    if not (outer_area > 10000.0 and inner_areas[0] > 5000.0):
        raise RuntimeError(f"Historical loop hierarchy unexpected: outer={outer_area}, inners={inner_areas}")

    profile = Face(outer_wire, inner_wires)
    if not profile.is_valid:
        raise RuntimeError("Historical direct-DXF profile is invalid")
    body = extrude(profile, amount=thickness_mm)
    body = body.rotate(Axis.X, -90.0).translate((0.0, Y_MIN_MM, 0.0))
    if len(body.solids()) != 1 or not body.is_valid:
        raise RuntimeError("Historical direct-DXF extrusion is not one valid solid")
    return body, outer_area, inner_areas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dxf", type=Path, required=True)
    parser.add_argument("--thickness", type=float, default=3.0)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    body, outer_area, inner_areas = build(args.dxf, args.thickness)
    export_step(body, str(args.out_dir / "midplate_reference.step"))
    export_stl(body, str(args.out_dir / "midplate_reference.stl"), tolerance=1.0e-5, angular_tolerance=0.01)
    print(f"HISTORICAL_OUTER_AREA_MM2={outer_area:.15g}")
    print("HISTORICAL_INNER_AREAS_MM2=" + ",".join(f"{value:.15g}" for value in inner_areas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
