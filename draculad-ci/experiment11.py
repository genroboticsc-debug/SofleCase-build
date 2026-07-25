from __future__ import annotations

import hashlib
import importlib.util
import sys
import traceback
from pathlib import Path

from build123d import Axis, Compound, Edge, Side, Wire, export_step, import_step

ROOT=Path(__file__).resolve().parent
SCRIPT=ROOT/'scripts'/'components'/'kailh cherry socket soldered.py'
REFERENCE=ROOT/'reference.step'
OUT=ROOT/'output';OUT.mkdir(exist_ok=True)
R=.375
EXPECTED='0b938e39f0fd84a6b424ef9c49f2c6aa8a232fa2a68f9105a0f9b821c987cc56'

spec=importlib.util.spec_from_file_location('kailh_mod',SCRIPT);mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)

def wires_of(obj):
 if obj is None:return []
 if isinstance(obj,Wire):return [obj]
 try:
  ws=list(obj.wires())
  if ws:return ws
 except Exception:pass
 try:return list(obj)
 except Exception:return []

def to_global(w,x):
 return w.rotate(Axis.X,90).rotate(Axis.Z,90).translate((x,0,0))

def local_open():
 edges=[Edge.make_bezier(*[(y,z,0) for y,z in span]) for span in mod.SOLDER_PROFILE_BEZIER_SPANS_YZ]
 ws=Wire.combine(edges,tol=mod.WIRE_JOIN_TOLERANCE_MM)
 if len(ws)!=1:raise RuntimeError(f'open count {len(ws)}')
 return ws[0]

def local_closed():
 op=local_open()
 edges=list(op.edges())+[Edge.make_line(op.end_point(),op.start_point())]
 ws=Wire.combine(edges,tol=mod.WIRE_JOIN_TOLERANCE_MM)
 if len(ws)!=1:raise RuntimeError(f'closed count {len(ws)}')
 return ws[0]

def main():
 if hashlib.sha256(REFERENCE.read_bytes()).hexdigest()!=EXPECTED:raise RuntimeError('sha')
 model=import_step(REFERENCE);ref=[s for s in model.solids() if 1.7<s.volume<1.9 and s.bounding_box(optimal=True).min.X>0][0]
 xend=mod.SOLDER_TAPER_START_X_MM+R
 refs=[]
 for e in ref.edges():
  bb=e.bounding_box(optimal=True)
  if bb.min.X>6.93 and bb.max.X<xend+8e-4 and bb.max.Z<1.76 and e.length>1e-5:refs.append(e)
 print('REFS',len(refs))
 export_step(Compound(children=refs),OUT/'ref_terminal.step')
 for source_name,source in (('open',local_open()),('closed',local_closed())):
  print('SOURCE',source_name,'len',source.length,'edges',len(source.edges()),'closed',source.is_closed,'forward',source.is_forward)
  export_step(to_global(source,mod.SOLDER_TAPER_START_X_MM),OUT/f'source_{source_name}.step')
  for side in (Side.LEFT,Side.RIGHT):
   for closed_arg in (False,True):
    tag=f'{source_name}_{side.name.lower()}_{closed_arg}'
    try:
     obj=source.offset_2d(R,side=side,closed=closed_arg)
     ws=wires_of(obj);print('OFFSET',tag,type(obj).__name__,'wires',len(ws))
     for wi,w in enumerate(ws):
      g=to_global(w,xend);bb=g.bounding_box(optimal=True)
      print(' WIRE',wi,'len',w.length,'edges',len(w.edges()),'valid',w.is_valid(),'closed',w.is_closed,'bbox',bb.min.to_tuple(),bb.max.to_tuple())
      close=[]
      for ei,e in enumerate(g.edges()):
       ds=[]
       for re in refs:
        try:ds.append(e.distance_to(re))
        except Exception:pass
       d=min(ds) if ds else 999
       if d<.1:
        eb=e.bounding_box(optimal=True);close.append((ei,e.geom_type.name,e.length,e.start_point().to_tuple(),e.end_point().to_tuple(),d,eb.min.to_tuple(),eb.max.to_tuple()))
      print(' CLOSE_COUNT',len(close))
      for item in close:print('  CLOSE',item)
      export_step(g,OUT/f'offset_{tag}_{wi}.step')
    except Exception as exc:print('OFFSET_FAIL',tag,repr(exc))

if __name__=='__main__':
 try:main()
 except Exception:traceback.print_exc();raise
