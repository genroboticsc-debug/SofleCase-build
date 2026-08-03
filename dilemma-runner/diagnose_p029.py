from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import traceback

from build123d import Face, Location, Shell, Solid, Wire

root = Path(__file__).resolve().parent / 'project'
script = root / 'scripts' / 'dilemma_4x6_4_hotswap_mid.py'
spec = importlib.util.spec_from_file_location('p029', script)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

p = mod.P029UpperParameters()
path = mod.upper_branch_path(p)
bo = mod._oriented_open_offset(path, p.lower_outer_inset).moved(Location((0,0,p.draft_break_y)))
to = mod._oriented_open_offset(path, p.top_outer_inset).moved(Location((0,0,p.top_y)))
bi = mod._oriented_open_offset(path, p.inner_inset).moved(Location((0,0,p.draft_break_y)))
ti = mod._oriented_open_offset(path, p.inner_inset).moved(Location((0,0,p.top_y)))
bottom = mod._branch_band_face(bo, bi)
top = mod._branch_band_face(to, ti)

print('P029 upper path edges', len(path.edges()), 'length', path.length)
for name, wire in [('bo',bo),('to',to),('bi',bi),('ti',ti)]:
    print(name, 'edges', len(wire.edges()), 'length', wire.length,
          'start', wire.start_point(), 'end', wire.end_point(), 'valid', wire.is_valid)
print('bottom band edges', len(bottom.outer_wire().edges()), 'area', bottom.area)
print('top band edges', len(top.outer_wire().edges()), 'area', top.area)

for ruled in (True, False):
    try:
        solid = Solid.make_loft((bottom.outer_wire(), top.outer_wire()), ruled=ruled)
        print('full loft ruled=', ruled, 'valid', solid.is_valid, 'solids', len(solid.solids()), 'volume', solid.volume)
    except Exception as exc:
        print('full loft ruled=', ruled, 'FAILED', type(exc).__name__, exc)

try:
    solid = mod.sweep_exact_upper_branch(path, p, 'upper diagnostic')
    print('sweep valid', solid.is_valid, 'solids', len(solid.solids()), 'volume', solid.volume)
except Exception as exc:
    print('sweep FAILED', type(exc).__name__, exc)

try:
    outer_side = Face.make_surface_from_curves(bo, to)
    inner_side = Face.make_surface_from_curves(bi, ti)
    print('outer side', type(outer_side).__name__, 'faces', len(outer_side.faces()), 'valid', outer_side.is_valid)
    print('inner side', type(inner_side).__name__, 'faces', len(inner_side.faces()), 'valid', inner_side.is_valid)

    def quad(a, b, c, d):
        return Face(Wire.make_polygon([a,b,c,d], close=True))

    start_face = quad(bo.start_point(), bi.start_point(), ti.start_point(), to.start_point())
    end_face = quad(bo.end_point(), to.end_point(), ti.end_point(), bi.end_point())
    faces = [bottom, top]
    faces.extend(outer_side.faces())
    faces.extend(inner_side.faces())
    faces.extend([start_face, end_face])
    print('manual input faces', len(faces), 'all valid', all(f.is_valid for f in faces))
    sewn = Face.sew_faces(faces)
    print('sewn groups', len(sewn), [len(group) for group in sewn])
    for idx, group in enumerate(sewn):
        try:
            shell = Shell(group)
            solid = Solid(shell).fix()
            print('manual group', idx, 'shell closed', shell.is_closed, 'solid valid', solid.is_valid,
                  'solids', len(solid.solids()), 'volume', solid.volume)
        except Exception as exc:
            print('manual group', idx, 'FAILED', type(exc).__name__, exc)
except Exception as exc:
    print('manual shell FAILED', type(exc).__name__, exc)
    traceback.print_exc()
