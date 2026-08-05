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
SPLITS=[(6.055618158,1.528915605),(5.468626708,1.381605638),(4.702351963,1.434926793),(4.120873789,1.576890676)]

spec=importlib.util.spec_from_file_location('kailh_mod',SCRIPT);mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)

def add(a,b):return Vector(a.X+b.X,a.Y+b.Y,a.Z+b.Z)
def mul(a,s):return Vector(a.X*s,a.Y*s,a.Z*s)
def cross(a,b):return Vector(a.Y*b.Z-a.Z*b.Y,a.Z*b.X-a.X*b.Z,a.X*b.Y-a.Y*b.X)
def unit(a):
 n=math.sqrt(a.X*a.X+a.Y*a.Y+a.Z*a.Z);return Vector(a.X/n,a.Y/n,a.Z/n)

def summary(name,s):
 bb=s.bounding_box(optimal=True);print(name,'type',type(s).__name__,'valid',s.is_valid(),'solids',len(s.solids()),'faces',len(s.faces()),'edges',len(s.edges()),'volume',s.volume,'area',s.area,'bbox',bb.min.to_tuple(),bb.max.to_tuple(),'center',s.center().to_tuple())

def full_wire(x):
 es=[Edge.make_bezier(*[(x,y,z) for y,z in span]) for span in mod.SOLDER_PROFILE_BEZIER_SPANS_YZ]
 ws=Wire.combine(es,tol=mod.WIRE_JOIN_TOLERANCE_MM)
 if len(ws)!=1:raise RuntimeError('wire')
 return ws[0]

def nearest_u(w,target):
 ty,tz=target
 def f(u):
  p=w.position_at(u);return (p.Y-ty)**2+(p.Z-tz)**2
 n=3000;i=min(range(n+1),key=lambda j:f(j/n));lo=max(0,(i-2)/n);hi=min(1,(i+2)/n);phi=(math.sqrt(5)-1)/2;c=hi-phi*(hi-lo);d=lo+phi*(hi-lo);fc=f(c);fd=f(d)
 for _ in range(70):
  if fc<fd:hi,d,fd=d,c,fc;c=hi-phi*(hi-lo);fc=f(c)
  else:lo,c,fc=c,d,fd;d=lo+phi*(hi-lo);fd=f(d)
 return (lo+hi)/2

def cutter_face(path):
 s=path.position_at(0);t=unit(path.tangent_at(0));x=Vector(1,0,0);n=unit(cross(t,x));a=add(s,mul(x,R));c=add(s,mul(n,R));b=add(a,mul(n,R));mid=add(c,mul(add(x,mul(n,-1)),R/math.sqrt(2)))
 ws=Wire.combine([Edge.make_line(s,a),Edge.make_line(a,b),Edge.make_three_point_arc(b,mid,s)],tol=1e-8)
 f=Face(ws[0]);print('CUTTER_SECTION_AREA',f.area,'expected',R*R*(1-math.pi/4))
 return f

def try_sweep(path):
 try:r=Solid.sweep(cutter_face(path).outer_wire(),path)
 except Exception:
  try:r=Solid.sweep(cutter_face(path),path)
  except Exception as exc:return None,repr(exc)
 return r,None

def adaptive(path,tag,depth=0,max_depth=8,min_length=.004):
 r,err=try_sweep(path)
 if r is not None and r.is_valid():
  print('ACCEPT',tag,'depth',depth,'len',path.length,'vol',r.volume);return [r]
 print('REJECT',tag,'depth',depth,'len',path.length,'valid',None if r is None else r.is_valid(),'err',err)
 if depth>=max_depth or path.length<min_length:return []
 return adaptive(path.trim(0,.5),tag+'a',depth+1,max_depth,min_length)+adaptive(path.trim(.5,1),tag+'b',depth+1,max_depth,min_length)

def pad():
 z=1.75;pts=[(4.54488778941404,3.76578476453536,z),(7.210189558447279,3.7479184533604792,z),(7.21019340060459,6.41087029507891,z),(4.54488778941404,6.41087029507891,z)]
 return extrude(Face(Wire.make_polygon(pts,close=True)),.05,dir=(0,0,1))

def main():
 if hashlib.sha256(REFERENCE.read_bytes()).hexdigest()!=EXPECTED:raise RuntimeError('sha')
 m=import_step(REFERENCE);ref=[s for s in m.solids() if 1.7<s.volume<1.9 and s.bounding_box(optimal=True).min.X>0][0];summary('REFERENCE',ref);export_step(ref,OUT/'reference.step')
 x0=mod.SOLDER_X_START_MM;xt=mod.SOLDER_TAPER_START_X_MM;xend=xt+R
 w=full_wire(xt);us=[0]+[nearest_u(w,p) for p in SPLITS]+[1];us=sorted(us);print('US',us)
 cutters=[]
 for i,(a,b) in enumerate(zip(us,us[1:])):
  pieces=adaptive(w.trim(a,b),f'i{i}');print('INTERVAL',i,'pieces',len(pieces),'volsum',sum(p.volume for p in pieces));cutters+=pieces
 print('CUTTERS',len(cutters),'volsum',sum(p.volume for p in cutters));export_step(Compound(children=cutters),OUT/'cutter_pieces.step')
 full=extrude(Face(mod._solder_profile_wire(x0)),xend-x0,dir=(1,0,0));summary('FULL_PRISM',full)
 result=full
 used=0
 for i,c in enumerate(cutters):
  try:
   cut=result.cut(c)
   sols=list(cut.solids())
   if len(sols)==1:
    result=sols[0];used+=1
   else:print('CUT_MULTI',i,len(sols),[s.volume for s in sols])
  except Exception as exc:print('CUT_FAIL',i,repr(exc))
 print('CUT_USED',used);summary('AFTER_R0375',result);export_step(result,OUT/'after_r0375.step')
 pd=pad();summary('PAD',pd)
 try:
  fused=result.fuse(pd);sols=list(fused.solids());print('PAD_FUSE_SOLIDS',len(sols),[s.volume for s in sols]);candidate=sols[0] if len(sols)==1 else Compound(children=sols)
 except Exception as exc:print('PAD_FUSE_FAIL',repr(exc));candidate=Compound(children=[result,pd])
 summary('CANDIDATE',candidate);export_step(candidate,OUT/'candidate_r0375_pad.step')
 print('ERRORS volume%',abs(candidate.volume-ref.volume)/ref.volume*100,'area%',abs(candidate.area-ref.area)/ref.area*100)
 rb=ref.bounding_box(optimal=True);cb=candidate.bounding_box(optimal=True);print('BBOX_DIFF',abs(cb.size.X-rb.size.X),abs(cb.size.Y-rb.size.Y),abs(cb.size.Z-rb.size.Z))
 try:
  am=ref.cut(candidate);bm=candidate.cut(ref);av=sum(s.volume for s in am.solids());bv=sum(s.volume for s in bm.solids());print('BOOLEAN',av,bv,av+bv,(av+bv)/ref.volume*100);export_step(am,OUT/'ref_minus.step');export_step(bm,OUT/'cand_minus.step')
 except Exception as exc:print('BOOLEAN_FAIL',repr(exc))

if __name__=='__main__':
 try:main()
 except Exception:traceback.print_exc();raise
