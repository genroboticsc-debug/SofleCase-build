from __future__ import annotations
import importlib.util, math, sys, traceback
from pathlib import Path
from build123d import Edge, Face, Wire, extrude, export_step, fillet
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.Geom import Geom_BSplineCurve
from OCP.TColgp import TColgp_Array1OfPnt
from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
from OCP.gp import gp_Pnt

ROOT=Path(__file__).resolve().parent
SCRIPT=ROOT/'scripts'/'components'/'kailh cherry socket soldered.py'
OUT=ROOT/'output'; OUT.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('kailh_mod',SCRIPT); mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)

def summary(name,s):
 print(name,'valid=',s.is_valid(),'solids=',len(s.solids()),'faces=',len(s.faces()),'edges=',len(s.edges()),'volume=',s.volume,'area=',s.area)
 bb=s.bounding_box(optimal=True); print(' bbox',bb.min.to_tuple(),bb.max.to_tuple())

def norm(a,b): return math.hypot(b[0]-a[0],b[1]-a[1])

def pair_edge(span_a,span_b,x):
 ratio=norm(span_b[0],span_b[1])/norm(span_a[2],span_a[3])
 vals=[span_a[0],span_a[1],span_a[2],span_a[3],span_b[1],span_b[2],span_b[3]]
 poles=TColgp_Array1OfPnt(1,7)
 for i,(y,z) in enumerate(vals,1): poles.SetValue(i,gp_Pnt(x,y,z))
 knots=TColStd_Array1OfReal(1,3); mults=TColStd_Array1OfInteger(1,3)
 for i,v in enumerate((0.0,1.0,1.0+ratio),1): knots.SetValue(i,v)
 for i,m in enumerate((4,3,4),1): mults.SetValue(i,m)
 curve=Geom_BSplineCurve(poles,knots,mults,3,False)
 ok=curve.RemoveKnot(2,2,1e-9)
 print('PAIR','ratio',ratio,'remove',ok,'continuity',curve.Continuity(),'poles',curve.NbPoles())
 maker=BRepBuilderAPI_MakeEdge(curve)
 if not maker.IsDone(): raise RuntimeError('edge failed')
 return Edge(maker.Edge())

def max_radius(raw,edges,upper=.375):
 lo,hi=0.,upper; best=None
 for _ in range(18):
  mid=(lo+hi)/2
  try: best=fillet(edges,mid); lo=mid
  except Exception: hi=mid
 return lo,best

def run_grouping(groups,tag):
 x=mod.SOLDER_X_START_MM; spans=mod.SOLDER_PROFILE_BEZIER_SPANS_YZ
 edges=[]
 for g in groups:
  if len(g)!=2: raise RuntimeError('only pairs')
  edges.append(pair_edge(spans[g[0]],spans[g[1]],x))
 edges.append(Edge.make_line(edges[-1].end_point(),edges[0].start_point()))
 wires=Wire.combine(edges,tol=mod.WIRE_JOIN_TOLERANCE_MM); print(tag,'wire_count',len(wires),'edge_lengths',[e.length for e in edges])
 raw=extrude(Face(wires[0]),2.0,dir=(1,0,0)); summary('RAW_'+tag,raw); export_step(raw,OUT/f'raw_{tag}.step')
 xmax=raw.bounding_box(optimal=True).max.X
 terminal=[e for e in raw.edges() if all(abs(v.X-xmax)<1e-6 for v in e.vertices())]
 curved=[e for e in terminal if e.geom_type.name!='LINE']
 print(tag,'terminal',[(e.geom_type.name,e.length) for e in terminal])
 try:
  rolled=fillet(curved,.375); summary('ROLLED_'+tag,rolled); export_step(rolled,OUT/f'rolled_{tag}.step')
 except Exception as exc:
  print('FILLET_FAIL',tag,repr(exc)); r,best=max_radius(raw,curved); print('MAX_RADIUS',tag,r)
  if best is not None and r>.01: export_step(best,OUT/f'maxfillet_{tag}.step')

def main():
 original=extrude(Face(mod._solder_profile_wire(mod.SOLDER_X_START_MM)),2.0,dir=(1,0,0)); summary('ORIGINAL',original)
 run_grouping([(0,1),(2,3),(4,5),(6,7),(8,9)],'pairs_01_23_45_67_89')

if __name__=='__main__':
 try: main()
 except Exception: traceback.print_exc(); raise
