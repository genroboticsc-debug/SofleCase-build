#!/usr/bin/env python3
"""Keep the authored offset controller wall until the exact terrace is recovered."""
from pathlib import Path
path=Path(__file__).with_name('dilemma_tenting_puck_family.py')
s=path.read_text()
old='''    lower_face=native_controller_cavity_face_exact(
        Face(raw_offset_wire(p.perimeter_clearance-p.wall_thickness))
    )
'''
new='''    lower_face=Face(
        raw_offset_wire(p.perimeter_clearance-p.wall_thickness)
    )
'''
if old not in s:
    raise RuntimeError('expected lower-face controller replacement not found')
path.write_text(s.replace(old,new,1))
print('kept authored offset controller wall for diagnostic baseline')
