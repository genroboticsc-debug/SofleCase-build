from __future__ import annotations

import hashlib
import importlib.util
import math
import sys
import traceback
from pathlib import Path

from build123d import Compound, Edge, Face, Solid, Vector, Wire, extrude, export_step, import_step

ROOT=Path(__file__).resolve().parent
SCRIPT=ROOT/'scripts'/'components'/'kailh cherry socket soldered.py'
REFERENCE=ROOT/'reference.step'
OUT=ROOT/'output';OUT.mkdir(exist_ok=True)
R=.375
EXPECTED='0b938e39f0fd84a6b424ef9c49f2c6aa8a232fa2a68f9105a0f9b821c987cc56'

spec=importlib.util.spec_from_file_location('kailh_mod',SCRIPT);mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)

SPLITS=[
 (6.055618158,1.528915605),
 (5.468626708,1.381605638),
 (4.702351963,1.434926793),
 (4.120873789,1.576890676),
]

def add(a,b):return Vector(a.X+b.X,a.Y+b.Y,a.Z+b.Z)
def mul(a,s):return Vector(a.X*s,a.Y*s,a.Z*s)
def cross(a,b):return Vector(a.Y*b.Z-a.Z*b.Y,a.Z*b.X-a.X*b.Z,a.X*b.Y-a.Y*b.X)
def unit(a):
 n=math.sqrt(a.X*a.X+a.Y*a.Y+a.Z*a.Z);return Vector(a.X/n,a.Y/n,a.Z/n)

def summary(name,s):
 bb=s.bounding_box(optimal=True);print(name,'type',type(s).__name__,'valid',s.is_valid(),'solids',len(s.solids()),'faces',len(s.faces()),'edges',len(s.edges()),'volume',s.volume,'area',s.area,'bbox',bb.min.to_tuple(),bb.max.to_tuple())

def profile_wire(x):
 edges=[Edge.make_bezier(*[(x,y,z) for y,z in span]) for span in mod.SOLDER_PROFILE_BEZIER_SPANS_YZ]
 ws=Wire.combine(edges,tol=mod.WIRE_JOIN_TOLERANCE_MM)
 if len(ws)!=1:raise RuntimeError('profile wire')
 return ws[0]

def nearest_u(w,target):
 tx,ty=target
 def d2(u):
  p=w.position_at(u);return (p.Y-tx)**2+(p.Z-ty)**2
 samples=4000
 best=min(range(samples+1),key=lambda i:d2(i/samples))/samples
 lo=max(0,best-2/samples);hi=min(1,best+2/samples)
 phi=(math.sqrt(5)-1)/2
 c=hi-phi*(hi-lo);d=lo+phi*(hi-lo);fc=d2(c);fd=d2(d)
 for _ in range(80):
  if fc<fd:hi,d,fd=d,c,fc;c=hi-phi*(hi-lo);fc=d2(c)
  else:lo,c,fc=c,d,fd;d=lo+phi*(hi-lo);fd=d2(d)
 u=(lo+hi)/2;p=w.position_at(u)
 return u,p,math.sqrt(d2(u))

def sector(path):
 source=path.position_at(0);t=unit(path.tangent_at(0));x=Vector(1,0,0);n=unit(cross(t,x))
 center=add(source,mul(n,R));terminal=add(center,mul(x,R));mid=add(center,mul(add(x,mul(n,-1)),R/math.sqrt(2)))
 es=[Edge.make_line(source,center),Edge.make_line(center,terminal),Edge.make_three_point_arc(terminal,mid,source)]
 ws=Wire.combine(es,tol=1e-8)
 return Face(ws[0])

def pad():
 z=1.75;pts=[(4.54488778941404,3.76578476453536,z),(7.210189558447279,3.7479184533604792,z),(7.21019340060459,6.41087029507891,z),(4.54488778941404,6.41087029507891,z)]
 return extrude(Face(Wire.make_polygon(pts,close=True)),.05,dir=(0,0,1))

def ref_solid():
 if hashlib.sha256(REFERENCE.read_bytes()).hexdigest()!=EXPECTED:raise RuntimeError('sha')
 m=import_step(REFERENCE);r=[s for s in m.solids() if 1.7<s.volume<1.9 and s.bounding_box(optimal=True).min.X>0]
 if len(r)!=1:raise RuntimeError('ref')
 return r[0]

def main():
 ref=ref_solid();summary('REFERENCE',ref);export_step(ref,OUT/'reference_right.step')
 x0=mod.SOLDER_X_START_MM;xt=mod.SOLDER_TAPER_START_X_MM
 full=profile_wire(xt)
 us=[0.0]
 for target in SPLITS:
  u,p,d=nearest_u(full,target);print('SPLIT',target,'u',u,'point',p.to_tuple(),'distance',d);us.append(u)
 us.append(1.0);us=sorted(us)
 print('PARAMS',us)
 paths=[];rolls=[]
 for i,(a,b) in enumerate(zip(us,us[1:])):
  path=full.trim(a,b);paths.append(path);print('PATH',i,'range',a,b,'len',path.length,'edges',len(path.edges()),'start',path.position_at(0).to_tuple(),'end',path.position_at(1).to_tuple())
  export_step(path,OUT/f'path_{i}.step')
  try:roll=Solid.sweep(sector(path).outer_wire(),path)
  except Exception:roll=Solid.sweep(sector(path),path)
  rolls.append(roll);summary(f'ROLL_{i}',roll);export_step(roll,OUT/f'roll_{i}.step')
 base=extrude(Face(mod._solder_profile_wire(x0)),xt-x0,dir=(1,0,0));p=pad();summary('BASE',base);summary('PAD',p)
 try:
  cand=base.fuse(*rolls,p)
  sols=list(cand.solids());print('FUSE_SOLIDS',len(sols),[s.volume for s in sols])
  if len(sols)==1:cand=sols[0]
  else:cand=Compound(children=sols)
  summary('CANDIDATE',cand);export_step(cand,OUT/'candidate_five_intervals.step')
  print('VOLUME_ERROR',abs(cand.volume-ref.volume)/ref.volume*100,'AREA_ERROR',abs(cand.area-ref.area)/ref.area*100)
  rb=ref.bounding_box(optimal=True);cb=cand.bounding_box(optimal=True);print('BBOX_DIFF',abs(cb.size.X-rb.size.X),abs(cb.size.Y-rb.size.Y),abs(cb.size.Z-rb.size.Z))
 except Exception as exc:print('FUSE_FAIL',repr(exc))

if __name__=='__main__':
 try:main()
 except Exception:traceback.print_exc();raise
