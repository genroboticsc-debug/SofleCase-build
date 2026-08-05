from __future__ import annotations

from pathlib import Path
import json
import math

import trimesh
from build123d import (
    Align,
    Box,
    Face,
    FontStyle,
    Location,
    Matrix,
    Plane,
    Text,
    Vector,
    Wire,
    export_step,
    export_stl,
    extrude,
    mirror,
)

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "top_fork_windows_results"
OUT.mkdir(exist_ok=True)
REF = ROOT / "AnalyzerBoxTop_fork.STL"

W, D = 56.0, 52.0
PLATE_H = 2.0
POCKET_X0, POCKET_X1 = 4.1, 51.9
POCKET_Y0, POCKET_Y1 = 23.0, 48.0
POCKET_FLOOR = 0.7
P = [
    (53.9, 2.1),
    (53.9, 30.22290788008854),
    (51.9, 30.22290788008854),
    (51.9, 4.1),
    (4.1, 4.1),
    (4.1, 48.0),
    (51.9, 48.0),
    (51.9, 46.18687434223028),
    (53.9, 46.18687434223028),
    (53.9, 50.0),
    (2.1, 50.0),
    (2.1, 2.1),
]
BAR_X0 = 8.82400006111012
BAR_X1 = 47.648297243181194
L1_B = (8.175548553466797, 11.870741844177246, 47.181888580322266, 18.574054718017578)
L2_B = (4.943937301635742, 2.590423345565796, 50.723636627197266, 7.054419994354248)


def prism(points, z0, height, fillet_vertices=None, radius=0.0):
    wire = Wire.make_polygon([Vector(x, y, z0) for x, y in points], close=True)
    face = Face(wire)
    if fillet_vertices:
        selected = []
        for vertex in face.vertices():
            p = vertex.center()
            if any(abs(p.X - x) < 1e-7 and abs(p.Y - y) < 1e-7 for x, y in fillet_vertices):
                selected.append(vertex)
        face = face.fillet_2d(radius, selected)
    return extrude(face, amount=height)


def build_mechanical():
    plate_raw = Box(W, D, PLATE_H + 0.01, align=(Align.MIN, Align.MIN, Align.MIN))
    selected = []
    for edge in plate_raw.edges():
        bb = edge.bounding_box()
        dz = bb.max.Z - bb.min.Z
        if (abs(bb.min.Z) < 1e-9 and abs(bb.max.Z) < 1e-9) or dz > PLATE_H:
            selected.append(edge)
    plate = plate_raw.fillet(2.0, selected)
    plate = plate & Box(W, D, PLATE_H, align=(Align.MIN, Align.MIN, Align.MIN))
    pocket = Box(
        POCKET_X1 - POCKET_X0,
        POCKET_Y1 - POCKET_Y0,
        PLATE_H - POCKET_FLOOR + 0.01,
        align=(Align.MIN, Align.MIN, Align.MIN),
    ).moved(Location((POCKET_X0, POCKET_Y0, POCKET_FLOOR)))
    part = plate - pocket
    part += prism(P, 2.0, 2.0, [(53.9, 2.1), (53.9, 50.0), (2.1, 50.0), (2.1, 2.1)], 2.0)
    part += Box(BAR_X1 - BAR_X0, 4.1, 3.5, align=(Align.MIN, Align.MIN, Align.MIN)).moved(
        Location((BAR_X0, 0.0, 2.0))
    )
    right = Box(1.2, 30.22290788008854 - 4.431020259857178, 0.74, align=(Align.MIN, Align.MIN, Align.MIN)).moved(
        Location((53.9, 4.431020259857178, 3.26))
    )
    right_edges = []
    for edge in right.edges():
        bb = edge.bounding_box()
        if abs(bb.min.X - 55.1) < 1e-7 and abs(bb.max.X - 55.1) < 1e-7 and abs(bb.min.Z - 4.0) < 1e-7 and abs(bb.max.Z - 4.0) < 1e-7:
            right_edges.append(edge)
    right = right.fillet(0.5, right_edges)
    left = Box(1.2, 48.014739990234375 - 4.2407307624816895, 0.7, align=(Align.MIN, Align.MIN, Align.MIN)).moved(
        Location((0.9, 4.2407307624816895, 3.3))
    )
    left_edges = []
    for edge in left.edges():
        bb = edge.bounding_box()
        if abs(bb.min.X - 0.9) < 1e-7 and abs(bb.max.X - 0.9) < 1e-7 and abs(bb.min.Z - 4.0) < 1e-7 and abs(bb.max.Z - 4.0) < 1e-7:
            left_edges.append(edge)
    left = left.fillet(0.5, left_edges)
    return part + right + left


def text_tool(txt, bounds, font, style, width_mode):
    x0, y0, x1, y1 = bounds
    target_w = x1 - x0
    target_h = y1 - y0
    probe = Text(txt, 10.0, font=font, font_style=style)
    size = 10.0 * target_h / probe.bounding_box().size.Y
    sketch = Text(txt, size, font=font, font_style=style)
    if width_mode == "envelope":
        sx = target_w / sketch.bounding_box().size.X
        sketch = sketch.transform_geometry(Matrix([[sx, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]))
    sketch = mirror(sketch, about=Plane.YZ)
    bb = sketch.bounding_box()
    sketch = sketch.moved(
        Location(((x0 + x1) / 2 - (bb.min.X + bb.max.X) / 2, (y0 + y1) / 2 - (bb.min.Y + bb.max.Y) / 2, 0))
    )
    return extrude(sketch, amount=0.01001)


def build(font1, style1, mode1, font2, style2, mode2):
    part = build_mechanical()
    part -= Box(47.8, 25.0, 0.01001, align=(Align.MIN, Align.MIN, Align.MIN)).moved(Location((4.1, 23.0, 0)))
    part -= text_tool("logicAnalyzer", L1_B, font1, style1, mode1)
    part -= text_tool("1-12PIN GND EXT_1", L2_B, font2, style2, mode2)
    if not part.is_valid:
        raise RuntimeError("invalid top-fork body")
    return part


reference = trimesh.load_mesh(REF, process=True)
variants = []
line1 = [("comic_regular", "Comic Sans MS", FontStyle.REGULAR), ("comic_bold", "Comic Sans MS", FontStyle.BOLD)]
line2 = [
    ("century_regular", "Century Gothic", FontStyle.REGULAR),
    ("century_bold", "Century Gothic", FontStyle.BOLD),
    ("arial_regular", "Arial", FontStyle.REGULAR),
    ("arial_bold", "Arial", FontStyle.BOLD),
]
for n1, f1, s1 in line1:
    for n2, f2, s2 in line2:
        for mode1 in ("natural", "envelope"):
            for mode2 in ("natural", "envelope"):
                name = f"{n1}_{mode1}__{n2}_{mode2}"
                print("BUILD", name, flush=True)
                body = build(f1, s1, mode1, f2, s2, mode2)
                stl = OUT / f"{name}.stl"
                export_stl(body, stl, tolerance=1.0, angular_tolerance=0.34)
                generated = trimesh.load_mesh(stl, process=True)
                missing_mesh = trimesh.boolean.difference([reference, generated], engine="manifold", check_volume=False)
                extra_mesh = trimesh.boolean.difference([generated, reference], engine="manifold", check_volume=False)
                missing = abs(missing_mesh.volume) if missing_mesh is not None else 0.0
                extra = abs(extra_mesh.volume) if extra_mesh is not None else 0.0
                pct = (missing + extra) / abs(reference.volume) * 100.0
                row = {
                    "name": name,
                    "font1": f1,
                    "style1": s1.name,
                    "mode1": mode1,
                    "font2": f2,
                    "style2": s2.name,
                    "mode2": mode2,
                    "brep_volume": body.volume,
                    "mesh_volume": generated.volume,
                    "missing_mm3": missing,
                    "extra_mm3": extra,
                    "symmetric_difference_percent": pct,
                    "watertight": bool(generated.is_watertight),
                }
                variants.append(row)
                print(json.dumps(row), flush=True)
variants.sort(key=lambda x: x["symmetric_difference_percent"])
(OUT / "results.json").write_text(json.dumps(variants, indent=2), encoding="utf-8")
best = variants[0]
best_body = build(
    best["font1"], FontStyle[best["style1"]], best["mode1"], best["font2"], FontStyle[best["style2"]], best["mode2"]
)
export_step(best_body, OUT / "BEST.step")
export_stl(best_body, OUT / "BEST.stl", tolerance=1.0, angular_tolerance=0.34)
(OUT / "BEST.json").write_text(json.dumps(best, indent=2), encoding="utf-8")
print("BEST", json.dumps(best), flush=True)
