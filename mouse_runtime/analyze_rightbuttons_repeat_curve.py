from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID,TopAbs_FACE,TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

TARGET_IDS=(357,358)

def read(path):
 r=STEPControl_Reader(); s=int(r.ReadFile(str(path))); assert s==int(IFSelect_RetDone); r.TransferRoots(); return r.OneShape()
def exp(shape,typ):
 x=TopExp_Explorer(shape,typ); out=[]
 while x.More():
  q=x.Current()
  if typ==TopAbs_SOLID:q=TopoDS.Solid_s(q)
  elif typ==TopAbs_FACE:q=TopoDS.Face_s(q)
  elif typ==TopAbs_EDGE:q=TopoDS.Edge_s(q)
  out.append(q); x.Next()
 return out
def same(a,b):return bool(a.IsSame(b))
def elen(e):
 g=GProp_GProps(); BRepGProp.LinearProperties_s(e,g); return float(g.Mass())
def sample(e,n=101):
 c=BRepAdaptor_Curve(e); a=float(c.FirstParameter()); b=float(c.LastParameter())
 return np.array([[float((p:=c.Value(a+(b-a)*i/(n-1))).X()),float(p.Y()),float(p.Z())] for i in range(n)])
def fit_rigid_2d(A,B):
 # return RMS after optimal planar rigid transform B->A, preserving scale
 ca=A[:,:2].mean(0); cb=B[:,:2].mean(0); X=A[:,:2]-ca; Y=B[:,:2]-cb
 H=Y.T@X; U,S,Vt=np.linalg.svd(H); R=U@Vt
 if np.linalg.det(R)<0:
  U[:,-1]*=-1; R=U@Vt
 Y2=Y@R; rms=float(np.sqrt(np.mean(np.sum((Y2-X)**2,axis=1))))
 return rms, R.tolist(), (ca-cb@R).tolist()
def fit_translation_3d(A,B):
 d=(A-B).mean(0); E=B+d-A
 return float(np.sqrt(np.mean(np.sum(E*E,axis=1)))),d.tolist(),float(np.max(np.linalg.norm(E,axis=1)))

root=read('reference/Mouse.STEP'); solids=exp(root,TopAbs_SOLID); rb=solids[9]
unique=[]
for e in exp(rb,TopAbs_EDGE):
 if not any(same(e,u) for u in unique):unique.append(e)
rows=[]
for j,e in enumerate(unique,1):
 try: pts=sample(e); L=elen(e)
 except: continue
 rows.append({'id':j,'length':L,'pts':pts})
result={}
for tid in TARGET_IDS:
 T=next(r for r in rows if r['id']==tid); A=T['pts']; candidates=[]
 for C in rows:
  if C['id']==tid:continue
  # curve congruence requires nearly equal arc length
  if abs(C['length']-T['length'])>0.02:continue
  for rev in (False,True):
   B=C['pts'][::-1] if rev else C['pts']
   r2,R,tr=fit_rigid_2d(A,B)
   r3,d,mx=fit_translation_3d(A,B)
   candidates.append({'candidate':C['id'],'length':C['length'],'reversed':rev,'rigid2d_rms_mm':r2,'translation3d_rms_mm':r3,'translation3d_max_mm':mx,'translation':d,'rotation2d':R})
 candidates.sort(key=lambda x:x['rigid2d_rms_mm'])
 result[str(tid)]={'length':T['length'],'best_congruent':candidates[:30]}
Path('mouse_runtime/rightbuttons_repeat_curve_analysis.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
