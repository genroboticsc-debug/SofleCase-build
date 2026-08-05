from __future__ import annotations

import hashlib
import importlib.util
import sys
import traceback
from pathlib import Path

from build123d import Compound, Edge, Face, Side, Wire, export_step, import_step

ROOT=Path(__file__).resolve().parent
SCRIPT=ROOT/'scripts'/'components'/'kailh cherry socket soldered.py'
REFERENCE=ROOT/'reference.step'
OUT=ROOT/'output'; OUT.mkdir(exist_ok=True)
R=.375
EXPECTED='0b938e39f0fd84a6b424ef9c49f2c6aa8a232fa2a68f9105a0f9b821c987cc56'

spec=importlib.util.spec_from_file_location('kailh_mod',SCRIPT); mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)

def wires_of(obj):
 if obj is None:return []
 if isinstance(obj,Wire):return [obj]
 try:
  ws=list(obj.wires())
  if ws:return ws
 except Exception:pass
 try:return list(obj)
 except Exception:return []

def info(tag,w,refs):
 bb=w.bounding_box(optimal=True)
 print(tag,'length',w.length,'edges',len(w.edges()),'valid',w.is_valid(),'closed',w.is_closed,'bbox',bb.min.to_tuple(),bb.max.to_tuple())
 for i,e in enumerate(w.edges()):
  eb=e.bounding_box(optimal=True)
  ds=[]
  for r in refs:
   try:ds.append(e.distance_to(r))
   except Exception:pass
  d=min(ds) if ds else None
  if d is not None and d<.15:
   print(' CLOSE',i,e.geom_type.name,e.length,e.start_point().to_tuple(),e.end_point().to_tuple(),eb.min.to_tuple(),eb.max.to_tuple(),'d',d)

def main():
 if hashlib.sha256(REFERENCE.read_bytes()).hexdigest()!=EXPECTED:raise RuntimeError('sha')
 model=import_step(REFERENCE)
 ref=[s for s in model.solids() if 1.7<s.volume<1.9 and s.bounding_box(optimal=True).min.X>0][0]
 xend=mod.SOLDER_TAPER_START_X_MM+R
 refs=[]
 for e in ref.edges():
  bb=e.bounding_box(optimal=True)
  if bb.min.X>6.93 and bb.max.X<xend+8e-4 and bb.max.Z<1.76 and e.length>1e-5:refs.append(e)
 print('REFS',len(refs),[(e.length,e.start_point().to_tuple(),e.end_point().to_tuple()) for e in refs])
 export_step(Compound(children=refs),OUT/'ref_terminal.step')

 x=mod.SOLDER_TAPER_START_X_MM
 closed=mod._solder_profile_wire(x)
 face=Face(closed)
 print('SOURCE','area',face.area,'wire_length',closed.length,'orientation',closed.is_forward)
 for side in (Side.LEFT,Side.RIGHT):
  for close_arg in (False,True):
   tag=f'closedwire_{side.name.lower()}_{close_arg}'
   try:
    obj=closed.offset_2d(R,side=side,closed=close_arg)
    ws=wires_of(obj)
    print('RESULT',tag,type(obj).__name__,len(ws))
    for j,w in enumerate(ws):
     moved=w.translate((R,0,0));info(tag+f'_{j}',moved,refs);export_step(moved,OUT/f'{tag}_{j}.step')
   except Exception as exc:print('FAIL',tag,repr(exc))

 for distance in (-R,R):
  tag=f'face_offset_{distance:+.3f}'
  for method in ('offset_2d','offset'):
   fn=getattr(face,method,None)
   if fn is None:continue
   try:
    obj=fn(distance)
    ws=wires_of(obj)
    print('RESULT',tag,method,type(obj).__name__,len(ws))
    for j,w in enumerate(ws):
     moved=w.translate((R,0,0));info(tag+f'_{method}_{j}',moved,refs);export_step(moved,OUT/f'{tag}_{method}_{j}.step')
   except Exception as exc:print('FAIL',tag,method,repr(exc))

if __name__=='__main__':
 try:main()
 except Exception:traceback.print_exc();raise
