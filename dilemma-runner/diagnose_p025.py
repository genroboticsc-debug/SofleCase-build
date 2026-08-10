from __future__ import annotations
import importlib.util
from pathlib import Path
import sys

from build123d import Face, Plane, Wire

root = Path(__file__).resolve().parent / 'project'
script = root / 'scripts' / 'dilemma_4x6_4_top.py'
spec = importlib.util.spec_from_file_location('p025', script)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

p = mod.TopCaseParameters()
profile = mod.perimeter_wall_face(p.support_wall_width)
controller_cluster = Face(mod.controller_frame_face().outer_wire())
for index in (0, 7, 8):
    controller_cluster = controller_cluster.fuse(mod.polygon_face(mod.MIDDLE_SUPPORT_PROFILES[index])).faces()[0]
profile = profile.fuse(controller_cluster).faces()[0]
for index, points in enumerate(mod.MIDDLE_SUPPORT_PROFILES):
    if index in (0, 7, 8):
        continue
    profile = profile.fuse(mod.polygon_face(points)).faces()[0]
for index, points in enumerate(mod.COMMON_RETENTION_PROFILES[:10]):
    profile = profile.fuse(mod.polygon_face(points)).faces()[0]

points = mod.COMMON_RETENTION_PROFILES[10]
rib = mod.polygon_face(points)
print('P025 parent before rib10 area', profile.area, 'edges', len(profile.edges()), 'wires', len(profile.wires()))
print('P025 rib10 points', points, 'area', rib.area, 'edges', len(rib.edges()))
try:
    distance, p_parent, p_rib = profile.distance_to_with_closest_points(rib)
    print('face distance', distance, 'parent point', p_parent, 'rib point', p_rib)
except Exception as exc:
    print('face distance FAILED', type(exc).__name__, exc)

for i, vertex in enumerate(rib.vertices()):
    try:
        d, p_parent, p_vertex = profile.distance_to_with_closest_points(vertex)
        print('rib vertex', i, tuple(vertex.to_tuple()), 'distance', d, 'parent point', p_parent)
    except Exception as exc:
        print('rib vertex', i, 'distance FAILED', type(exc).__name__, exc)

for i, edge in enumerate(rib.edges()):
    try:
        d, p_parent, p_edge = profile.distance_to_with_closest_points(edge)
        print('rib edge', i, 'start', edge.start_point(), 'end', edge.end_point(), 'distance', d,
              'parent point', p_parent, 'edge point', p_edge)
    except Exception as exc:
        print('rib edge', i, 'distance FAILED', type(exc).__name__, exc)

for include_touched in (False, True):
    try:
        common = profile.intersect(rib, tolerance=1e-9, include_touched=include_touched)
        if common is None:
            print('intersection touched=', include_touched, 'NONE')
        else:
            expanded = list(common.expand()) if hasattr(common, 'expand') else list(common)
            print('intersection touched=', include_touched, 'count', len(expanded),
                  [(type(x).__name__, getattr(x, 'area', None), getattr(x, 'length', None)) for x in expanded])
    except Exception as exc:
        print('intersection touched=', include_touched, 'FAILED', type(exc).__name__, exc)

try:
    fused = profile.fuse(rib)
    print('fuse result faces', len(fused.faces()), 'valid', fused.is_valid,
          'areas', [face.area for face in fused.faces()])
except Exception as exc:
    print('fuse FAILED', type(exc).__name__, exc)

# Find the exact nearest parent boundary edge to every rib endpoint.
parent_edges = list(profile.edges())
for i, (x, y) in enumerate(points):
    point = mod.Vector(x, y, 0.0)
    ranked = []
    for j, edge in enumerate(parent_edges):
        try:
            d = edge.distance_to(point)
            ranked.append((d, j, edge.start_point(), edge.end_point(), edge.geom_type))
        except Exception:
            pass
    ranked.sort(key=lambda row: row[0])
    print('point', i, (x,y), 'nearest parent edges', ranked[:5])
