from __future__ import annotations

import hashlib
import importlib.util
import sys
import traceback
from pathlib import Path

from build123d import Edge, Side, Wire, export_step, import_step

ROOT=Path(__file__).resolve().parent
SCRIPT=ROOT/'scripts'/'components'/'kailh cherry socket soldered.py'
REFERENCE=ROOT/'reference.step'
OUT=ROOT/'output'; OUT.mkdir(exist_ok=True)
R=0.375
EXPECTED='0b938e39f0fd84a6b424ef9c49f2c6aa8a232fa2a68f9105a0f9b821c987cc56'

spec=importlib.util.spec_from_file_location('kailh_mod',SCRIPT); mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)

def edge_info(prefix, edge):
 bb=edge.bounding_box(optimal=True)
 print(prefix,'type',edge.geom_type.name,'len',edge.length,'start',edge.start_point().to_tuple(),'end',edge.end_point().to_tuple(),'bbox',bb.min.to_tuple(),bb.max.to_tuple())

def get_ref():
 if hashlib.sha256(REFERENCE.read_bytes()).hexdigest()!=EXPECTED: raise RuntimeError('sha')
 model=import_step(REFERENCE)
 refs=[s for s in model.solids() if 1.7<s.volume<1.9 and s.bounding_box(optimal=True).min.X>0]
 if len(refs)!=1: raise RuntimeError('ref selection')
 return refs[0]

def source_wire():
 x=mod.SOLDER_TAPER_START_X_MM
 edges=[Edge.make_bezier(*[(x,y,z) for y,z in span]) for span in mod.SOLDER_PROFILE_BEZIER_SPANS_YZ]
 wires=Wire.combine(edges,tol=mod.WIRE_JOIN_TOLERANCE_MM)
 if len(wires)!=1: raise RuntimeError(f'wire count {len(wires)}')
 return wires[0]

def as_wires(obj):
 if obj is None: return []
 if isinstance(obj, Wire): return [obj]
 try:
  ws=list(obj.wires())
  if ws: return ws
 except Exception: pass
 try: return list(obj)
 except Exception: return []

def main():
 ref=get_ref(); xend=mod.SOLDER_TAPER_START_X_MM+R
 print('XEND',xend)
 ref_edges=[]
 for edge in ref.edges():
  bb=edge.bounding_box(optimal=True)
  if abs(bb.min.X-xend)<5e-4 and abs(bb.max.X-xend)<5e-4 and bb.max.Z<1.76:
   ref_edges.append(edge)
 print('REF_TERMINAL_EDGE_COUNT',len(ref_edges))
 for i,e in enumerate(ref_edges): edge_info(f'REF_{i}',e)
 if ref_edges: export_step(Wire.combine(ref_edges,tol=1e-4),OUT/'reference_terminal_edges.step')

 src=source_wire()
 print('SOURCE_LENGTH',src.length,'edges',len(src.edges()))
 for side in (Side.LEFT,Side.RIGHT):
  tag=side.name.lower()
  for closed in (False,True):
   try:
    result=src.offset_2d(R,side=side,closed=closed)
    wires=as_wires(result)
    print('OFFSET',tag,'closed',closed,'object',type(result).__name__,'wire_count',len(wires))
    for wi,w in enumerate(wires):
     moved=w.translate((R,0,0))
     print(' WIRE',wi,'length',w.length,'edges',len(w.edges()),'valid',w.is_valid())
     for ei,e in enumerate(moved.edges()):
      edge_info(f'{tag}_{closed}_{wi}_{ei}',e)
      distances=[]
      for re in ref_edges:
       try: distances.append(e.distance_to(re))
       except Exception: pass
      print('  MIN_REF_DISTANCE',min(distances) if distances else None)
     export_step(moved,OUT/f'offset_{tag}_closed_{closed}_{wi}.step')
   except Exception as exc:
    print('OFFSET_FAIL',tag,closed,repr(exc))

if __name__=='__main__':
 try: main()
 except Exception: traceback.print_exc(); raise
